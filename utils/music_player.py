from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import discord
import yt_dlp
import imageio_ffmpeg

log = logging.getLogger("MusicPlayer")

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

# ─── ThreadPool riêng cho yt-dlp ─────────────────────────────────────────────
_YTDL_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ytdl")

# ─── Cookie setup ─────────────────────────────────────────────────────────────
# Thứ tự ưu tiên: cookies.txt file → browser cookies → không dùng cookie
_COOKIES_FILE = Path(__file__).parent.parent / "cookies.txt"
_BROWSER_ORDER = ["chrome", "edge", "firefox", "chromium", "brave"]

def _get_cookie_opts() -> dict:
    """Tự động phát hiện cookie phù hợp nhất."""
    # 1. File cookies.txt (ưu tiên cao nhất, ổn định nhất)
    if _COOKIES_FILE.exists():
        log.info(f"🍪 Dùng cookies.txt: {_COOKIES_FILE}")
        return {"cookiefile": str(_COOKIES_FILE)}
    # 2. Browser được chỉ định trong .env
    browser_env = os.getenv("COOKIE_BROWSER", "").lower().strip()
    if browser_env:
        log.info(f"🍪 Dùng cookies từ browser: {browser_env}")
        return {"cookiesfrombrowser": (browser_env,)}
    # Không dùng cookies nếu không cần — tránh conflict PO Token
    log.info("ℹ️  Không dùng cookies (player_client sẽ xử lý auth)")
    return {}

_COOKIE_OPTS = _get_cookie_opts()

# ─── YT-DLP Options (tối ưu tốc độ) ─────────────────────────────────────────
YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "scsearch",
    "source_address": "0.0.0.0",
    "skip_download": True,
    "writethumbnail": False,
    "writesubtitles": False,
    "writeautomaticsub": False,
    "writedescription": False,
    "writeannotations": False,
    "ignoreerrors": True,
    "socket_timeout": 10,
    "retries": 3,
    # Dùng Node.js để giải mã chữ ký YouTube (bắt buộc cho nhiều video)
    "js_runtimes": {"node": {}},
    "extractor_args": {
        "youtube": {
            "skip": ["translated_subs"],
            "player_client": ["web", "android"],
        }
    },
    "postprocessors": [],
    **_COOKIE_OPTS,
}

# ─── FFmpeg pipe options (dùng khi pipe từ yt-dlp process) ──────────────────
FFMPEG_PIPE_OPTIONS = {
    "pipe": True,
    "options": "-vn",
}

# ─── FFmpeg URL options (fallback) ───────────────────────────────────────────
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

URL_REGEX = re.compile(
    r"^(https?://)?(www\.)?"
    r"(youtube\.com|youtu\.be|music\.youtube\.com|soundcloud\.com)"
)


# ─── Song ────────────────────────────────────────────────────────────────────

class Song:
    """Đại diện một bài nhạc trong hàng đợi."""

    def __init__(self, data: dict, requester: discord.Member):
        self.extractor: str   = data.get("extractor", "") or ""
        self.url: str         = data.get("url") or ""
        self.webpage_url: str = data.get("webpage_url") or self.url
        self.title: str       = data.get("title", "Unknown")
        self.uploader: str    = data.get("uploader", "Unknown")
        self.duration: int    = int(data.get("duration") or 0)
        self.thumbnail: str   = data.get("thumbnail", "")
        self.requester: discord.Member = requester

    @property
    def duration_str(self) -> str:
        m, s = divmod(self.duration, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def create_embed(self, title: str = "🎵 Đang phát") -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=f"[{self.title}]({self.webpage_url})",
            color=0x1DB954,
        )
        embed.set_thumbnail(url=self.thumbnail)
        embed.add_field(name="⏱️ Thời lượng", value=self.duration_str,    inline=True)
        embed.add_field(name="🎤 Kênh",        value=self.uploader,        inline=True)
        embed.add_field(name="👤 Yêu cầu bởi", value=self.requester.mention, inline=True)
        return embed


# ─── QueueEntry (metadata trước khi resolve stream URL) ──────────────────────

class QueueEntry:
    """
    Lưu trữ thông tin bài nhạc TRƯỚC khi resolve stream URL.
    Stream URL YouTube hết hạn sau ~6h nên chỉ resolve ngay trước khi phát.
    """
    def __init__(self, data: dict, requester: discord.Member):
        self.data       = data          # Raw yt-dlp data (có thể là partial)
        self.requester  = requester
        self._song: Optional[Song] = None   # Cached sau khi resolve

    @property
    def title(self) -> str:
        return self.data.get("title", "Unknown")

    @property
    def duration(self) -> int:
        return int(self.data.get("duration") or 0)

    @property
    def webpage_url(self) -> str:
        return self.data.get("webpage_url", "")

    async def resolve(self, loop: asyncio.AbstractEventLoop) -> Optional[Song]:
        """Resolve stream URL thực sự, trả về Song sẵn sàng để phát."""
        if self._song:
            return self._song
        try:
            # Re-extract để lấy stream URL mới nhất (tránh URL expired)
            url = self.webpage_url or self.data.get("url", "")
            if not url:
                return None
            data = await loop.run_in_executor(
                _YTDL_POOL,
                lambda: _ytdl_extract(url, YTDL_OPTIONS),
            )
            if not data:
                return None
            # Lấy entry đầu nếu là playlist
            if "entries" in data:
                entries = [e for e in data["entries"] if e]
                data = entries[0] if entries else None
            if not data:
                return None
            self._song = Song(data, self.requester)
            return self._song
        except Exception as e:
            log.error(f"Lỗi resolve stream URL cho '{self.title}': {e}")
            return None


# ─── MusicPlayer ─────────────────────────────────────────────────────────────

class MusicPlayer:
    """Quản lý hàng đợi và phát nhạc cho một guild."""

    def __init__(self, ctx, idle_timeout: int = 300):
        self.ctx          = ctx
        self.guild        = ctx.guild
        self.channel      = ctx.channel
        self.idle_timeout = idle_timeout

        self._queue: deque[QueueEntry]     = deque()
        self.current: Optional[Song]       = None
        self._prefetched: Optional[Song]   = None   # Bài đã pre-fetch sẵn
        self.volume: float                 = 0.5
        self._next  = asyncio.Event()
        self._task  = asyncio.ensure_future(self._player_loop())

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def queue(self) -> list[QueueEntry]:
        return list(self._queue)

    @property
    def is_playing(self) -> bool:
        vc = self.guild.voice_client
        return bool(vc and vc.is_playing())

    @property
    def is_paused(self) -> bool:
        vc = self.guild.voice_client
        return bool(vc and vc.is_paused())

    # ── Tìm kiếm ─────────────────────────────────────────────────────────────

    @staticmethod
    async def search(query: str, *, loop: asyncio.AbstractEventLoop = None) -> Optional[dict]:
        """Tìm kiếm và trả về metadata dict (KHÔNG có stream URL để nhanh hơn)."""
        loop = loop or asyncio.get_event_loop()
        is_url = bool(URL_REGEX.match(query))
        search_query = query if is_url else f"scsearch:{query}"

        # Khi search: dùng flat_extract để cực nhanh (chỉ lấy metadata, không URL)
        opts = dict(YTDL_OPTIONS)
        if not is_url:
            opts["extract_flat"] = "in_playlist"   # Chỉ lấy metadata nhẹ

        try:
            data = await loop.run_in_executor(
                _YTDL_POOL,
                lambda: _ytdl_extract(search_query, opts),
            )
        except Exception as e:
            log.error(f"Lỗi search: {e}")
            return None

        if not data:
            return None
        if "entries" in data:
            entries = [e for e in data["entries"] if e]
            return entries[0] if entries else None
        return data

    @staticmethod
    async def search_many(query: str, count: int = 5, *, loop: asyncio.AbstractEventLoop = None) -> list[dict]:
        """Tìm nhiều kết quả (flat, nhanh)."""
        loop = loop or asyncio.get_event_loop()
        opts = dict(YTDL_OPTIONS)
        opts["extract_flat"] = "in_playlist"
        opts["noplaylist"] = False

        try:
            data = await loop.run_in_executor(
                _YTDL_POOL,
                lambda: _ytdl_extract(f"scsearch{count}:{query}", opts),
            )
        except Exception as e:
            log.error(f"Lỗi search_many: {e}")
            return []

        if not data:
            return []
        if "entries" in data:
            return [e for e in data["entries"] if e][:count]
        return [data]

    # ── Hàng đợi ─────────────────────────────────────────────────────────────

    def enqueue(self, entry: QueueEntry):
        self._queue.append(entry)

    def clear_queue(self):
        self._queue.clear()
        self._prefetched = None

    def skip(self):
        self._prefetched = None   # Huỷ pre-fetch khi skip
        vc = self.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()

    def pause(self):
        vc = self.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            return True
        return False

    def resume(self):
        vc = self.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            return True
        return False

    def set_volume(self, vol: float):
        self.volume = max(0.0, min(1.0, vol))
        vc = self.guild.voice_client
        if vc and vc.source:
            vc.source.volume = self.volume

    # ── Vòng lặp phát nhạc ───────────────────────────────────────────────────

    async def _player_loop(self):
        await self.ctx.bot.wait_until_ready()
        loop = asyncio.get_event_loop()

        while True:
            self._next.clear()

            # ── Chờ có bài hoặc timeout idle ─────────────────────────────────
            if not self._queue and not self._prefetched:
                try:
                    await asyncio.wait_for(self._wait_for_song(), timeout=self.idle_timeout)
                except asyncio.TimeoutError:
                    await self._idle_disconnect()
                    return

            # ── Lấy song: dùng pre-fetch nếu có ─────────────────────────────
            if self._prefetched:
                song = self._prefetched
                self._prefetched = None
                log.info(f"▶ Phát từ pre-fetch: {song.title}")
            else:
                entry = self._queue.popleft()
                log.info(f"🔄 Resolve stream: {entry.title}")
                song = await entry.resolve(loop)

            if not song:
                await self.channel.send(
                    embed=discord.Embed(
                        description="❌ Không thể phát bài này. Bỏ qua...",
                        color=0xFF4444,
                    )
                )
                continue

            self.current = song

            # ── Pre-fetch bài tiếp theo trong background ──────────────────────
            if self._queue:
                asyncio.ensure_future(self._prefetch_next(loop))

            # ── Tạo FFmpeg source qua pipe (stable hơn URL trực tiếp) ────────
            vc = self.guild.voice_client
            if not vc:
                self.current = None
                return

            try:
                # Kiểm tra nguồn: YouTube dùng yt-dlp pipe để tránh 403
                # SoundCloud và các nguồn khác dùng direct stream (HLS/MP3 URL)
                is_youtube = (
                    "youtube" in song.extractor
                    or "youtube.com" in song.webpage_url
                    or "youtu.be" in song.webpage_url
                )
                if is_youtube:
                    log.info(f"🎵 YouTube pipe: {song.title}")
                    source = await loop.run_in_executor(
                        None, lambda: self._make_pipe_source(song)
                    )
                else:
                    # SoundCloud / direct URL → FFmpeg stream trực tiếp
                    log.info(f"🎵 Direct stream ({song.extractor or 'unknown'}): {song.title} → {song.url[:60]}")
                    source = discord.FFmpegPCMAudio(
                        song.url,
                        before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                        options="-vn",
                        executable=FFMPEG_EXE,
                    )
                source = discord.PCMVolumeTransformer(source, volume=self.volume)
            except Exception as e:
                log.error(f"Lỗi tạo source cho '{song.title}': {e}")
                await self.channel.send(
                    embed=discord.Embed(
                        description=f"❌ Lỗi phát **{song.title}**. Bỏ qua...",
                        color=0xFF4444,
                    )
                )
                self.current = None
                continue

            def _after(err):
                if err:
                    log.error(f"FFmpeg lỗi khi phát '{song.title}': {err}")
                self._next.set()

            vc.play(source, after=_after)
            await self.channel.send(embed=song.create_embed("🎵 Đang phát"))

            await self._next.wait()
            self.current = None

    @staticmethod
    def _make_pipe_source(song: Song) -> discord.FFmpegPCMAudio:
        """
        Dùng yt-dlp subprocess pipe audio trực tiếp vào FFmpeg.
        Tránh hoàn toàn vấn đề URL expiry và HTTP 403 khi stream.
        """
        ytdl_cmd = [
            "yt-dlp",
            "--format", "bestaudio/best",
            "--quiet",
            "--no-warnings",
            "--output", "-",       # output ra stdout
            song.webpage_url,
        ]
        # Thêm cookies nếu có
        cookies_file = Path(__file__).parent.parent / "cookies.txt"
        if cookies_file.exists():
            ytdl_cmd += ["--cookies", str(cookies_file)]

        log.info(f"🎵 Pipe: {' '.join(ytdl_cmd[-3:])}")
        process = subprocess.Popen(
            ytdl_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        return discord.FFmpegPCMAudio(
            process.stdout, pipe=True, executable=FFMPEG_EXE, options="-vn"
        )

    async def _prefetch_next(self, loop: asyncio.AbstractEventLoop):
        """Pre-fetch stream URL của bài tiếp trong queue (chạy nền)."""
        if not self._queue:
            return
        next_entry = self._queue[0]   # Peek, không pop
        log.info(f"🔁 Pre-fetching: {next_entry.title}")
        try:
            song = await next_entry.resolve(loop)
            if song and self._queue and self._queue[0] is next_entry:
                # Chỉ cache nếu bài này vẫn còn ở đầu queue
                self._prefetched = song
                self._queue.popleft()   # Đã pre-fetch → remove khỏi queue
                log.info(f"✅ Pre-fetch xong: {song.title}")
        except Exception as e:
            log.warning(f"Pre-fetch thất bại (sẽ resolve khi phát): {e}")

    async def _wait_for_song(self):
        while not self._queue and not self._prefetched:
            await asyncio.sleep(0.5)

    async def _idle_disconnect(self):
        vc = self.guild.voice_client
        if vc:
            await vc.disconnect()
        await self.channel.send(
            embed=discord.Embed(
                description="⏹️ Hết nhạc và không có ai yêu cầu, bot đã rời kênh.",
                color=0x888888,
            )
        )

    def destroy(self):
        self._task.cancel()
        self.clear_queue()
        _YTDL_POOL.shutdown(wait=False)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _ytdl_extract(query: str, opts: dict) -> Optional[dict]:
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(query, download=False)
