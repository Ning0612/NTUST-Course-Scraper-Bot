# 使用官方 Playwright Python 映像檔 (包含 Python, Playwright 和所有瀏覽器依賴)
# 這能解決在 Debian/Ubuntu slim 版本上手動安裝 Playwright 依賴失敗的問題
FROM mcr.microsoft.com/playwright/python:v1.50.0-jammy

# 設定工作目錄
WORKDIR /app

# 設定時區為台北時間
ENV TZ=Asia/Taipei
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 安裝系統基本依賴 (如果需要)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 複製 Python 依賴清單
COPY requirements.txt .

# 安裝 Python 套件
RUN pip install --no-cache-dir -r requirements.txt

# 官方映像檔通常已內建瀏覽器，但為了保險起見確保安裝 Chromium
# 由於使用官方映像檔，這一步通常會非常快或直接跳過
RUN playwright install chromium

# 複製專案所有檔案
COPY . .

# 設定環境變數
ENV PYTHONUNBUFFERED=1

# 啟動機器人
CMD ["python", "main.py"]
