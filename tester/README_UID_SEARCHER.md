# UID Searcher 使用說明

## 簡介

`uid_searcher` 是一個 C 程式工具，用於模擬從本機連接的設備讀取 UID 並自動傳送至後端系統。當前端點擊「搜尋」按鈕後，執行此程式可將 UID 自動填入前端 UI。

## 編譯

### 方法 1：使用 Makefile（推薦）

```bash
cd tester
make uid_searcher
```

### 方法 2：使用 gcc

```bash
# macOS（使用 Homebrew curl）
gcc -O2 -Wall -I$(brew --prefix curl)/include -L$(brew --prefix curl)/lib \
    -o uid_searcher uid_searcher.c -lcurl

# Linux 或系統內建 curl
gcc -O2 -Wall -o uid_searcher uid_searcher.c -lcurl
```

## 使用方式

### 基本用法

```bash
# 自動產生隨機 UID 並傳送（模擬搜尋延遲 1-2 秒）
./uid_searcher

# 傳送指定的 UID
./uid_searcher NL-20251204-0001
```

### 使用 Makefile 快捷指令

```bash
make run_searcher
```

## 完整測試流程

### 1. 啟動後端服務

確保後端服務在 `http://localhost:8000` 運行：

```bash
cd backend
docker-compose up -d
# 或
uvicorn app.main:app --reload
```

### 2. 啟動前端（frontend-nl）

```bash
cd frontend-nl
npm start
```

前端會在 `http://localhost:3001` 啟動。

### 3. 執行 UID 搜尋流程

1. **前端操作**：
   - 開啟瀏覽器進入 `http://localhost:3001`
   - 點選「PCBA進料檢驗」頁面
   - 點擊「搜尋」按鈕（前端會顯示「正在搜尋 UID...」）

2. **執行 uid_searcher**：
   
   ```bash
   cd tester
   ./uid_searcher
   ```
   
   或使用指定 UID：
   
   ```bash
   ./uid_searcher NL-20251204-9999
   ```

3. **結果確認**：
   - `uid_searcher` 終端會顯示傳送成功訊息
   - 前端 UID 欄位會自動填入接收到的 UID
   - 序號欄位也會同步更新為相同的 UID
   - 前端會顯示「UID 已接收: NL-xxxx-xxxx」訊息

### 4. 開始測試

UID 填入後，點擊「開始測試」按鈕即可啟動測試流程（維持原有測試邏輯）。

## 工作原理

```
┌──────────┐         ┌──────────┐         ┌──────────┐
│ 前端     │         │ 後端     │         │ uid_     │
│ (React)  │         │ (FastAPI)│         │ searcher │
└────┬─────┘         └────┬─────┘         └────┬─────┘
     │                    │                     │
     │ 1. 點擊「搜尋」    │                     │
     ├───────────────────>│                     │
     │                    │                     │
     │                    │ 2. 執行搜尋程式     │
     │                    │<────────────────────┤
     │                    │                     │
     │                    │ 3. POST /api/pcba/  │
     │                    │    uid-search       │
     │                    │<────────────────────┤
     │                    │    {uid: "NL-..."}  │
     │                    │                     │
     │ 4. WebSocket       │                     │
     │    廣播 uid_search │                     │
     │<───────────────────┤                     │
     │                    │                     │
     │ 5. 顯示 UID        │                     │
     │    自動填入欄位    │                     │
     └────────────────────┴─────────────────────┘
```

### 詳細步驟

1. **前端點擊搜尋**：設定 `searchingUid = true`，顯示等待訊息
2. **執行 uid_searcher**：模擬搜尋延遲後產生或使用指定 UID
3. **POST 到後端**：`uid_searcher` 將 UID 透過 HTTP POST 傳送至 `/api/pcba/uid-search`
4. **後端廣播**：後端收到後透過 WebSocket 廣播 `uid_search` 事件給所有連線的前端
5. **前端接收**：前端 WebSocket 接收到事件後自動填入 UID 欄位並顯示成功訊息

## API 端點

### POST /api/pcba/uid-search

接收 UID 並廣播給前端。

**Request Body:**
```json
{
  "uid": "NL-20251204-0001"
}
```

**Response:**
```json
{
  "status": "accepted",
  "uid": "NL-20251204-0001",
  "message": "UID broadcasted to frontend"
}
```

## 故障排除

### UID 沒有出現在前端

1. **檢查後端服務**：
   ```bash
   curl http://localhost:8000/health
   ```

2. **檢查 WebSocket 連線**：
   - 前端下方應顯示 "WS connected"（綠色）
   - 若顯示紅色 "disconnected"，重新載入頁面

3. **手動測試 API**：
   ```bash
   curl -X POST http://localhost:8000/api/pcba/uid-search \
     -H "Content-Type: application/json" \
     -d '{"uid":"TEST-UID-12345"}'
   ```

4. **檢查後端日誌**：
   ```bash
   docker-compose logs -f backend
   ```
   應看到：
   ```
   [PCBA:/uid-search] Received UID: ...
   [PCBA:/uid-search] Broadcasted UID to frontend: ...
   ```

### 404 Not Found 錯誤

如果遇到 404 錯誤，表示後端路由未載入。需要重啟後端服務：

```bash
# 重啟 Docker 容器
cd /Users/lance/Documents/GitHub/production-test-system
docker-compose restart backend

# 等待幾秒後測試
sleep 3
curl -X POST http://localhost:8000/api/pcba/uid-search \
  -H "Content-Type: application/json" \
  -d '{"uid":"TEST-123"}'

# 應該返回：
# {"status":"accepted","uid":"TEST-123","message":"UID broadcasted to frontend"}
```

### 編譯錯誤

- **找不到 curl.h**：安裝 libcurl 開發套件
  ```bash
  # macOS
  brew install curl
  
  # Ubuntu/Debian
  sudo apt-get install libcurl4-openssl-dev
  ```

- **連結錯誤**：確認 Makefile 中的 curl 路徑正確
  ```bash
  brew --prefix curl
  ```

## 進階用法

### 批次測試

建立腳本批次傳送多個 UID：

```bash
#!/bin/bash
for i in {1..5}; do
  ./uid_searcher "NL-20251204-$(printf '%04d' $i)"
  sleep 2
done
```

### 整合實際硬體

將 `uid_searcher.c` 中的 `generate_uid()` 函數替換為實際讀取硬體序號的邏輯：

```c
void read_device_uid(char* uid, size_t max_len) {
    // 替換為實際的硬體讀取邏輯
    // 例如：讀取 USB 設備、UART 通訊等
}
```

## 相關檔案

- `uid_searcher.c`：UID 搜尋程式原始碼
- `Makefile`：編譯設定（支援 `pcba_watcher` 和 `uid_searcher`）
- `backend/app/routers/pcba_events.py`：後端 API 端點實作
- `frontend-nl/src/components/PcbaIQC.js`：前端 PCBA IQC 頁面
- `frontend-nl/src/i18n/locales.js`：中英文翻譯

## 授權

此工具為內部測試工具，僅供開發與測試使用。
