# NTUST Course Scraper Bot (台科大課程爬蟲機器人)

這是一個 Discord 機器人，用於監控國立臺灣科技大學 (NTUST) 的課程查詢系統，並在有課程餘額時通知使用者。

## ✨ 功能

- 監控指定課程的剩餘名額。
- 當課程有名額時，自動在指定的 Discord 頻道中 Tag (提及) 追蹤該課程的使用者。
- 支援多個伺服器、多個課程同時追蹤。
- 透過簡單的斜線指令 (`/`) 進行互動。

## 📋 需求

- Python 3.8+
- Playwright 所需的瀏覽器核心

## 🚀 安裝與設定

1.  **複製專案**
    ```bash
    git clone <repository_url>
    cd "NTUST Course Scraper Bot"
    ```

2.  **建立並啟用虛擬環境**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **安裝依賴套件**
    ```bash
    pip install -r requirements.txt
    ```

4.  **安裝 Playwright 瀏覽器**
    ```bash
    playwright install
    ```

5.  **設定環境變數**
    - 將 `.env.example` 檔案複製為 `.env`。
    - 在 `.env` 檔案中填入您的 Discord Bot Token。
    ```env
    TOKEN=YOUR_DISCORD_BOT_TOKEN
    ```

## ▶️ 如何執行

```bash
python main.py
```

## 🤖 使用指令

-   `/add <course_code>`: 新增要追蹤的課程。
-   `/del <course_code>`: 取消追蹤指定的課程。
-   `/list`: 列出目前伺服器所有正在追蹤的課程及追蹤者。
-   `/set_channel`: 將目前的頻道設定為課程通知的頻道。
