# 客戶部署包

## 📦 部署文件

為了在客戶環境中運行此系統，請使用以下文件：

### 必需文件
- `docker-compose.yml` - Docker Compose 配置（使用預構建鏡像）
- `.env.example` - 環境變量模板（請複製為 `.env` 並修改）

### 文檔
- `DEPLOYMENT.md` - 完整部署指南
- `API.md` - API 文檔

## 🚀 快速開始（3 步）

### 1️⃣ 認證 GitHub Container Registry

```bash
docker login ghcr.io
# 使用你的 GitHub 用戶名和 Personal Access Token
```

> **如何獲取 Token？**
> - 前往 GitHub → Settings → Developer settings → Personal access tokens
> - 建立新 token，勾選 `read:packages`
> - 複製 token 並在上述命令中使用

### 2️⃣ 準備環境變量

```bash
cp .env.example .env
# 編輯 .env 修改敏感信息和配置
```

### 3️⃣ 啟動應用

```bash
docker-compose pull    # 拉取最新鏡像
docker-compose up -d   # 啟動所有服務
```

### ✅ 驗證啟動成功

```bash
docker-compose ps
```

所有容器應顯示 `Up` 狀態。

## 🌐 訪問應用

| 服務 | URL | 用途 |
|------|-----|------|
| Frontend-SMAC | http://localhost:3000 | 主要測試界面 |
| Frontend-NL | http://localhost:3001 | NL 測試界面 |
| API | http://localhost:8000 | REST API |
| API 文檔 | http://localhost:8000/docs | Swagger UI |

## 📋 常用命令

```bash
# 查看日誌
docker-compose logs -f backend

# 重啟服務
docker-compose restart

# 停止服務
docker-compose down

# 更新到最新版本
docker-compose pull
docker-compose up -d
```

## 🔒 安全建議

- ✅ 使用強密碼修改 `.env` 中的 `MYSQL_ROOT_PASSWORD` 和 `MYSQL_PASSWORD`
- ✅ 將 `REACT_APP_API_URL` 設置為實際伺服器 IP/域名
- ✅ 在生產環境使用 HTTPS（建議用 Nginx 反向代理）
- ✅ 定期更新 Docker 鏡像：`docker-compose pull`

## 🆘 故障排除

**問題：登錄失敗**
```bash
# 檢查 token 是否正確
docker logout ghcr.io
docker login ghcr.io
```

**問題：容器無法啟動**
```bash
docker-compose logs mysql
docker-compose logs backend
```

**問題：無法連接數據庫**
- 確認 MySQL 容器正常運行：`docker-compose ps`
- 檢查 `.env` 中的 `MYSQL_PASSWORD` 是否正確

## 📞 支持

如有問題，請聯繫開發團隊。

---

**版本**: 1.0  
**最後更新**: 2025-12-05
