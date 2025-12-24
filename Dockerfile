# NTUST Course Scraper Bot - Optimized for Railway Deployment
# Phase 2: Course API (No Playwright required)

FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 設定時區為台北時間
ENV TZ=Asia/Taipei
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 安裝系統依賴（僅必要套件）
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 複製 Python 依賴清單
COPY requirements.txt .

# 安裝 Python 套件
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 複製專案所有檔案
COPY . .

# 設定環境變數
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 啟動機器人
CMD ["python", "main.py"]
