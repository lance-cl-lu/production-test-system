# 快速啟動指南

## 方法一: 使用啟動腳本（推薦）

```bash
# 賦予執行權限
chmod +x start.sh stop.sh

# 啟動所有服務
./start.sh

# 停止所有服務
./stop.sh
```

## 方法二: 手動啟動

### 1. 啟動資料庫

```bash
docker-compose up -d mysql
```

### 2. 啟動後端

```bash
cd backend
cp .env.example .env
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 3. 啟動前端（新終端機）

```bash
cd frontend
cp .env.example .env
npm install
npm start
```

### 4. 執行測試程式（新終端機）

```bash
cd tester
cp .env.example .env
pip install -r requirements.txt

# 單次測試
python tester.py single

# 批次測試 20 筆
python tester.py batch 20

# 連續測試（每 3 秒）
python tester.py continuous 3
```

## 服務網址

- **前端**: http://localhost:3000
- **後端 API**: http://localhost:8000
- **API 文檔**: http://localhost:8000/docs
- **MySQL**: localhost:3306

## 預設帳號

- **MySQL**
  - 帳號: `testuser`
  - 密碼: `testpassword`
  - 資料庫: `production_test`

## 常見問題

### Q: 資料庫連線失敗？
確認 MySQL 容器已啟動:
```bash
docker ps
```

### Q: 前端無法連接後端？
檢查 `.env` 檔案中的 API URL 設定。

### Q: 測試程式上傳失敗？
確認後端服務已啟動並檢查 API URL。

## 功能說明

### 1. 儀表板
- 即時顯示測試統計資料
- 總測試數、通過數、失敗數
- 良率計算
- 今日測試數

### 2. 測試記錄
- 測試記錄列表
- 支援篩選（設備ID、測試結果、日期範圍）
- 即時更新（透過 WebSocket）

### 3. 測試程式
- 單次測試模式
- 批次測試模式
- 連續測試模式（模擬產線）

### 4. 雲端上傳（可選）
- 定時上傳未上傳的記錄
- 可在 `.env` 中設定上傳間隔
- 記錄上傳日誌

## 開發說明

### 後端技術棧
- FastAPI (Web Framework)
- SQLAlchemy (ORM)
- MySQL (Database)
- APScheduler (定時任務)
- WebSocket (即時通訊)

### 前端技術棧
- React 18
- Ant Design 5
- Axios (HTTP Client)
- WebSocket (即時通訊)
- Recharts (圖表)

### 測試程式
- Python 3
- Requests (HTTP Client)
