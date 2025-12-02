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
