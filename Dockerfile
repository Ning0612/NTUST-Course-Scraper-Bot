# 使用 Python 3.10 作為基礎映像
FROM python:3.10-slim

# 設定工作目錄
WORKDIR /app

# 設定時區為台北時間 (解決日誌時間問題)
ENV TZ=Asia/Taipei
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 安裝系統基本依賴
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 複製 Python 依賴清單
COPY requirements.txt .

# 安裝 Python 套件
RUN pip install --no-cache-dir -r requirements.txt

# 安裝 Playwright 瀏覽器及其依賴 (僅安裝 Chromium 以節省空間)
RUN playwright install --with-deps chromium

# 複製專案所有檔案
COPY . .

# 設定環境變數，確保 Python 輸出不被緩衝 (即時顯示 Log)
ENV PYTHONUNBUFFERED=1

# 啟動機器人
CMD ["python", "main.py"]
