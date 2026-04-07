FROM python:3.10-slim

# Cài đặt FFmpeg (Bắt buộc để bot có thể phát nhạc)
RUN apt-get update && \
    apt-get install -y ffmpeg curl build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy thư viện và cài đặt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ mã nguồn bot vào Container
COPY . .

# Khởi chạy Bot
CMD ["python", "bot.py"]
