from __future__ import annotations

import asyncio
import logging
import os
import re
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

def _get_ytdl_pool() -> ThreadPoolExecutor:
    """Trả về pool đang hoạt động. Tạo lại nếu đã bị shutdown."""
    global _YTDL_POOL
    if getattr(_YTDL_POOL, '_shutdown', False):
        _YTDL_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ytdl")
    return _YTDL_POOL

# ─── Cookie setup ─────────────────────────────────────────────────────────────
_COOKIES_FILE = Path(__file__).parent.parent / "cookies.txt"

def _get_cookie_opts() -> dict:
    if _COOKIES_FILE.exists():
        log.info(f"🍪 Dùng cookies.txt: {_COOKIES_FILE}")
        return {"cookiefile": str(_COOKIES_FILE)}
    browser_env = os.getenv("COOKIE_BROWSER", "").lower().strip()
    if browser_env:
        log.info(f"🍪 Dùng cookies từ browser: {browser_env}")
        return {"cookiesfrombrowser": (browser_env,)}
    return {}

_COOKIE_OPTS = _get_cookie_opts()

# ─── YT-DLP Options (Chỉ YouTube, tối ưu lấy URL) ────────────────────────────
YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "skip_download": True,
    "writethumbnail": False,
    "writesubtitles": False,
    "writeautomaticsub": False,
    "writedescription": False,
    "writeannotations": False,
    "ignoreerrors": True,
    "socket_timeout": 15,
    "retries": 3,
    "extractor_args": {
        "youtube": {
            "skip": ["translated_subs"],
            "player_client": ["web", "android"],
        }
    },
    "postprocessors": [],
    **_COOKIE_OPTS,
}

# ─── FFmpeg Options (Dùng flags riêng lẻ thay vì -headers để tránh crash -11) ──
# Dùng -user_agent và -referer thay vì -headers vì Windows/CMD shell hay lỗi quote
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
REFERER = "https://www.youtube.com/"

FFMPEG_OPTIONS = (
    "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
    f'-user_agent "{USER_AGENT}" '
    f'-referer "{REFERER}"'
)

URL_REGEX = re.compile(
    r"^(https?://)?(www\.)?"
    r"(youtube\.com|youtu\.be|music\.youtube\.com)"
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
            color=0xFF0000,
        )
        embed.set_thumbnail(url=self.thumbnail)
        embed.add_field(name="⏱️ Thời lượng", value=self.duration_str,       inline=True)
        embed.add_field(name="🎤 Kênh",        value=self.uploader,           inline=True)
        embed.add_field(name="👤 Yêu cầu bởi", value=self.requester.mention,  inline=True)
        return embed


# ─── QueueEntry ───────────────────────────────────────────────────────────────

class QueueEntry:
    """Lưu metadata bài nhạc. Stream URL sẽ được resolve ngay trước khi phát."""
    def __init__(self, data: dict, requester: discord.Member):
        self.data      = data
        self.requester = requester
        self._song: Optional[Song] = None

    @property
    def title(self) -> str:
        return self.data.get("title", "Unknown")

    @property
    def duration(self) -> int:
        return int(self.data.get("duration") or 0)

    @property
    def webpage_url(self) -> str:
        return self.data.get("webpage_url", "") or self.data.get("url", "")

    async def resolve(self, loop: asyncio.AbstractEventLoop) -> Optional[Song]:
        """Lấy stream URL mới nhất."""
        if self._song:
            return self._song
        try:
            url = self.webpage_url
            if not url:
                return None

            log.info(f"🔄 Resolving YouTube: {self.title}")
            data = await loop.run_in_executor(
                _get_ytdl_pool(),
                lambda: _ytdl_extract(url, YTDL_OPTIONS),
            )
            if not data:
                return None
            if "entries" in data:
                data = data["entries"][0] if data["entries"] else None
            if not data:
                return None

            self._song = Song(data, self.requester)
            return self._song
        except Exception as e:
            log.error(f"Lỗi resolve '{self.title}': {e}")
            return None


# ─── MusicPlayer ─────────────────────────────────────────────────────────────

class MusicPlayer:
    """Quản lý hàng đợi và phát nhạc cho một guild."""

    def __init__(self, ctx, idle_timeout: int = 300):
        self.ctx          = ctx
        self.guild        = ctx.guild
        self.channel      = ctx.channel
        self.idle_timeout = idle_timeout

        self._queue: deque[QueueEntry]   = deque()
        self.current: Optional[Song]     = None
        self.volume: float               = 0.5
        self._next  = asyncio.Event()
        self._task  = asyncio.ensure_future(self._player_loop())

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

    @staticmethod
    async def search(query: str, *, loop: asyncio.AbstractEventLoop = None) -> Optional[dict]:
        loop = loop or asyncio.get_event_loop()
        is_url = bool(URL_REGEX.match(query))
        search_query = query if is_url else f"ytsearch:{query}"
        opts = dict(YTDL_OPTIONS)
        if not is_url: opts["extract_flat"] = "in_playlist"

        try:
            data = await loop.run_in_executor(_get_ytdl_pool(), lambda: _ytdl_extract(search_query, opts))
            if not data: return None
            if "entries" in data: return data["entries"][0] if data["entries"] else None
            return data
        except Exception as e:
            log.error(f"Lỗi search: {e}")
            return None

    @staticmethod
    async def search_many(query: str, count: int = 5, *, loop: asyncio.AbstractEventLoop = None) -> list[dict]:
        loop = loop or asyncio.get_event_loop()
        opts = dict(YTDL_OPTIONS)
        opts["extract_flat"] = "in_playlist"
        opts["noplaylist"] = False
        try:
            data = await loop.run_in_executor(_get_ytdl_pool(), lambda: _ytdl_extract(f"ytsearch{count}:{query}", opts))
            if not data: return []
            return [e for e in data.get("entries", []) if e][:count] if "entries" in data else [data]
        except Exception as e:
            log.error(f"Lỗi search_many: {e}")
            return []

    def enqueue(self, entry: QueueEntry):
        self._queue.append(entry)

    def clear_queue(self):
        self._queue.clear()

    def skip(self):
        vc = self.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()): vc.stop()

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
        if vc and vc.source: vc.source.volume = self.volume

    async def _player_loop(self):
        await self.ctx.bot.wait_until_ready()
        loop = asyncio.get_event_loop()

        while True:
            self._next.clear()
            if not self._queue:
                try:
                    await asyncio.wait_for(self._wait_for_song(), timeout=self.idle_timeout)
                except asyncio.TimeoutError:
                    await self._idle_disconnect()
                    return

            entry = self._queue.popleft()
            song  = await entry.resolve(loop)
            
            if not song:
                await self.channel.send(embed=discord.Embed(description="❌ Lỗi resolve bài này. Bỏ qua...", color=0xFF4444))
                continue

            self.current = song
            vc = self.guild.voice_client
            if not vc: return

            try:
                log.info(f"🎵 URL play: {song.title}")
                source = discord.FFmpegPCMAudio(
                    song.url,
                    before_options=FFMPEG_OPTIONS,
                    options="-vn",
                    executable=FFMPEG_EXE
                )
                source = discord.PCMVolumeTransformer(source, volume=self.volume)
                
                def _after(err):
                    if err: log.error(f"FFmpeg lỗi: {err}")
                    self._next.set()

                vc.play(source, after=_after)
                await self.channel.send(embed=song.create_embed("🎵 Đang phát"))
                await self._next.wait()
            except Exception as e:
                log.error(f"Lỗi play '{song.title}': {e}")
                await self.channel.send(embed=discord.Embed(description=f"❌ Lỗi phát **{song.title}**.", color=0xFF4444))
            
            self.current = None

    async def _wait_for_song(self):
        while not self._queue: await asyncio.sleep(0.5)

    async def _idle_disconnect(self):
        vc = self.guild.voice_client
        if vc: await vc.disconnect()
        await self.channel.send(embed=discord.Embed(description="⏹️ Đã rời kênh vì không có nhạc.", color=0x888888))

    def destroy(self):
        self._task.cancel()
        self.clear_queue()

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _ytdl_extract(query: str, opts: dict) -> Optional[dict]:
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(query, download=False)
