# Production Test System

生產測試資料管理系統

## 架構說明

```
[ React Web UI ]
    |   ↑
    | REST API / WebSocket
    v
[ FastAPI Backend ]
    ├── REST API
    ├── WebSocket Server
    ├── Scheduler（定時上傳雲端）
    ├── DB Access Layer (SQLAlchemy)
    v
[ Local MySQL Database ]
    ^
    |
[ Production Tester Program (Python) ]
    |
    └── Upload測試資料 → FastAPI

[ Cloud Service（Optional） ]
    ↑
    └── FastAPI Scheduler Upload
```

## 專案結構

```
.
├── backend/          # FastAPI 後端
├── frontend/         # React 前端
├── tester/          # 測試程式
└── docker-compose.yml
```

## 快速啟動

### 1. 啟動資料庫和後端

```bash
docker-compose up -d
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 2. 啟動前端

```bash
cd frontend
npm install
npm start
```

### 3. 執行測試程式

```bash
cd tester
pip install -r requirements.txt
python tester.py
```

## 環境變數

複製 `.env.example` 為 `.env` 並配置相關參數。

## API 文檔

啟動後端後訪問: http://localhost:8000/docs
