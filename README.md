# NTUST Course Tracker Bot（台科大課程追蹤機器人）

一個高效能的 Discord 機器人，用於監控國立台灣科技大學選課系統，當課程出現空位時自動通知使用者。

## ✨ 特色功能

- 🚀 **即時監控**：每 10 秒自動查詢課程剩餘名額
- 📢 **智慧通知**：有空位時自動在 Discord 頻道中標記追蹤者
- 🔄 **並行查詢**：Worker Pool 架構，同時追蹤多門課程
- 📅 **選課期間管理**：自動在選課期間啟動輪詢，結束後清除清單
- 💾 **資料持久化**：追蹤資料儲存至本機檔案，重啟後自動恢復
- 🌐 **多伺服器**：支援多個 Discord 伺服器同時使用
- ⚡ **輕量高效**：記憶體使用 < 300MB（追蹤 50 門課程）

## 🏗️ 架構特點

### v2.0（當前版本）

- **查詢方式**：NTUST Course API（REST）
- **並行處理**：Worker Pool（5 workers）
- **記憶體使用**：< 300MB
- **查詢速度**：1-2 秒/課程

### 相較 v1.0 的改進

| 指標 | v1.0（Playwright） | v2.0（API + Worker Pool） | 改善 |
|------|-------------------|--------------------------|------|
| 記憶體使用 | 5-15 GB | < 300 MB | -95% |
| 查詢速度 | 10-15 秒 | 1-2 秒 | -85% |
| 啟動時間 | 20-30 秒 | 5-10 秒 | -70% |

## 📋 系統需求

- **Python**：3.11+
- **Discord Bot Token**：從 [Discord Developer Portal](https://discord.com/developers/applications) 取得

## 🚀 部署方式

### 方式 1：本地 Python 環境

```bash
# 1. 複製專案
git clone https://github.com/Ning0612/ntust-course-tracker-bot
cd ntust-course-tracker-bot

# 2. 建立虛擬環境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. 安裝依賴
pip install -r requirements.txt

# 4. 設定環境變數
cp .env.example .env
# 編輯 .env，填入 Discord Bot Token

# 5. 執行
python main.py
```

---

## 🤖 使用指令

| 指令 | 參數 | 說明 |
|------|------|------|
| `/add` | `<course_code>` | 新增追蹤課程（例如：`/add CS1006301`） |
| `/del` | `<course_code>` | 取消追蹤指定課程 |
| `/list` | 無 | 列出目前伺服器追蹤的所有課程 |
| `/set_channel` | 無 | 設定當前頻道為通知頻道 |
| `/help` | 無 | 顯示指令說明 |

---

### 必要變數

- `TOKEN`：Discord Bot Token

### 選用變數（有預設值）

- `DEBUG`：除錯模式（`True`/`False`，預設 `False`）
- `WORKER_POOL_SIZE`：並行查詢的 Worker 數量（預設 `5`）
- `POLLING_INTERVAL`：課程查詢間隔秒數（預設 `10`）
- `NOTIFICATION_INTERVAL`：持續通知間隔分鐘數（預設 `1`）
- `DATA_FILE`：資料檔案路徑（預設 `courses.json`）
- `TRACKING_PERIODS`：選課期間設定（格式：`MM-DD~MM-DD`，多組用逗號分隔，例如：`03-17~03-28,09-15~10-05`，留空則永遠輪詢）

---

## 📁 專案結構

```
ntust-course-tracker-bot/
├── main.py                 # 程式入口
├── config/
│   ├── __init__.py
│   └── settings.py         # 配置管理
├── models/
│   ├── __init__.py
│   └── course.py           # 課程資料模型
├── services/
│   ├── __init__.py
│   ├── api_client.py       # NTUST API 封裝
│   ├── tracker.py          # 課程追蹤邏輯
│   ├── worker_pool.py      # Worker Pool 實作
│   ├── notification.py     # 通知服務
│   └── data_manager.py     # 資料持久化
├── bot/
│   ├── __init__.py
│   ├── commands.py         # Discord 斜線指令
│   └── tasks.py            # 定期任務
├── ntust_api/              # NTUST Course API 模組
├── courses.json            # 追蹤課程資料（自動生成）
├── requirements.txt        # Python 依賴
└── .env.example            # 環境變數範本
```

---

## 🔧 常見問題

### 1. Bot 啟動後立即停止
**原因**：缺少 `TOKEN` 環境變數
**解決**：確認 `.env` 中已設定 Discord Bot Token

### 2. 課程資料重啟後遺失
**原因**：資料檔案路徑不在持久化儲存上
**解決**：確認 `DATA_FILE` 指向可寫入且重啟後仍存在的路徑

### 3. 記憶體使用過高
**原因**：Worker Pool 過大
**解決**：調整 `WORKER_POOL_SIZE`（建議 3-10）

### 4. API 查詢失敗
**原因**：查詢頻率過高或 NTUST API 異常
**解決**：增加 `POLLING_INTERVAL` 至 15-20 秒

### 5. 選課期間自動管理
**功能**：設定選課期間後，Bot 僅在期間內啟動課程輪詢；選課結束後自動清除追蹤清單
**設定**：在 `.env` 中設定 `TRACKING_PERIODS=03-17~03-28,09-15~10-05`
**行為說明**：
- 選課前：可加入追蹤清單、可查詢，但不啟動輪詢
- 選課中：完整輪詢與空位通知功能啟用
- 選課結束：自動停止輪詢並清除追蹤清單，發送 Discord 通知
- 支援多組期間（上下學期），跨年期間（如 `12-01~03-01`）亦正確支援

---

## 🛡️ 安全性注意事項

- ⚠️ **永不提交** `.env` 檔案到 Git（已加入 `.gitignore`）
- ⚠️ 如果 Discord Bot Token 洩漏，立即在 Discord Developer Portal 重設
- ✅ 部署時使用環境變數管理敏感資訊（勿寫入程式碼）
- ✅ 定期更換 Discord Bot Token

---

## 📊 效能監控

追蹤 50 門課程的預期表現：

- **記憶體使用**：200-300 MB
- **查詢週期**：每 10 秒一輪（可調整）
- **API 呼叫**：每小時 ~360 次
- **網路流量**：每天 ~4-5 GB

---

## 📄 授權

本專案僅供學術研究與個人使用，請勿用於商業用途。

---

**版本**：v2.1
**最後更新**：2026-03-28
**部署目標**：GCP
**技術架構**：Python 3.11 + discord.py + NTUST Course API + Worker Pool
