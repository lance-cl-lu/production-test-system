# PCBA 測試流程快速指南

## 新的整合流程

`pcba_watcher` 現已整合 UID 搜尋與測試功能，流程更簡潔！

## 架構圖

```
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│  前端 UI     │         │   後端       │         │ pcba_watcher │
│ (React)      │         │  (FastAPI)   │         │   (C)        │
└──────┬───────┘         └──────┬───────┘         └──────┬───────┘
       │                        │                        │
       │ 1. 點擊「搜尋」        │                        │
       ├───────────────────────>│                        │
       │ POST /uid-search       │                        │
       │                        │ 2. 寫入 SEARCH 指令    │
       │                        ├───────────────────────>│
       │                        │   到 pcba_test.txt     │
       │                        │                        │
       │                        │    3. 產生虛擬 UID     │
       │                        │<───────────────────────┤
       │                        │   POST /uid-found      │
       │  4. WebSocket 廣播     │                        │
       │<───────────────────────┤                        │
       │  顯示 UID              │                        │
       │                        │                        │
       │ 5. 點擊「開始測試」    │                        │
       ├───────────────────────>│                        │
       │ POST /start-test       │                        │
       │                        │ 6. 寫入 TEST <UID>     │
       │                        ├───────────────────────>│
       │                        │   到 pcba_test.txt     │
       │                        │                        │
       │                        │   7. 執行測試流程      │
       │                        │<───────────────────────┤
       │                        │   POST /events (多次)  │
       │  8. WebSocket 廣播     │                        │
       │<───────────────────────┤                        │
       │  測試進度與結果        │                        │
       └────────────────────────┴────────────────────────┘
```

## 啟動步驟

### 1. 啟動後端（如果尚未啟動）

```bash
cd /Users/lance/Documents/GitHub/production-test-system
docker-compose up -d backend
```

### 2. 啟動 pcba_watcher（必須）

```bash
cd tester
./pcba_watcher
```

應看到：
```
========================================
PCBA 測試監看程式啟動
========================================
監看檔案: ../shared/pcba_test.txt
測試事件 API: http://localhost:8000/api/pcba/events
UID 回報 API: http://localhost:8000/api/pcba/uid-found

支援指令：
  SEARCH          - 產生虛擬 UID
  TEST <SERIAL>   - 執行測試流程
========================================
等待指令...
```

### 3. 啟動前端（如果尚未啟動）

```bash
cd frontend-nl
npm start
```

## 完整測試流程

### 方式 1：搜尋後測試（推薦）

1. **開啟前端**：`http://localhost:3001` → PCBA進料檢驗
2. **點擊「搜尋」**：
   - 前端顯示「正在搜尋 UID...」
   - pcba_watcher 產生虛擬 UID（例如：`NL-20251204-1234`）
   - UID 自動填入序號欄位
3. **點擊「開始測試」**：
   - pcba_watcher 執行 5 個測試項目
   - 前端即時顯示測試進度
   - 測試完成後自動儲存

### 方式 2：手動輸入 UID 測試

1. **開啟前端**：`http://localhost:3001` → PCBA進料檢驗
2. **手動輸入序號**：例如 `NL-TEST-999`
3. **點擊「開始測試」**：
   - pcba_watcher 執行測試
   - 前端即時顯示結果

## pcba_watcher 輸出範例

### 搜尋 UID

```
[SEARCH] Generating virtual UID...
[SEARCH] Generated UID: NL-20251204-7823
[SEARCH] Sending UID to backend: http://localhost:8000/api/pcba/uid-found
[SEARCH] ✓ UID sent successfully
```

### 執行測試

```
========================================
[TEST] Starting test for: NL-20251204-7823
========================================
[TEST] Testing wifi for NL-20251204-7823...
[TEST] wifi: pass
[TEST] Testing firmware for NL-20251204-7823...
[TEST] firmware: pass
[TEST] Testing touch for NL-20251204-7823...
[TEST] touch: pass
[TEST] Testing bluetooth for NL-20251204-7823...
[TEST] bluetooth: pass
[TEST] Testing speaker for NL-20251204-7823...
[TEST] speaker: fail
========================================
[TEST] Test completed: NL-20251204-7823
========================================
```

## 手動測試指令

### 測試 SEARCH 指令

```bash
echo "SEARCH" > shared/pcba_test.txt
touch shared/pcba_test.txt
```

### 測試 TEST 指令

```bash
echo "TEST NL-MANUAL-001" > shared/pcba_test.txt
touch shared/pcba_test.txt
```

## 疑難排解

### pcba_watcher 沒有反應

1. 確認檔案路徑正確：
   ```bash
   ls -la ../shared/pcba_test.txt
   ```

2. 確認後端運行：
   ```bash
   curl http://localhost:8000/health
   ```

3. 確認 API 端點可用：
   ```bash
   curl -X POST http://localhost:8000/api/pcba/uid-search \
     -H "Content-Type: application/json" -d '{}'
   ```

### 前端沒有收到 UID

1. 檢查 WebSocket 連線（前端下方應顯示 "WS connected"）
2. 檢查後端日誌：
   ```bash
   docker-compose logs -f backend
   ```
3. 確認 pcba_watcher 正在運行

### 重新編譯

```bash
cd tester
make clean
make
./pcba_watcher
```

## 與舊流程的差異

**舊流程**（已移除）：
- 需要分別啟動 `pcba_watcher` 和 `uid_searcher`
- 前端搜尋時手動執行 `./uid_searcher`
- 兩個獨立的 C 程式

**新流程**（當前）：
- 只需啟動 `pcba_watcher`
- 前端搜尋自動觸發 UID 產生
- 單一整合程式處理所有功能

## 檔案說明

- `pcba_watcher.c`：整合 UID 搜尋與測試的 C 程式
- `shared/pcba_test.txt`：指令傳遞檔案
- `README_WATCHER.md`：詳細使用說明
- `Makefile`：編譯配置

---

**注意**：`uid_searcher.c` 已移除，所有功能已整合至 `pcba_watcher.c`。
