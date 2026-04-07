import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
import logging

# ─── Logging setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("MusicBot")

# ─── Load biến môi trường ─────────────────────────────────────────────────────
load_dotenv()
TOKEN  = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("PREFIX", "!")

if not TOKEN:
    log.critical("❌  Không tìm thấy DISCORD_TOKEN trong file .env!")
    raise SystemExit(1)

# ─── Intents ─────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states     = True

# ─── Bot ─────────────────────────────────────────────────────────────────────
class MusicBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=PREFIX,
            intents=intents,
            help_command=None,          # Tắt help mặc định, dùng help custom
            case_insensitive=True,
        )

    async def setup_hook(self):
        await self.load_extension("cogs.music")
        log.info("✅  Đã load cog: music")
        await self.load_extension("cogs.games")
        log.info("✅  Đã load cog: games")
        
        try:
            synced = await self.tree.sync()
            log.info(f"✅  Đã đồng bộ {len(synced)} Slash Commands")
        except Exception as e:
            log.error(f"❌  Lỗi đồng bộ lệnh: {e}")

    async def on_ready(self):
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name=f"{PREFIX}play | {PREFIX}help",
        )
        await self.change_presence(activity=activity)
        log.info(f"🎵  Bot đã online: {self.user} (ID: {self.user.id})")
        log.info(f"📡  Kết nối tới {len(self.guilds)} server(s)")

    async def on_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                embed=discord.Embed(
                    description=f"⚠️  Thiếu tham số. Dùng `{PREFIX}help` để xem hướng dẫn.",
                    color=0xFFAA00,
                )
            )
            return
        log.error(f"Lỗi lệnh '{ctx.command}': {error}", exc_info=error)

# ─── Main ─────────────────────────────────────────────────────────────────────
async def main():
    async with MusicBot() as bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
