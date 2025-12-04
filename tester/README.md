# Production Tester

生產測試程式模擬器

## 安裝

```bash
pip install -r requirements.txt
```

## 設定

複製 `.env.example` 為 `.env` 並配置參數:

```bash
cp .env.example .env
```

## 使用方式

### 1. 單次測試

### 觸發檔案格式（pcba_test.txt）

Watcher 監聽 `../shared/pcba_test.txt`。為了簡化操作，統一以下格式：

- 單行指令：`SERIAL <序號> <動作>`
- `<動作>` 支援：`START`、`STOP`

範例：

```
SERIAL NL-20251204-0001 START
SERIAL NL-20251204-0001 STOP
SERIAL GW-ABCDEF123456 START
```

注意事項：
- 建議每次觸發覆寫整個檔案內容為單一指令，避免混淆。
- Watcher 每次檔案變更時讀取當前最後一行指令並送至後端 API。

### 一鍵觸發腳本

提供 `tester/trigger_pcba.sh`，支援互動模式與參數模式：

用法：

```
# 互動模式（依序輸入序號與動作）
./trigger_pcba.sh

# 參數模式
./trigger_pcba.sh <SERIAL> <START|STOP>

# 範例
./trigger_pcba.sh NL-20251204-0001 START
./trigger_pcba.sh GW-ABCDEF123456 STOP
```

執行前請賦予執行權限：

```
chmod +x ./trigger_pcba.sh
```

腳本行為：
- 會將 `SERIAL <SERIAL> <ACTION>` 寫入 `../shared/pcba_test.txt`（覆寫）。
- 寫入後 `touch` 檔案，讓 watcher 立即偵測到變更。
- 會在終端印出已觸發內容方便確認。

### 後端連線檢查

Watcher 會將指令轉送至後端 `http://localhost:8000/api/pcba/events`。請確保後端服務已啟動並可連線。

### 疑難排解

- 若 watcher 無反應，確認 `../shared/pcba_test.txt` 路徑與權限。
- 若後端未收到事件，確認後端服務與防火牆設定。
執行一次測試並上傳資料:
```bash
python tester.py single
```

### 2. 批次測試
執行指定數量的測試:
```bash
python tester.py batch 20
```

### 3. 連續測試模式
模擬產線持續運作，每隔指定秒數執行測試:
```bash
# 預設每5秒測試一次
python tester.py continuous

# 自訂間隔（例如每3秒）
python tester.py continuous 3
```

## 測試資料說明

程式會自動生成以下測試資料:
- **序號**: 格式 `SN{日期}{流水號}`
- **電壓**: 4.8V - 5.2V (規格: 5V ±2%)
- **電流**: 0.45A - 0.55A (規格: 0.5A ±4%)
- **溫度**: 20°C - 35°C (規格: ≤32°C)
- **測試結果**: 所有參數符合規格為 PASS，否則為 FAIL

## 環境變數

- `API_URL`: FastAPI 後端 API 網址
- `DEVICE_ID`: 測試設備 ID
- `TEST_STATION`: 測試站別名稱
