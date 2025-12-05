# 開發環境設置指南

## 🚀 快速開始

### 啟動開發環境

```bash
# 啟動所有服務（自動構建容器）
./start.sh

# 或使用 docker-compose 直接啟動
docker-compose up -d --build
```

### 停止開發環境

```bash
# 停止所有服務
./stop.sh

# 或使用 docker-compose
docker-compose down
```

---

## 📁 開發工作流

### 後端開發 (FastAPI)

**熱重載開發**
```bash
# 後端代碼修改會自動重新加載
# 位置: backend/app/

# 查看後端日誌
docker-compose logs -f backend

# 進入後端容器調試
docker-compose exec backend bash

# 運行測試（在容器內）
docker-compose exec backend pytest
```

**訪問 API 文檔**
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 前端開發 (React)

**熱更新開發**
```bash
# Frontend-SMAC 代碼修改會自動重新加載
# 位置: frontend-smac/src/

# Frontend-NL 代碼修改會自動重新加載
# 位置: frontend-nl/src/

# 查看前端日誌
docker-compose logs -f frontend-smac
docker-compose logs -f frontend-nl
```

**訪問前端**
- SMAC: http://localhost:3000
- NL: http://localhost:3001

### 數據庫開發

```bash
# 進入 MySQL 容器
docker-compose exec mysql bash

# 連接數據庫
mysql -u testuser -p production_test

# 或使用 MySQL 工具（如 DBeaver）連接
# Host: localhost
# Port: 3306
# User: testuser
# Password: testpassword
```

---

## 🔄 常見任務

### 重建特定服務

```bash
# 重建並重啟後端
docker-compose up -d --build backend

# 重建並重啟前端
docker-compose up -d --build frontend-smac

# 重建所有服務
docker-compose up -d --build
```

### 查看日誌

```bash
# 查看所有服務日誌
docker-compose logs

# 實時查看後端日誌
docker-compose logs -f backend

# 查看最後 100 行日誌
docker-compose logs --tail=100 backend

# 查看特定時間範圍日誌
docker-compose logs --since 10m backend
```

### 進入容器調試

```bash
# 後端調試
docker-compose exec backend bash
cd /app
python -m pytest
python -c "import app; print(app.__file__)"

# 前端調試
docker-compose exec frontend-smac bash
npm list  # 檢查依賴

# 數據庫調試
docker-compose exec mysql mysql -u testuser -p production_test
```

### 查看容器資源使用

```bash
# 查看運行中的容器
docker-compose ps

# 查看容器統計信息（CPU, 內存）
docker stats

# 查看容器詳細信息
docker-compose exec backend df -h  # 磁盤空間
```

### 清理開發環境

```bash
# 停止並移除容器（保留數據）
docker-compose down

# 停止並移除容器及數據卷（完全清除）
docker-compose down -v

# 清理 Docker 系統（移除未使用的鏡像、容器等）
docker system prune -a

# 清理 Docker 卷（移除未使用的卷）
docker volume prune
```

---

## 🛠️ 開發工具

### 推薦 IDE 和工具

**後端**
- VS Code + Python 擴展
- PyCharm
- 調試: `python -m pdb`, `print` 或 VS Code Debugger

**前端**
- VS Code + React 擴展
- Chrome DevTools（F12）
- React DevTools 擴展

**數據庫**
- DBeaver（MySQL 視覺化工具）
- TablePlus
- 命令行: `mysql` 客戶端

### 有用的 Docker 命令

```bash
# 顯示容器ID
docker-compose ps -q backend

# 進入容器並執行命令
docker-compose exec backend sh -c "cd /app && python -m pytest"

# 複製文件到容器
docker-compose cp ./test.txt backend:/app/

# 複製文件從容器
docker-compose cp backend:/app/output.txt ./

# 查看容器網絡
docker-compose exec backend ping mysql

# 查看容器環境變量
docker-compose exec backend env | grep DATABASE_URL
```

---

## 🐛 常見問題

### Q: 容器無法啟動
```bash
# 查看具體錯誤日誌
docker-compose logs backend

# 檢查端口是否被占用
lsof -i :8000
lsof -i :3000
lsof -i :3001
```

### Q: 修改代碼後沒有更新
```bash
# 確保卷掛載正確
docker-compose ps -a

# 檢查是否正在監聽文件更改
docker-compose logs -f frontend-smac | grep -i "watching"

# 強制重新加載
docker-compose restart frontend-smac
```

### Q: 無法連接數據庫
```bash
# 檢查 MySQL 容器是否運行
docker-compose ps mysql

# 檢查連接字符串
docker-compose exec backend env | grep DATABASE_URL

# 測試連接
docker-compose exec backend python -c \
  "from app.database import engine; engine.connect()"
```

### Q: 前端出現跨域問題（CORS）
```bash
# 檢查 REACT_APP_API_URL 環境變量
docker-compose exec frontend-smac env | grep REACT_APP_API_URL

# 應確保指向 http://localhost:8000 或正確的後端地址
```

---

## 📝 開發最佳實踐

1. **定期提交**
   ```bash
   git add .
   git commit -m "feat: description"
   ```

2. **使用 .gitignore**
   ```bash
   # 避免提交敏感文件
   echo ".env" >> .gitignore
   echo "node_modules/" >> .gitignore
   ```

3. **編寫測試**
   ```bash
   # 後端測試
   docker-compose exec backend pytest tests/

   # 前端測試
   docker-compose exec frontend-smac npm test
   ```

4. **代碼格式化**
   ```bash
   # Python 格式化
   docker-compose exec backend black app/

   # JavaScript 格式化
   docker-compose exec frontend-smac npx prettier --write src/
   ```

5. **定期更新依賴**
   ```bash
   # Python
   docker-compose exec backend pip list --outdated

   # Node
   docker-compose exec frontend-smac npm outdated
   ```

---

## 📚 更多資源

- [Docker Compose 官方文檔](https://docs.docker.com/compose/)
- [FastAPI 官方文檔](https://fastapi.tiangolo.com/)
- [React 官方文檔](https://react.dev/)
- [MySQL 官方文檔](https://dev.mysql.com/doc/)

