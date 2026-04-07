# 🎵 Discord Music Bot

Bot Discord hỗ trợ tìm kiếm và phát nhạc từ YouTube, với hàng đợi thông minh và giao diện đẹp.

---

## ✨ Tính năng

- 🔍 Tìm kiếm nhạc theo từ khóa hoặc URL YouTube
- 📋 Hàng đợi nhạc với nhiều bài
- ⏸️ Pause / Resume / Skip / Stop
- 🔊 Chỉnh âm lượng
- 🎨 Embed đẹp có thumbnail, thời lượng, tên kênh
- 👤 Tự rời kênh khi không có ai / hết nhạc

---

## ⚙️ Yêu cầu hệ thống

- **Python 3.10+**
- **FFmpeg** (bắt buộc phải có trong PATH)
  - Windows: Tải tại https://www.gyan.dev/ffmpeg/builds/ → giải nén → thêm vào PATH
  - Kiểm tra: `ffmpeg -version`

---

## 🚀 Cài đặt

### 1. Cài dependencies

```bash
pip install -r requirements.txt
```

### 2. Tạo file `.env`

```bash
copy .env.example .env
```

Mở file `.env` và điền Discord Bot Token của bạn:

```env
DISCORD_TOKEN=your_discord_bot_token_here
PREFIX=!
IDLE_TIMEOUT=300
```

> 💡 Lấy token tại: https://discord.com/developers/applications  
> Bật Privileged Gateway Intents: **Message Content Intent** và **Server Members Intent**

### 3. Chạy bot

```bash
python bot.py
```

---

## 📖 Danh sách lệnh

| Lệnh | Alias | Mô tả |
|------|-------|-------|
| `!play <tên/URL>` | `!p` | Phát nhạc hoặc thêm vào hàng đợi |
| `!search <từ khóa>` | `!s`, `!find` | Tìm 5 bài, chọn bằng số |
| `!pause` | — | Tạm dừng |
| `!resume` | `!r` | Tiếp tục phát |
| `!skip` | `!next`, `!n` | Bỏ qua bài hiện tại |
| `!stop` | — | Dừng và xóa hàng đợi |
| `!queue` | `!q`, `!list` | Xem hàng đợi |
| `!nowplaying` | `!np`, `!current` | Bài đang phát |
| `!volume <0-100>` | `!vol`, `!v` | Chỉnh âm lượng |
| `!disconnect` | `!dc`, `!leave`, `!bye` | Rời voice channel |
| `!help` | `!h` | Hiển thị trợ giúp |

---

## 🔧 Cấu hình Bot trên Discord Developer Portal

1. Vào https://discord.com/developers/applications
2. Tạo Application mới → Bot
3. Bật các Privileged Intents:
   - ✅ PRESENCE INTENT
   - ✅ SERVER MEMBERS INTENT
   - ✅ MESSAGE CONTENT INTENT
4. Copy Token → paste vào `.env`
5. OAuth2 → URL Generator → chọn `bot` scope
6. Chọn permissions: `Send Messages`, `Connect`, `Speak`, `Read Message History`
7. Dùng URL được tạo để mời bot vào server

---

## 📁 Cấu trúc thư mục

```
BOT/
├── bot.py               # Entry point
├── cogs/
│   └── music.py         # Lệnh nhạc
├── utils/
│   └── music_player.py  # Logic phát nhạc & yt-dlp
├── .env                 # Token (KHÔNG commit lên git)
├── .env.example
├── requirements.txt
└── README.md
```
