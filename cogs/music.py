from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import discord
from discord.ext import commands

from utils.music_player import MusicPlayer, Song, QueueEntry

log = logging.getLogger("MusicCog")

IDLE_TIMEOUT = int(os.getenv("IDLE_TIMEOUT", 300))
PREFIX       = os.getenv("PREFIX", "!")

# Màu sắc embed
COLOR_GREEN  = 0x1DB954   # Spotify green
COLOR_RED    = 0xFF4444
COLOR_YELLOW = 0xFFAA00
COLOR_BLUE   = 0x5865F2   # Discord blurple
COLOR_GREY   = 0x888888


def err_embed(msg: str) -> discord.Embed:
    return discord.Embed(description=f"❌  {msg}", color=COLOR_RED)

def ok_embed(msg: str) -> discord.Embed:
    return discord.Embed(description=msg, color=COLOR_GREEN)

def warn_embed(msg: str) -> discord.Embed:
    return discord.Embed(description=f"⚠️  {msg}", color=COLOR_YELLOW)


class Music(commands.Cog):
    """🎵 Cog điều khiển nhạc cho Discord Bot."""

    def __init__(self, bot: commands.Bot):
        self.bot     = bot
        self._players: dict[int, MusicPlayer] = {}   # guild_id → MusicPlayer

    # ── Internal helpers ──────────────────────────────────────────────────────

    def get_player(self, ctx: commands.Context) -> MusicPlayer:
        """Lấy hoặc tạo MusicPlayer cho guild hiện tại."""
        gid = ctx.guild.id
        if gid not in self._players:
            self._players[gid] = MusicPlayer(ctx, idle_timeout=IDLE_TIMEOUT)
        return self._players[gid]

    def remove_player(self, guild_id: int):
        player = self._players.pop(guild_id, None)
        if player:
            player.destroy()

    async def ensure_voice(self, ctx: commands.Context) -> bool:
        """Kiểm tra người dùng có ở voice channel không, bot tham gia nếu cần."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send(embed=err_embed("Bạn phải vào **Voice Channel** trước!"))
            return False

        target_channel = ctx.author.voice.channel
        vc = ctx.guild.voice_client

        # Nếu voice client đang ở sai kênh → di chuyển
        if vc and vc.channel == target_channel:
            return True  # Đã đúng kênh, không cần làm gì thêm

        # Nếu vc tồn tại nhưng bị broken (transport đang đóng) hoặc sai kênh → dọn dẹp trước
        if vc:
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass
            # Chờ discord.py dọn sạch state
            await asyncio.sleep(0.5)

        # Thử kết nối (có 1 lần retry nếu thất bại)
        for attempt in range(2):
            try:
                await target_channel.connect(timeout=20.0, reconnect=True)
                return True
            except asyncio.TimeoutError:
                if attempt == 0:
                    log.warning("Voice connect timeout, thử lại lần 2...")
                    await asyncio.sleep(1)
                    continue
                await ctx.send(embed=err_embed(
                    "⏱️ Hết thời gian kết nối Voice Channel. Vui lòng thử lại!"
                ))
                return False
            except discord.ClientException as e:
                log.error(f"ClientException khi connect voice: {e}")
                await ctx.send(embed=err_embed("Không thể kết nối tới voice channel!"))
                return False
            except Exception as e:
                # Bắt ClientConnectionResetError và các lỗi transport khác
                log.error(f"Lỗi kết nối voice (attempt {attempt+1}): {type(e).__name__}: {e}")
                if attempt == 0:
                    # Thử dọn sạch rồi retry
                    vc2 = ctx.guild.voice_client
                    if vc2:
                        try:
                            await vc2.disconnect(force=True)
                        except Exception:
                            pass
                    await asyncio.sleep(1)
                    continue
                await ctx.send(embed=err_embed(
                    f"❌ Lỗi kết nối voice channel: `{type(e).__name__}`. Vui lòng thử lại!"
                ))
                return False

        return False

    # ── Lệnh /help ────────────────────────────────────────────────────────────

    @commands.command(name="help", aliases=["h"])
    async def help_cmd(self, ctx: commands.Context):
        """Hiển thị danh sách lệnh."""
        p = PREFIX
        embed = discord.Embed(
            title="🎵 Music Bot — Danh sách lệnh",
            color=COLOR_BLUE,
        )
        embed.set_footer(text=f"Prefix: {p}  |  Ví dụ: {p}play Sơn Tùng MTP")

        cmds = [
            (f"`{p}play <tên/URL>`",    "Phát nhạc hoặc thêm vào hàng đợi"),
            (f"`{p}search <từ khóa>`",  "Tìm 5 bài, chọn bằng số"),
            (f"`{p}pause`",             "Tạm dừng"),
            (f"`{p}resume`",            "Tiếp tục phát"),
            (f"`{p}skip`",              "Bỏ qua bài hiện tại"),
            (f"`{p}stop`",              "Dừng & xóa hàng đợi"),
            (f"`{p}queue`",             "Xem hàng đợi"),
            (f"`{p}nowplaying`",        "Xem bài đang phát"),
            (f"`{p}volume <0-100>`",    "Chỉnh âm lượng"),
            (f"`{p}disconnect`",        "Rời voice channel"),
        ]
        for name, value in cmds:
            embed.add_field(name=name, value=value, inline=False)

        await ctx.send(embed=embed)

    # ── !play ─────────────────────────────────────────────────────────────────

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx: commands.Context, *, query: str):
        """Tìm kiếm và phát nhạc. Hỗ trợ từ khóa và URL YouTube."""
        if not await self.ensure_voice(ctx):
            return

        async with ctx.typing():
            msg = await ctx.send(
                embed=discord.Embed(
                    description=f"🔍 Đang tìm kiếm: **{query}**...",
                    color=COLOR_GREY,
                )
            )

            data = await MusicPlayer.search(query, loop=self.bot.loop)
            if not data:
                await msg.edit(embed=err_embed(f"Không tìm thấy kết quả cho: **{query}**"))
                return

            entry  = QueueEntry(data, requester=ctx.author)
            player = self.get_player(ctx)
            player.enqueue(entry)

            if player.is_playing or player.is_paused:
                # Hiển thị embed nhanh từ metadata (không cần đợi stream URL)
                embed = discord.Embed(
                    title="✅ Đã thêm vào hàng đợi",
                    description=f"[{entry.title}]({entry.webpage_url})",
                    color=0x1DB954,
                )
                m, s = divmod(entry.duration, 60)
                embed.add_field(name="⏱️ Thời lượng", value=f"{m:02d}:{s:02d}", inline=True)
                embed.add_field(name="📋 Vị trí", value=str(len(player.queue)), inline=True)
                embed.add_field(name="👤 Yêu cầu bởi", value=ctx.author.mention, inline=True)
                await msg.edit(embed=embed)
            else:
                await msg.delete()

    # ── !search ───────────────────────────────────────────────────────────────

    @commands.command(name="search", aliases=["s", "find"])
    async def search_cmd(self, ctx: commands.Context, *, query: str):
        """Tìm kiếm 5 bài nhạc và cho bạn chọn."""
        if not await self.ensure_voice(ctx):
            return

        async with ctx.typing():
            results = await MusicPlayer.search_many(query, count=5, loop=self.bot.loop)

        if not results:
            await ctx.send(embed=err_embed(f"Không tìm thấy kết quả cho: **{query}**"))
            return

        lines = []
        for i, r in enumerate(results, 1):
            title    = r.get("title", "Unknown")[:60]
            uploader = r.get("uploader", "?")
            dur      = int(r.get("duration") or 0)
            m, s     = divmod(dur, 60)
            lines.append(f"`{i}.` **{title}** — {uploader} `{m:02d}:{s:02d}`")

        embed = discord.Embed(
            title=f"🔍 Kết quả tìm kiếm: {query}",
            description="\n".join(lines),
            color=COLOR_BLUE,
        )
        embed.set_footer(text="Nhập số (1-5) để chọn bài, hoặc 'cancel' để huỷ.")
        prompt = await ctx.send(embed=embed)

        def check(m):
            return (
                m.author == ctx.author
                and m.channel == ctx.channel
                and (m.content.lower() == "cancel" or m.content.isdigit())
            )

        try:
            reply = await self.bot.wait_for("message", check=check, timeout=30)
        except asyncio.TimeoutError:
            await prompt.edit(embed=warn_embed("Hết thời gian chờ. Đã huỷ."))
            return

        if reply.content.lower() == "cancel":
            await prompt.edit(embed=warn_embed("Đã huỷ tìm kiếm."))
            return

        idx = int(reply.content) - 1
        if not (0 <= idx < len(results)):
            await prompt.edit(embed=err_embed("Số không hợp lệ."))
            return

        chosen = results[idx]
        entry  = QueueEntry(chosen, requester=ctx.author)
        player = self.get_player(ctx)
        player.enqueue(entry)

        if player.is_playing or player.is_paused:
            embed = discord.Embed(
                title="✅ Đã thêm vào hàng đợi",
                description=f"[{entry.title}]({entry.webpage_url})",
                color=0x1DB954,
            )
            m, s = divmod(entry.duration, 60)
            embed.add_field(name="⏱️ Thời lượng", value=f"{m:02d}:{s:02d}", inline=True)
            embed.add_field(name="📋 Vị trí", value=str(len(player.queue)), inline=True)
            embed.add_field(name="👤 Yêu cầu bởi", value=ctx.author.mention, inline=True)
            await prompt.edit(embed=embed)
        else:
            await prompt.delete()

        try:
            await reply.delete()
        except discord.Forbidden:
            pass

    # ── !pause ───────────────────────────────────────────────────────────────

    @commands.command(name="pause")
    async def pause(self, ctx: commands.Context):
        """Tạm dừng bài đang phát."""
        player = self._players.get(ctx.guild.id)
        if not player or not player.is_playing:
            await ctx.send(embed=warn_embed("Hiện không có bài nào đang phát."))
            return
        player.pause()
        await ctx.send(embed=ok_embed("⏸️ Đã tạm dừng."))

    # ── !resume ──────────────────────────────────────────────────────────────

    @commands.command(name="resume", aliases=["r", "continue"])
    async def resume(self, ctx: commands.Context):
        """Tiếp tục phát nhạc."""
        player = self._players.get(ctx.guild.id)
        if not player or not player.is_paused:
            await ctx.send(embed=warn_embed("Nhạc không bị tạm dừng."))
            return
        player.resume()
        await ctx.send(embed=ok_embed("▶️ Tiếp tục phát."))

    # ── !skip ─────────────────────────────────────────────────────────────────

    @commands.command(name="skip", aliases=["next", "n"])
    async def skip(self, ctx: commands.Context):
        """Bỏ qua bài hiện tại."""
        player = self._players.get(ctx.guild.id)
        if not player or (not player.is_playing and not player.is_paused):
            await ctx.send(embed=warn_embed("Không có gì để bỏ qua."))
            return
        player.skip()
        await ctx.send(embed=ok_embed("⏭️ Đã bỏ qua bài hiện tại."))

    # ── !stop ─────────────────────────────────────────────────────────────────

    @commands.command(name="stop")
    async def stop(self, ctx: commands.Context):
        """Dừng phát nhạc và xóa hàng đợi."""
        vc = ctx.guild.voice_client
        player = self._players.get(ctx.guild.id)
        if player:
            player.clear_queue()
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await ctx.send(embed=ok_embed("⏹️ Đã dừng phát nhạc và xóa hàng đợi."))
        else:
            await ctx.send(embed=warn_embed("Không có gì đang phát."))

    # ── !queue ───────────────────────────────────────────────────────────────

    @commands.command(name="queue", aliases=["q", "list"])
    async def queue_cmd(self, ctx: commands.Context):
        """Hiển thị hàng đợi nhạc."""
        player = self._players.get(ctx.guild.id)

        embed = discord.Embed(title="📋 Hàng đợi nhạc", color=COLOR_BLUE)

        # Bài đang phát
        if player and player.current:
            c = player.current
            m, s = divmod(c.duration, 60)
            embed.add_field(
                name="🎵 Đang phát",
                value=f"[{c.title}]({c.webpage_url}) `{m:02d}:{s:02d}` — {c.requester.mention}",
                inline=False,
            )
        else:
            embed.add_field(name="🎵 Đang phát", value="*(Không có)*", inline=False)

        # Hàng đợi
        if player and player.queue:
            lines = []
            total_sec = 0
            for i, song in enumerate(player.queue[:10], 1):
                m, s = divmod(song.duration, 60)
                lines.append(
                    f"`{i}.` [{song.title[:50]}]({song.webpage_url}) `{m:02d}:{s:02d}`"
                )
                total_sec += song.duration

            if len(player.queue) > 10:
                lines.append(f"... và **{len(player.queue) - 10}** bài nữa.")

            th, tm = divmod(total_sec, 3600)
            tm2, ts = divmod(tm, 60)
            total_str = f"{th}:{tm2:02d}:{ts:02d}" if th else f"{tm2:02d}:{ts:02d}"

            embed.add_field(
                name=f"⏳ Hàng đợi ({len(player.queue)} bài | {total_str})",
                value="\n".join(lines),
                inline=False,
            )
        else:
            embed.add_field(name="⏳ Hàng đợi", value="*(Trống)*", inline=False)

        await ctx.send(embed=embed)

    # ── !nowplaying ──────────────────────────────────────────────────────────

    @commands.command(name="nowplaying", aliases=["np", "current"])
    async def nowplaying(self, ctx: commands.Context):
        """Hiển thị bài đang phát."""
        player = self._players.get(ctx.guild.id)
        if not player or not player.current:
            await ctx.send(embed=warn_embed("Hiện không có bài nào đang phát."))
            return
        await ctx.send(embed=player.current.create_embed("🎵 Đang phát"))

    # ── !volume ──────────────────────────────────────────────────────────────

    @commands.command(name="volume", aliases=["vol", "v"])
    async def volume(self, ctx: commands.Context, vol: int):
        """Chỉnh âm lượng từ 0 đến 100."""
        if not (0 <= vol <= 100):
            await ctx.send(embed=err_embed("Âm lượng phải từ **0** đến **100**."))
            return
        player = self._players.get(ctx.guild.id)
        if not player:
            await ctx.send(embed=warn_embed("Bot chưa vào voice channel."))
            return
        player.set_volume(vol / 100)
        await ctx.send(embed=ok_embed(f"🔊 Âm lượng đặt thành **{vol}%**"))

    # ── !disconnect ──────────────────────────────────────────────────────────

    @commands.command(name="disconnect", aliases=["dc", "leave", "bye"])
    async def disconnect(self, ctx: commands.Context):
        """Bot rời voice channel."""
        vc = ctx.guild.voice_client
        if not vc:
            await ctx.send(embed=warn_embed("Bot không ở trong voice channel nào."))
            return
        self.remove_player(ctx.guild.id)
        await vc.disconnect()
        await ctx.send(embed=ok_embed("👋 Đã rời voice channel. Hẹn gặp lại!"))

    # ── Voice state listener ─────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """Tự rời nếu còn lại một mình trong channel."""
        if member.bot:
            return

        vc = member.guild.voice_client
        if not vc:
            return

        # Nếu channel chỉ còn bot
        if len([m for m in vc.channel.members if not m.bot]) == 0:
            await asyncio.sleep(30)  # Chờ 30s xem có ai quay lại không
            vc2 = member.guild.voice_client
            if vc2 and len([m for m in vc2.channel.members if not m.bot]) == 0:
                self.remove_player(member.guild.id)
                await vc2.disconnect()


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
