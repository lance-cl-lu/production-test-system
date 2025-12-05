# 快速啟動指南

## 🚀 一鍵啟動（推薦）

```bash
# 啟動所有服務（開發模式，自動構建）
./start.sh

# 訪問應用
# - Frontend-SMAC: http://localhost:3000
# - Frontend-NL:   http://localhost:3001
# - Backend API:   http://localhost:8000
# - API 文檔:      http://localhost:8000/docs

# 停止所有服務
./stop.sh
```

---

## 📖 開發與部署

### 開發環境
```bash
# 開發模式（源代碼卷掛載，熱重載）
./start.sh

# 查看日誌
docker-compose logs -f backend
docker-compose logs -f frontend-smac

# 進入容器調試
docker-compose exec backend bash
docker-compose exec frontend-smac bash
```

詳見：**[DEVELOPMENT.md](DEVELOPMENT.md)** - 完整開發指南

### 客戶部署
```bash
# 生產模式（使用 GHCR 預構建鏡像，無源代碼）
docker login ghcr.io
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d
```

詳見：**[CUSTOMER_DEPLOYMENT.md](CUSTOMER_DEPLOYMENT.md)** - 客戶部署指南

---

## 📂 文檔導航

| 文檔 | 說明 |
|------|------|
| **QUICKSTART.md** | ⬅️ 你在這裡（快速開始） |
| **DEVELOPMENT.md** | 開發環境設置和工作流 |
| **CUSTOMER_DEPLOYMENT.md** | 給客戶的部署指南 |
| **DEPLOYMENT.md** | 詳細的技術部署文檔 |
| **DEPLOYMENT_PLAN.md** | 部署計劃和檢查清單 |
| **API.md** | API 文檔 |

---

## 🌐 服務網址

| URL | 服務 | 說明 |
|-----|------|------|
| http://localhost:3000 | Frontend-SMAC | SMAC 測試界面 |
| http://localhost:3001 | Frontend-NL | NL 測試界面 |
| http://localhost:8000 | Backend API | FastAPI 服務 |
| http://localhost:8000/docs | Swagger UI | API 互動文檔 |
| http://localhost:8000/redoc | ReDoc | API 參考文檔 |
| localhost:3306 | MySQL | 數據庫 |

---

## 🔑 預設帳號密碼

**MySQL**
- 用戶名：`testuser`
- 密碼：`testpassword`
- 數據庫：`production_test`
- 連接地址：`localhost:3306`

> ⚠️ **生產環境：** 必須修改 `.env` 中的所有密碼

---

## 🔄 常用命令速查

```bash
# 查看容器狀態
docker-compose ps

# 查看所有日誌
docker-compose logs

# 查看特定服務日誌
docker-compose logs -f backend
docker-compose logs -f frontend-smac
docker-compose logs -f mysql

# 重啟某個服務
docker-compose restart backend

# 進入容器
docker-compose exec backend bash

# 停止並清除所有容器和數據
docker-compose down -v

# 完全清理系統（謹慎！）
docker system prune -a
```

---

## ✅ 驗證安裝

啟動後，檢查以下項目確認系統正常：

```bash
# 1. 檢查所有容器都在運行
docker-compose ps
# 所有容器應顯示 "Up" 狀態

# 2. 測試後端 API
curl http://localhost:8000/docs
# 應能訪問 Swagger UI

# 3. 測試前端
curl http://localhost:3000
# 應返回 HTML 內容

# 4. 測試數據庫連接
docker-compose exec mysql mysql -u testuser -p production_test -e "SELECT 1;"
# 應顯示查詢結果
```

---

## 🆘 常見問題

### Q: 容器無法啟動
```bash
# 查看詳細錯誤
docker-compose logs

# 完全重新開始
docker-compose down -v
./start.sh
```

### Q: 修改代碼後沒有更新
```bash
# 前端：瀏覽器刷新或重啟容器
docker-compose restart frontend-smac

# 後端：自動重新加載，查看日誌確認
docker-compose logs -f backend
```

### Q: 無法連接數據庫
```bash
# 檢查 MySQL 容器
docker-compose logs mysql

# 測試連接
docker-compose exec mysql mysql -u testuser -p production_test -e "SHOW TABLES;"
```

### Q: 前端顯示 CORS 錯誤
```bash
# 檢查 REACT_APP_API_URL 環境變量
docker-compose exec frontend-smac env | grep REACT_APP_API_URL

# 應該指向 http://localhost:8000
```

### Q: 忘記清理舊容器
```bash
# 查看所有容器（包括停止的）
docker ps -a

# 移除特定容器
docker rm CONTAINER_ID

# 或清理所有未使用資源
docker system prune -a
```

---

## 📝 下一步

1. **開發功能**
   - 查看 [DEVELOPMENT.md](DEVELOPMENT.md) 了解開發工作流
   - 修改後端代碼（backend/app/）
   - 修改前端代碼（frontend-*/src/）
   - 查看日誌確認更改

2. **部署到生產**
   - 提交代碼到 GitHub（main 分支）
   - GitHub Actions 自動構建並推送到 GHCR
   - 查看 [CUSTOMER_DEPLOYMENT.md](CUSTOMER_DEPLOYMENT.md) 給客戶部署

3. **測試與驗證**
   - 訪問 API 文檔：http://localhost:8000/docs
   - 測試各個 API 端點
   - 驗證前端功能

---

## 💡 提示

- 第一次運行時會自動下載 Docker 鏡像，可能需要幾分鐘
- 修改代碼後，前端和後端都有熱重載功能，無需手動重啟
- 定期 commit 代碼：GitHub Actions 會自動構建和部署
- 遇到問題時，`docker-compose logs` 是最好的調試工具

---

## 📚 更多資源

- [Docker Compose 文檔](https://docs.docker.com/compose/)
- [FastAPI 文檔](https://fastapi.tiangolo.com/)
- [React 文檔](https://react.dev/)
- [MySQL 文檔](https://dev.mysql.com/doc/)

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
