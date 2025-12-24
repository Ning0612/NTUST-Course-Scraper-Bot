# NTUST Course Scraper Bot（台科大課程追蹤機器人）

一個高效能的 Discord 機器人，用於監控國立台灣科技大學選課系統，當課程出現空位時自動通知使用者。

## ✨ 特色功能

- 🚀 **即時監控**：每 10 秒自動查詢課程剩餘名額
- 📢 **智慧通知**：有空位時自動在 Discord 頻道中標記追蹤者
- 🔄 **並行查詢**：Worker Pool 架構，同時追蹤多門課程
- 💾 **資料持久化**：支援 Railway Volumes，重啟不遺失追蹤資料
- 🌐 **多伺服器**：支援多個 Discord 伺服器同時使用
- ⚡ **輕量高效**：記憶體使用 < 300MB（追蹤 50 門課程）

## 🏗️ 架構特點

### v2.0（當前版本）

- **查詢方式**：NTUST Course API（REST）
- **並行處理**：Worker Pool（5 workers）
- **記憶體使用**：< 300MB
- **查詢速度**：1-2 秒/課程
- **Docker Image**：300MB（python:3.11-slim）

### 相較 v1.0 的改進

| 指標 | v1.0（Playwright） | v2.0（API + Worker Pool） | 改善 |
|------|-------------------|--------------------------|------|
| 記憶體使用 | 5-15 GB | < 300 MB | -95% |
| 查詢速度 | 10-15 秒 | 1-2 秒 | -85% |
| Docker Image | 1.5 GB | 300 MB | -80% |
| 啟動時間 | 20-30 秒 | 5-10 秒 | -70% |

## 📋 系統需求

- **Python**：3.11+
- **Discord Bot Token**：從 [Discord Developer Portal](https://discord.com/developers/applications) 取得
- **部署平台**（擇一）：
  - Railway（推薦）
  - Docker
  - 本地 Python 環境

## 🚀 部署方式

### 方式 1：Railway 部署（推薦，5 分鐘完成）

#### 前置準備
- GitHub 帳號
- Railway 帳號（https://railway.app - 免費註冊）
- Discord Bot Token

#### 部署步驟

**1. Fork 或推送專案到 GitHub**
```bash
# 如果是本地專案，先推送到 GitHub
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/你的帳號/NTUST-Course-Scraper-Bot.git
git push -u origin main
```

**2. 在 Railway 建立專案**
1. 前往 https://railway.app
2. 點擊 **New Project**
3. 選擇 **Deploy from GitHub repo**
4. 授權 Railway 存取 GitHub
5. 選擇 `NTUST-Course-Scraper-Bot` repository

**3. Railway 會自動**
- 偵測 `Dockerfile` 和 `railway.json`
- 開始建置（約 2-3 分鐘）
- 部署完成後等待設定環境變數

**4. 設定環境變數**

在 Railway Dashboard → **Variables** → **Add Variable**：

| 變數名稱 | 必要性 | 範例值 | 說明 |
|---------|--------|--------|------|
| `TOKEN` | ✅ 必要 | `MTI1Mz...` | Discord Bot Token |
| `DEBUG` | 選用 | `False` | 除錯模式（生產環境建議 False） |
| `WORKER_POOL_SIZE` | 選用 | `5` | Worker Pool 大小 |
| `POLLING_INTERVAL` | 選用 | `10` | 查詢間隔（秒） |
| `NOTIFICATION_INTERVAL` | 選用 | `1` | 通知間隔（分鐘） |
| `DATA_FILE` | 選用 | `/app/data/courses.json` | 資料檔案路徑 |

**5. 設定資料持久化（重要！）**

Railway CLI 方式：
```bash
# 安裝 Railway CLI
npm install -g @railway/cli

# 登入
railway login

# 連結專案
railway link

# 建立 Volume
railway volume create course-data --mount /app/data

# 確認環境變數
railway variables set DATA_FILE="/app/data/courses.json"
```

Railway Dashboard 方式：
1. Project Settings → **Volumes**
2. 點擊 **New Volume**
3. 設定：
   - **Name**: `course-data`
   - **Mount Path**: `/app/data`
4. 確認 Variables 中 `DATA_FILE=/app/data/courses.json`

**6. 驗證部署**
```bash
# 查看日誌
railway logs --tail

# 預期輸出：
# ✅ Bot 已啟動：YourBotName
# ✅ Course API Client 已初始化
# ✅ Worker Pool 已啟動 (大小: 5)
```

在 Discord 中測試：
- 確認 Bot 上線（綠燈）
- 執行 `/help`
- 執行 `/add CS1006301`

#### Railway 成本估算

- **Hobby Plan**（$5/月）：適合追蹤 < 50 門課程
- **Pro Plan**（$20/月起）：適合追蹤 100+ 門課程

詳細說明請參考 [RAILWAY-DEPLOY.md](./RAILWAY-DEPLOY.md)

---

### 方式 2：Docker 本地部署

```bash
# 1. 複製專案
git clone <repository_url>
cd NTUST-Course-Scraper-Bot

# 2. 建立 .env 檔案
cp .env.example .env
# 編輯 .env，填入 Discord Bot Token

# 3. 建置 Docker Image
docker build -t ntust-course-bot .

# 4. 執行容器
docker run -d \
  --name ntust-bot \
  --env-file .env \
  -v $(pwd)/courses.json:/app/courses.json \
  ntust-course-bot
```

---

### 方式 3：本地 Python 環境

```bash
# 1. 複製專案
git clone <repository_url>
cd NTUST-Course-Scraper-Bot

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

---

## 📁 專案結構

```
NTUST-Course-Scraper-Bot/
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
├── Dockerfile              # Docker 建置配置
├── railway.json            # Railway 部署配置
└── .env.example            # 環境變數範本
```

---

## 🔧 常見問題

### 1. Bot 啟動後立即停止
**原因**：缺少 `TOKEN` 環境變數
**解決**：確認 Railway Variables 或 `.env` 中已設定 Discord Bot Token

### 2. 課程資料重啟後遺失
**原因**：未配置持久化儲存
**解決**：Railway 需設定 Volume，Docker 需掛載 volume

### 3. 記憶體使用過高
**原因**：Worker Pool 過大
**解決**：調整 `WORKER_POOL_SIZE`（建議 3-10）

### 4. API 查詢失敗
**原因**：查詢頻率過高或 NTUST API 異常
**解決**：增加 `POLLING_INTERVAL` 至 15-20 秒


---

## 🛡️ 安全性注意事項

- ⚠️ **永不提交** `.env` 檔案到 Git（已加入 `.gitignore`）
- ⚠️ 如果 Discord Bot Token 洩漏，立即在 Discord Developer Portal 重設
- ✅ Railway 部署時使用 Dashboard Variables（加密儲存）
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

**版本**：v2.0
**最後更新**：2025-12-25
**部署目標**：Railway（推薦）
**技術架構**：Python 3.11 + discord.py + NTUST Course API + Worker Pool
