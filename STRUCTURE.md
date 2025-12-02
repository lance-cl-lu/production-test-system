# Production Test System - 專案結構

```
production-test-system/
├── backend/                    # FastAPI 後端
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py            # 主程式入口
│   │   ├── config.py          # 設定檔
│   │   ├── database.py        # 資料庫連線
│   │   ├── models.py          # SQLAlchemy 模型
│   │   ├── schemas.py         # Pydantic 資料驗證
│   │   ├── services.py        # 業務邏輯層
│   │   ├── scheduler.py       # 定時任務
│   │   └── routers/
│   │       ├── __init__.py
│   │       ├── test_records.py  # 測試記錄 API
│   │       └── websocket.py     # WebSocket 端點
│   ├── requirements.txt       # Python 依賴
│   ├── Dockerfile
│   └── .env.example
│
├── frontend/                   # React 前端
│   ├── public/
│   │   └── index.html
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard.js      # 儀表板
│   │   │   └── TestRecordList.js # 測試記錄列表
│   │   ├── services/
│   │   │   ├── api.js            # REST API 服務
│   │   │   └── websocket.js      # WebSocket 服務
│   │   ├── App.js
│   │   ├── App.css
│   │   └── index.js
│   ├── package.json
│   └── .env.example
│
├── tester/                     # 測試程式
│   ├── tester.py              # 測試程式主檔
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
│
├── docs/                       # 文檔
│   ├── API.md                 # API 文檔
│   ├── DATABASE.md            # 資料庫文檔
│   └── DEPLOYMENT.md          # 部署指南
│
├── logs/                       # 日誌目錄
│
├── docker-compose.yml         # Docker Compose 設定
├── README.md                  # 專案說明
├── QUICKSTART.md             # 快速啟動指南
├── start.sh                   # 啟動腳本
├── stop.sh                    # 停止腳本
└── .gitignore
```

## 技術架構

### 後端 (Backend)
- **框架**: FastAPI 0.104.1
- **資料庫 ORM**: SQLAlchemy 2.0.23
- **資料庫**: MySQL 8.0
- **排程器**: APScheduler 3.10.4
- **即時通訊**: WebSocket
- **API 文檔**: Swagger UI / ReDoc

### 前端 (Frontend)
- **框架**: React 18.2.0
- **UI 庫**: Ant Design 5.11.5
- **HTTP 客戶端**: Axios 1.6.2
- **圖表**: Recharts 2.10.3
- **日期處理**: Day.js 1.11.10

### 測試程式 (Tester)
- **語言**: Python 3
- **HTTP 客戶端**: Requests 2.31.0

## 核心功能

### 1. FastAPI 後端
✅ RESTful API (CRUD 操作)
✅ WebSocket 即時通訊
✅ 定時任務（雲端上傳）
✅ 資料庫層（SQLAlchemy ORM）
✅ 資料驗證（Pydantic）
✅ 自動生成 API 文檔

### 2. React 前端
✅ 儀表板（統計資訊）
✅ 測試記錄管理
✅ 即時更新（WebSocket）
✅ 資料篩選與查詢
✅ 響應式設計

### 3. 測試程式
✅ 單次測試模式
✅ 批次測試模式
✅ 連續測試模式（模擬產線）
✅ 自動生成測試資料
✅ 錯誤處理與重試

### 4. 雲端上傳（可選）
✅ 定時自動上傳
✅ 上傳狀態追蹤
✅ 上傳日誌記錄
✅ 可配置上傳間隔

## 資料流程

```
1. 測試程式生成測試資料
   ↓
2. POST 到 FastAPI 後端
   ↓
3. 後端寫入 MySQL 資料庫
   ↓
4. 透過 WebSocket 推送到前端
   ↓
5. 前端即時更新顯示
   ↓
6. 排程器定時上傳雲端（可選）
```

## 開發規範

### 程式碼風格
- Python: PEP 8
- JavaScript: ESLint (React)

### Git 工作流程
1. 從 `main` 分支建立功能分支
2. 開發並測試新功能
3. 提交 Pull Request
4. Code Review 後合併

### 環境變數管理
- 開發環境: `.env`
- 生產環境: 環境變數或 `.env.production`

## 測試

### 後端測試
```bash
cd backend
pytest
```

### 前端測試
```bash
cd frontend
npm test
```

## 擴展建議

### 短期優化
- [ ] 新增使用者認證（JWT）
- [ ] 新增測試報告匯出功能（PDF/Excel）
- [ ] 新增即時圖表顯示
- [ ] 新增告警通知（Email/SMS）

### 中期優化
- [ ] 支援多測試站別管理
- [ ] 新增產品配置管理
- [ ] 新增測試規格管理
- [ ] 新增批次分析功能

### 長期優化
- [ ] AI 異常檢測
- [ ] 預測性維護
- [ ] 多語言支援（i18n）
- [ ] 行動版 APP

## 授權

MIT License
