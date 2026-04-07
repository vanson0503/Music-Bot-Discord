import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio

# --- LOGIC ĐOÁN SỐ ---
# --- LOGIC TIKTOK TREND ĐỘNG ---
class DynamicTrendView(discord.ui.View):
    def __init__(self, ctx, answer_idx, options):
        super().__init__(timeout=45.0)
        self.ctx = ctx
        self.answer_idx = answer_idx
        self.options = options

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("❌ Người khác đang chơi mà, bạn đừng bấm ké!", ephemeral=True)
            return False
        return True

    async def check_answer(self, interaction: discord.Interaction, btn_idx: int):
        for child in self.children:
            child.disabled = True
            
        is_correct = (btn_idx == self.answer_idx)
        embed = interaction.message.embeds[0]
        
        if is_correct:
            embed.color = 0x2ECC71
            embed.title = "✅ CHÍNH XÁC!"
            embed.description = f"Quá đỉnh! **{self.options[btn_idx]}** chính là nguồn gốc của bức ảnh này. Bạn đích thực là chiến thần Tóp Tóp!"
        else:
            embed.color = 0xE74C3C
            embed.title = "❌ SAI RỒI!"
            embed.description = f"Bạn chọn: **{self.options[btn_idx]}**\nĐáp án chuẩn phải là: **{self.options[self.answer_idx]}**."

        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="A", style=discord.ButtonStyle.primary)
    async def btn_a(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.check_answer(interaction, 0)
    @discord.ui.button(label="B", style=discord.ButtonStyle.primary)
    async def btn_b(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.check_answer(interaction, 1)
    @discord.ui.button(label="C", style=discord.ButtonStyle.primary)
    async def btn_c(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.check_answer(interaction, 2)
    @discord.ui.button(label="D", style=discord.ButtonStyle.primary)
    async def btn_d(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.check_answer(interaction, 3)

async def start_dynamic_trend_logic(bot, ctx):
    msg = await ctx.send("🕵️ **Cán bộ Tóp Tóp** đang đi moi móc dữ liệu trend rần rần... Chờ mị chút nhé!")
    
    loop = asyncio.get_event_loop()
    def fetch_trends():
        import yt_dlp
        opts = {'extract_flat': True, 'quiet': True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            # Tìm kiếm các clip short hoặc video meme có tính giải trí cao
            info = ydl.extract_info("ytsearch30:tiktok meme việt nam hài hước", download=False)
            return info.get('entries', [])

    try:
        entries = await loop.run_in_executor(None, fetch_trends)
    except Exception as e:
        return await msg.edit(content=f"❌ Úi dồi ôi, lỗi cáp tới Tóp Tóp rồi: {e}")
        
    if not entries or len(entries) < 4:
        return await msg.edit(content="❌ Không đủ muối để tạo câu hỏi cho bạn. Thử lại sau nhé!")
        
    import random
    random.shuffle(entries)
    
    correct_video = entries[0]
    
    # 3 Trap mồi nhử từ các video khác nhưng được tẩm thêm muối
    trap_videos = entries[1:4]
    options_data = [correct_video] + trap_videos
    random.shuffle(options_data)
    correct_idx = options_data.index(correct_video)
    
    thumbnail = ""
    if correct_video.get("thumbnails"):
        thumbnail = correct_video["thumbnails"][-1].get("url", "")
    elif correct_video.get("url"):
        vid = correct_video["url"].split("v=")[-1]
        thumbnail = f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"

    def clean_title(t):
        import re
        t = re.sub(r'(?i)#\w+', '', t) # Xoá hashtag
        t = re.sub(r'\[.*?\]|\(.*?\)', '', t) # Xoá ngoặc [TikTok]
        t = t.replace("TikTok", "").replace("Trend", "").replace("Meme", "").replace("|", "-")
        t = t.strip()
        
        # Chỉ viết hoa chữ cái đầu cho giống kiểu cap meme
        if t:
            t = t[0].upper() + t[1:].lower()
            
        if len(t) > 45: 
            t = t[:42] + "..."
            
        # Tẩm thêm emoji lầy lội vào cuối
        emojis = [" 🤣", " 💀", " 🤡", " 🤪", " 👀", " 🤫", " 🐧", " 🚩", " 🦆", " 🐸"]
        return t + random.choice(emojis)
        
    opts_clean = [clean_title(v.get('title', 'Video tấu hài không tên')) for v in options_data]
    
    view = DynamicTrendView(ctx, correct_idx, opts_clean)
    
    embed = discord.Embed(
        title="🕵️ Lệnh Truy Nã: Nguồn Gốc Bức Ảnh Này?", 
        description=(
            f"Vụ án mạng cười sảng đã xảy ra từ chiếc video có Thumbnail bên dưới.\n"
            f"Theo linh cảm của một **Báo thủ**, tiêu đề video này là gì?\n\n"
            f"**A.** 👉 {opts_clean[0]}\n"
            f"**B.** 👉 {opts_clean[1]}\n"
            f"**C.** 👉 {opts_clean[2]}\n"
            f"**D.** 👉 {opts_clean[3]}\n"
        ),
        color=0xFF0050
    )
    if thumbnail:
        embed.set_image(url=thumbnail)
        
    await msg.edit(content="", embed=embed, view=view)

async def start_guess_logic(bot, ctx, number):
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()

    tries = 0
    max_tries = 5
    while tries < max_tries:
        try:
            msg = await bot.wait_for("message", check=check, timeout=30.0)
        except asyncio.TimeoutError:
            return await ctx.send(f"⌛ Hết thời gian! Bạn đã không đoán số kịp. Số đúng là **{number}**.")
        
        guess = int(msg.content)
        tries += 1

        if guess == number:
            return await ctx.send(f"🎉 BINGO {ctx.author.mention}! Bạn đã đoán đúng số **{number}** sau {tries} lượt!")
        elif guess < number:
            await ctx.send(f"📈 Lượt {tries}/{max_tries}: Số bạn đoán hơi **NHỎ**!")
        else:
            await ctx.send(f"📉 Lượt {tries}/{max_tries}: Số bạn đoán hơi **LỚN**!")

    await ctx.send(f"💀 Bạn đã hết {max_tries} lượt! Số đúng mà bot chọn là **{number}**.")

# --- LOGIC ĐOÁN CHỮ (SCRAMBLE) ---
async def start_scramble_logic(bot, ctx):
    words = ["vietnam", "discord", "python", "javascript", "developer", "internet", "computer", "keyboard", "gaming"]
    word = random.choice(words)
    scrambled = "".join(random.sample(word, len(word)))
    
    embed = discord.Embed(
        title="🔠 Trò chơi Đoán Chữ (Word Scramble)", 
        description=f"Từ tiếng Anh bí ẩn đã bị xáo trộn: **` {scrambled} `**\n\n👉 Bạn có **30 giây** để giải mã và gõ từ đúng vào chat!", 
        color=0xE67E22
    )
    await ctx.send(embed=embed)
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    try:
        msg = await bot.wait_for("message", check=check, timeout=30.0)
    except asyncio.TimeoutError:
        return await ctx.send(f"⌛ Hết giờ! Chịu thua à? Từ đúng là: **{word}**")
        
    if msg.content.lower() == word:
         await ctx.send(f"🎉 Rất thông minh {ctx.author.mention}! Bạn đã giải mã đúng từ **{word}**!")
    else:
         await ctx.send(f"💀 Sai rồi! Rất tiếc, từ đúng phải là: **{word}**.")

# --- LOGIC TIC TAC TOE ---
class TicTacToeButton(discord.ui.Button):
    def __init__(self, x, y):
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=y)
        self.x = x
        self.y = y

    async def callback(self, interaction: discord.Interaction):
        view = getattr(self, 'view', None)
        if not view: return
        
        if interaction.user != view.player:
            return await interaction.response.send_message("❌ Xin lỗi, người khác đang chơi ván này!", ephemeral=True)
            
        # Nước đi của người chơi (X)
        self.style = discord.ButtonStyle.success
        self.label = "X"
        self.disabled = True
        view.board[self.y][self.x] = view.X
        
        if view.check_win(view.X):
            view.disable_all()
            embed = discord.Embed(title="❌⭕ Cờ Caro", description="🎉 Chúc mừng bạn đã **THẮNG** trận này!", color=0x2ECC71)
            return await interaction.response.edit_message(embed=embed, view=view)
        if view.is_tie():
            view.disable_all()
            embed = discord.Embed(title="❌⭕ Cờ Caro", description="🤝 Trận đấu hòa!", color=0x95A5A6)
            return await interaction.response.edit_message(embed=embed, view=view)
            
        # Nước đi của Bot (O) rải ngẫu nhiên
        empty_buttons = [child for child in view.children if getattr(child, "disabled", False) is False]
        if empty_buttons:
            bot_move = random.choice(empty_buttons)
            bot_move.style = discord.ButtonStyle.danger
            bot_move.label = "O"
            bot_move.disabled = True
            view.board[bot_move.y][bot_move.x] = view.O

        if view.check_win(view.O):
            view.disable_all()
            embed = discord.Embed(title="❌⭕ Cờ Caro", description="💀 Bot đã **THẮNG**, bạn còn non lắm!", color=0xE74C3C)
            return await interaction.response.edit_message(embed=embed, view=view)
        if view.is_tie():
            view.disable_all()
            embed = discord.Embed(title="❌⭕ Cờ Caro", description="🤝 Trận đấu hòa!", color=0x95A5A6)
            return await interaction.response.edit_message(embed=embed, view=view)

        await interaction.response.edit_message(view=view)

class TicTacToeView(discord.ui.View):
    X = -1
    O = 1

    def __init__(self, player):
        super().__init__(timeout=60.0)
        self.player = player
        self.board = [[0, 0, 0] for _ in range(3)]
        for y in range(3):
            for x in range(3):
                self.add_item(TicTacToeButton(x, y))

    def check_win(self, mark):
        b = self.board
        for i in range(3):
            if b[i][0] == b[i][1] == b[i][2] == mark: return True
            if b[0][i] == b[1][i] == b[2][i] == mark: return True
        if b[0][0] == b[1][1] == b[2][2] == mark: return True
        if b[0][2] == b[1][1] == b[2][0] == mark: return True
        return False
        
    def is_tie(self):
        return all(self.board[y][x] != 0 for y in range(3) for x in range(3))

    def disable_all(self):
        for child in self.children:
            child.disabled = True


# --- LOGIC OẲN TÙ TÌ ---
class RPSView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=30.0)
        self.ctx = ctx

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("❌ Đây không phải trò chơi do bạn tạo!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Búa", emoji="🪨", style=discord.ButtonStyle.primary)
    async def rock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play_rps(interaction, "Búa")

    @discord.ui.button(label="Bao", emoji="📄", style=discord.ButtonStyle.primary)
    async def paper(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play_rps(interaction, "Bao")

    @discord.ui.button(label="Kéo", emoji="✂️", style=discord.ButtonStyle.primary)
    async def scissors(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play_rps(interaction, "Kéo")

    async def play_rps(self, interaction: discord.Interaction, user_choice: str):
        bot_choice = random.choice(["Búa", "Bao", "Kéo"])
        win_conditions = {"Búa": "Kéo", "Bao": "Búa", "Kéo": "Bao"}
        
        if user_choice == bot_choice:
            result = "🤝 Hòa nhau! Không ai thua."
            color = 0x95A5A6
        elif win_conditions[user_choice] == bot_choice:
            result = "🎉 Chúc mừng bạn đã Thắng!"
            color = 0x2ECC71
        else:
            result = "💀 Thua rồi! Bot quá thông minh."
            color = 0xE74C3C
            
        for child in self.children:
            child.disabled = True

        embed = discord.Embed(title="✂️ Kết quả Oẳn Tù Tì", color=color)
        embed.add_field(name="Bạn ra", value=f"**{user_choice}**", inline=True)
        embed.add_field(name="Bot ra", value=f"**{bot_choice}**", inline=True)
        embed.add_field(name="Kết cuộc", value=result, inline=False)
        
        await interaction.response.edit_message(embed=embed, view=self)


# --- MENU CHỌN GAME CHUNG ---
class GameSelect(discord.ui.Select):
    def __init__(self, bot, ctx):
        self.bot = bot
        self.ctx = ctx
        options = [
            discord.SelectOption(label="Đoán Trend TikTok", description="Thử tài hiểu biết TikTok VN", emoji="📱", value="trend"),
            discord.SelectOption(label="Cờ Caro (Tic Tac Toe)", description="Quyết đấu 3x3 với Bot", emoji="❌", value="tictactoe"),
            discord.SelectOption(label="Đoán Chữ (Scramble)", description="Ghép từ nhanh", emoji="🔠", value="scramble"),
            discord.SelectOption(label="Oẳn Tù Tì", description="Đấu trí RPS với bot", emoji="✂️", value="rps"),
            discord.SelectOption(label="Tung Đồng Xu", description="Thử vận may 50/50", emoji="🪙", value="coin"),
            discord.SelectOption(label="Đoán Số", description="Đoán số từ 1 đến 100", emoji="🔢", value="guess"),
        ]
        super().__init__(placeholder="Chọn một trò chơi để bắt đầu...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("❌ Bạn không phải là người gọi lệnh này!", ephemeral=True)

        game = self.values[0]
        if game == "rps":
            view = RPSView(self.ctx)
            embed = discord.Embed(title="✂️ Oẳn Tù Tì", description="Hãy chọn Búa, Bao, hoặc Kéo ở dưới!", color=0x5865F2)
            await interaction.response.edit_message(embed=embed, view=view)
            
        elif game == "coin":
            result = random.choice(["Ngửa (Heads)", "Sấp (Tails)"])
            color = 0xF1C40F if "Ngửa" in result else 0x95A5A6
            embed = discord.Embed(title="🪙 Tung Đồng Xu", description=f"Đồng xu lắc lắc và rơi xuống... **{result}**!", color=color)
            await interaction.response.edit_message(embed=embed, view=None)
            
        elif game == "guess":
            number = random.randint(1, 100)
            embed = discord.Embed(
                title="🔢 Trò chơi Đoán Số", 
                description="Bot đã gieo một số ngẫu nhiên từ **1 đến 100**.\nBạn có **5 lượt** để đoán!\n\n👉 **Hãy nhập số bạn đoán vào kênh chat nhé.**", 
                color=0x2ECC71
            )
            await interaction.response.edit_message(embed=embed, view=None)
            await start_guess_logic(self.bot, self.ctx, number)
            
        elif game == "scramble":
            await interaction.response.defer()
            await interaction.delete_original_response()
            await start_scramble_logic(self.bot, self.ctx)
            
        elif game == "trend":
            await interaction.response.defer()
            await interaction.delete_original_response()
            await start_dynamic_trend_logic(self.bot, self.ctx)
            
        elif game == "tictactoe":
            view = TicTacToeView(self.ctx.author)
            embed = discord.Embed(
                title="❌⭕ Cờ Caro", 
                description="Lượt của bạn! Bạn là dấu **X**.\nHãy bấm vào ô trống bên dưới để đánh.", 
                color=0x3498DB
            )
            await interaction.response.edit_message(embed=embed, view=view)


class GameMenu(discord.ui.View):
    def __init__(self, bot, ctx):
        super().__init__(timeout=60.0)
        self.add_item(GameSelect(bot, ctx))


# --- COMMAND TỔNG QUÁT ---
class Games(commands.Cog):
    """🎮 Cog chứa các trò chơi nhỏ (Minigames) xịn xò."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="game", aliases=["games", "playgame", "minigame"], description="Mở menu hoặc chọn ngay Minigame để chơi.")
    @app_commands.describe(ten_game="Chọn trò chơi bạn muốn chơi (Tùy chọn)")
    @app_commands.choices(ten_game=[
        app_commands.Choice(name="Đoán Trend TikTok", value="trend"),
        app_commands.Choice(name="Cờ Caro (Tic Tac Toe)", value="tictactoe"),
        app_commands.Choice(name="Đoán Chữ (Scramble)", value="scramble"),
        app_commands.Choice(name="Oẳn Tù Tì", value="rps"),
        app_commands.Choice(name="Tung Đồng Xu", value="coin"),
        app_commands.Choice(name="Đoán Số", value="guess"),
    ])
    async def game_cmd(self, ctx: commands.Context, ten_game: str = None):
        """Mở menu chọn Minigame."""
        if not ten_game:
            view = GameMenu(self.bot, ctx)
            embed = discord.Embed(
                title="🎮 Trung Tâm Minigame",
                description="Chào mừng bạn đến với khu Game. Hãy làm vài ván giải trí nhé!\n\n👇 Vui lòng bấm vào Menu bên dưới để chọn trò chơi:",
                color=0x9B59B6
            )
            embed.set_footer(text=f"Yêu cầu bởi {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed, view=view)
        else:
            val = ten_game
            if val == "rps":
                view = RPSView(ctx)
                embed = discord.Embed(title="✂️ Oẳn Tù Tì", description="Hãy chọn Búa, Bao, hoặc Kéo ở dưới!", color=0x5865F2)
                await ctx.send(embed=embed, view=view)
            elif val == "coin":
                result = random.choice(["Ngửa (Heads)", "Sấp (Tails)"])
                color = 0xF1C40F if "Ngửa" in result else 0x95A5A6
                embed = discord.Embed(title="🪙 Tung Đồng Xu", description=f"Đồng xu lắc lắc và rơi xuống... **{result}**!", color=color)
                await ctx.send(embed=embed)
            elif val == "guess":
                number = random.randint(1, 100)
                embed = discord.Embed(
                    title="🔢 Trò chơi Đoán Số", 
                    description="Bot đã gieo một số ngẫu nhiên từ **1 đến 100**.\nBạn có **5 lượt** để đoán!\n\n👉 **Hãy nhập số bạn đoán vào kênh chat nhé.**", 
                    color=0x2ECC71
                )
                await ctx.send(embed=embed)
                await start_guess_logic(self.bot, ctx, number)
            elif val == "scramble":
                await start_scramble_logic(self.bot, ctx)
            elif val == "trend":
                await start_dynamic_trend_logic(self.bot, ctx)
            elif val == "tictactoe":
                view = TicTacToeView(ctx.author)
                embed = discord.Embed(
                    title="❌⭕ Cờ Caro", 
                    description="Lượt của bạn! Bạn chơi cờ **X**.\nHãy bấm vào ô trống để đánh nhé.", 
                    color=0x3498DB
                )
                await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Games(bot))
