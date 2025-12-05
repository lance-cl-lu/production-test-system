# 生產環境部署指南

## 前置要求

- Docker & Docker Compose
- GitHub 帳號（用於從 GHCR 拉取私有鏡像）

## 步驟 1：設置 GitHub 認證

### 獲取 Personal Access Token (PAT)

1. 進入 GitHub Settings → Developer settings → Personal access tokens
2. 點擊 "Generate new token (classic)"
3. 選擇 `read:packages` 權限
4. 複製 token

### 登錄到 GitHub Container Registry

```bash
docker login ghcr.io -u YOUR_GITHUB_USERNAME -p YOUR_PERSONAL_ACCESS_TOKEN
```

## 步驟 2：準備配置文件

將以下文件複製到客戶的機器：

```
├── docker-compose.yml
├── .env
├── shared/          # (如有必要的共享數據)
```

### 創建 `.env` 文件

```bash
# Database Configuration
MYSQL_ROOT_PASSWORD=your_secure_password
MYSQL_DATABASE=production_test
MYSQL_USER=testuser
MYSQL_PASSWORD=your_secure_password

# API Configuration
BACKEND_PORT=8000

# Frontend Configuration
FRONTEND_SMAC_PORT=3000
FRONTEND_NL_PORT=3001

# Application Configuration
REACT_APP_API_URL=http://your-server-ip:8000
CLOUD_UPLOAD_ENABLED=false
```

## 步驟 3：啟動服務

```bash
# 拉取最新鏡像
docker-compose pull

# 啟動所有服務（後台運行）
docker-compose up -d

# 查看服務狀態
docker-compose ps

# 查看日誌
docker-compose logs -f backend
docker-compose logs -f frontend-smac
docker-compose logs -f frontend-nl
```

## 步驟 4：訪問應用

- **Frontend-SMAC**: http://localhost:3000
- **Frontend-NL**: http://localhost:3001
- **API 文檔**: http://localhost:8000/docs

## 常見操作

### 重啟服務

```bash
docker-compose restart backend
docker-compose restart frontend-smac
```

### 停止服務

```bash
docker-compose down
```

### 完整清理（包括數據）

```bash
docker-compose down -v
```

### 更新到最新版本

```bash
docker-compose pull
docker-compose up -d
```

## 故障排除

### 檢查容器日誌

```bash
docker-compose logs mysql
docker-compose logs backend
```

### 重建特定容器

```bash
docker-compose up -d --force-recreate backend
```

### 查看容器內部連接

```bash
docker-compose exec backend bash
```

## 支持

如有問題，請聯繫開發團隊或查看 GitHub 倉庫的 Issues。
