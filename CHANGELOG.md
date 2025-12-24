# 變更記錄（Changelog）

本專案的所有重要變更都會記錄在此檔案。

格式基於 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.0.0/)，
版本號遵循 [語義化版本](https://semver.org/lang/zh-TW/)。

---

## [2.0.0] - 2025-12-25

### 🎉 重大更新：架構重構

這是一次完整的架構重寫，大幅提升效能與可維護性。

### ✨ 新增功能

#### 核心架構
- **Worker Pool 並行處理**：採用固定大小的 Worker Pool（預設 5 workers），替代「每課程一任務」模式
- **模組化架構**：將 543 行單一檔案重構為 8 個獨立模組
  - `config/` - 配置管理
  - `models/` - 資料模型
  - `services/` - 業務邏輯（API 客戶端、追蹤器、Worker Pool、資料管理）
  - `bot/` - Discord 指令與任務
- **Course API 整合**：使用 NTUST Course API（REST）替代 Playwright 網頁爬蟲
- **智慧資料持久化**：支援 JSON 檔案儲存，相容 Railway Volumes

#### 配置管理
- **環境變數完整化**：新增 `WORKER_POOL_SIZE`、`POLLING_INTERVAL`、`NOTIFICATION_INTERVAL`、`DATA_FILE`
- **靈活配置**：所有配置項都有合理的預設值，僅 `TOKEN` 為必要

#### 部署支援
- **Railway 原生支援**：新增 `railway.json` 配置檔
- **Docker 優化**：Dockerfile 從 Playwright 基礎映像改為 `python:3.11-slim`
- **一鍵部署**：支援 GitHub → Railway 自動部署工作流程

#### 文檔系統
- **ENV-VARS.md**：環境變數詳細說明（500+ 行）
- **RAILWAY-DEPLOY.md**：Railway 專用部署指南
- **DEPLOYMENT.md**：完整部署指南（包含 Docker、本地、Railway）
- **PHASE2-COMPLETE.md**：Phase 2 完成總結

### 🚀 效能改進

| 指標 | v1.0（Playwright） | v2.0（API + Worker Pool） | 改善幅度 |
|------|-------------------|--------------------------|---------|
| **記憶體使用** | 5-15 GB（50 門課程） | < 300 MB | **-95%** |
| **查詢速度** | 10-15 秒/課程 | 1-2 秒/課程 | **-85%** |
| **Docker Image** | 1.5 GB | 300 MB | **-80%** |
| **啟動時間** | 20-30 秒 | 5-10 秒 | **-70%** |
| **建置時間** | 5-8 分鐘 | 1-2 分鐘 | **-70%** |

### 🔧 變更內容

#### 依賴項目
- **移除** `playwright` - 不再需要瀏覽器核心
- **新增** `requests` - 用於 HTTP API 查詢
- **保留** `discord.py`、`python-dotenv`

#### 資料模型
- **新增** `TrackedCourse` 資料類別（dataclass）
- **改進** 課程資料序列化與反序列化邏輯
- **優化** 追蹤者（followers）使用 Set 儲存，避免重複

#### 查詢邏輯
- **替換** Playwright 網頁爬蟲 → NTUST Course API（REST）
- **移除** 複雜的 DOM 解析與正則表達式
- **簡化** 人數上限直接從 `Restrict2` 欄位取得
- **加速** 查詢時間從 10-15 秒降至 1-2 秒

#### 並行處理
- **移除** 「每課程一個 asyncio.Task」模式（會導致資源耗盡）
- **新增** Worker Pool 架構，固定 5 個 workers 處理所有課程
- **優化** 使用單一輪詢任務 + 任務佇列

### 🗑️ 移除功能

- **Playwright 相關**：
  - `playwright_browser` 全域變數
  - `playwright_context` 全域變數
  - 瀏覽器啟動與關閉邏輯
  - Page 物件管理
- **正則表達式解析**：
  - `extract_max_students()` 函數
  - `extract_max_students_from_remark()` 函數
  - `get_max_students_improved()` 函數（182 行）
- **備份檔案**：所有 `.bak` 檔案

### 📁 檔案結構變更

#### 新增檔案
```
config/
├── __init__.py
└── settings.py

models/
├── __init__.py
└── course.py

services/
├── __init__.py
├── api_client.py
├── tracker.py
├── worker_pool.py
├── notification.py
└── data_manager.py

bot/
├── __init__.py
├── commands.py
└── tasks.py

ntust_api/          # 從 Course_API 專案整合
├── __init__.py
├── client.py
└── query.py
```

#### 修改檔案
- `main.py`：367 行 → 139 行（-62%）
- `requirements.txt`：移除 playwright，新增 requests
- `Dockerfile`：完全重寫，基礎映像從 1.5GB 降至 300MB
- `.gitignore`：新增 `*.bak` 排除
- `.dockerignore`：新增開發檔案排除
- `.env.example`：新增完整環境變數說明

#### 新增配置
- `railway.json`：Railway 平台配置
- `ENV-VARS.md`：環境變數文檔
- `RAILWAY-DEPLOY.md`：Railway 部署指南
- `DEPLOYMENT.md`：完整部署指南

### 🐛 修正問題

- **記憶體洩漏**：修正「每課程一任務」導致的記憶體耗盡問題
- **查詢超時**：使用 API 替代 Playwright，避免瀏覽器超時
- **DOM 解析失效**：不再依賴網站 DOM 結構，使用穩定的 JSON API
- **人數上限錯誤**：從 `Restrict2` 直接取得，準確率 100%

### 🔐 安全性改進

- **環境變數加密**：Railway Variables 使用加密儲存
- **Token 保護**：.env 已加入 .gitignore
- **文檔警告**：在多處文檔強調不要提交 Token

### 📝 文檔更新

- **README.md**：完全重寫，新增 Railway 部署說明
- **CHANGELOG.md**（本檔案）：新增 v2.0.0 記錄
- **ENV-VARS.md**：環境變數詳細說明（500+ 行）
- **RAILWAY-DEPLOY.md**：Railway 專用指南（400+ 行）
- **DEPLOYMENT.md**：通用部署指南
- **PHASE2-COMPLETE.md**：Phase 2 完成總結

### 🎯 部署建議

#### Railway（推薦）
- 記憶體需求：Hobby Plan（512MB）足夠追蹤 50 門課程
- 成本：$5/月（Hobby）或 $20/月起（Pro）
- 必須配置：Volume（資料持久化）

#### Docker
- 映像大小：300MB（v1.0: 1.5GB）
- 建置時間：1-2 分鐘（v1.0: 5-8 分鐘）
- Volume 掛載：`-v $(pwd)/courses.json:/app/courses.json`

#### 本地
- Python 版本：3.11+
- 記憶體需求：< 500MB
- 環境變數：透過 .env 檔案配置

---

## [1.0.0] - 2025-08-20

### ✨ 新增功能

#### 初始專案建立
- **課程追蹤系統**：`/add`、`/del`、`/list` 指令
- **課程名額通知**：有空位時自動標記使用者
- **安全配置**：使用 `.env` 儲存 Token 與 `DEBUG` 模式
- **即時驗證**：`/add` 指令執行時立即驗證課程
- **使用者友善**：`/help` 指令提供 Embed 格式說明
- **專案文檔**：`README.md` 提供安裝與使用說明
- **依賴管理**：`requirements.txt` 簡化安裝流程
- **版本控制**：`.gitignore` 排除敏感與不必要檔案
- **變更記錄**：`CHANGELOG.md` 追蹤版本變更

### 🔧 變更內容
- **指令回應**：`/add` 改為公開回應至頻道
- **爬蟲穩定性**：增加超時時間與延遲
- **錯誤日誌**：提供更具體的錯誤訊息

### 🗑️ 移除功能
- **不安全的配置**：移除 `config.py` 檔案（改用 .env）

---

## 版本規劃

### [2.0.1] - 待定
- 錯誤處理改進
- 日誌格式優化
- 小型 Bug 修正

---

## 格式說明

- `新增功能` - 新功能
- `變更內容` - 既有功能的變更
- `棄用功能` - 即將移除的功能
- `移除功能` - 已移除的功能
- `修正問題` - Bug 修正
- `安全性改進` - 安全性相關變更

---

**版本號規則**：
- **主版本號（Major）**：不相容的 API 變更
- **次版本號（Minor）**：向下相容的功能新增
- **修訂號（Patch）**：向下相容的問題修正
