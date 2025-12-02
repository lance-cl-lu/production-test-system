# 部署指南

## Docker 部署（推薦）

### 1. 完整部署（使用 Docker Compose）

```bash
# 啟動所有服務
docker-compose up -d

# 查看日誌
docker-compose logs -f

# 停止服務
docker-compose down
```

### 2. 僅資料庫容器化

適合開發環境，後端和前端在本地運行:

```bash
# 僅啟動 MySQL
docker-compose up -d mysql

# 本地啟動後端和前端
cd backend && uvicorn app.main:app --reload &
cd frontend && npm start &
```

## 生產環境部署

### 方案一: 使用 Nginx + Gunicorn

#### 1. 後端部署

```bash
# 安裝依賴
cd backend
pip install -r requirements.txt
pip install gunicorn

# 使用 Gunicorn 啟動
gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --daemon
```

#### 2. 前端建置

```bash
cd frontend
npm install
npm run build
```

#### 3. Nginx 設定

```nginx
# /etc/nginx/sites-available/production-test

upstream backend {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name your-domain.com;

    # 前端
    location / {
        root /path/to/frontend/build;
        try_files $uri /index.html;
    }

    # 後端 API
    location /api {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket
    location /ws {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

```bash
# 啟用設定
sudo ln -s /etc/nginx/sites-available/production-test /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 方案二: 使用 Docker

#### 1. 建置後端映像

```bash
cd backend
docker build -t production-test-backend .
```

#### 2. 建置前端映像

建立 `frontend/Dockerfile`:
```dockerfile
FROM node:18-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

建立 `frontend/nginx.conf`:
```nginx
server {
    listen 80;
    location / {
        root /usr/share/nginx/html;
        try_files $uri /index.html;
    }
}
```

```bash
cd frontend
docker build -t production-test-frontend .
```

#### 3. 執行容器

```bash
# 網路
docker network create prod-test-network

# MySQL
docker run -d \
  --name prod-test-db \
  --network prod-test-network \
  -e MYSQL_ROOT_PASSWORD=rootpassword \
  -e MYSQL_DATABASE=production_test \
  -e MYSQL_USER=testuser \
  -e MYSQL_PASSWORD=testpassword \
  -v mysql_data:/var/lib/mysql \
  mysql:8.0

# 後端
docker run -d \
  --name prod-test-backend \
  --network prod-test-network \
  -p 8000:8000 \
  -e DATABASE_URL=mysql+pymysql://testuser:testpassword@prod-test-db:3306/production_test \
  production-test-backend

# 前端
docker run -d \
  --name prod-test-frontend \
  -p 80:80 \
  production-test-frontend
```

## 系統服務設定（Linux）

### 後端服務

建立 `/etc/systemd/system/production-test-backend.service`:

```ini
[Unit]
Description=Production Test Backend
After=network.target mysql.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/production-test/backend
Environment="PATH=/opt/production-test/backend/venv/bin"
ExecStart=/opt/production-test/backend/venv/bin/gunicorn \
  app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable production-test-backend
sudo systemctl start production-test-backend
sudo systemctl status production-test-backend
```

## 環境變數設定

### 生產環境 .env

```bash
# Backend
DATABASE_URL=mysql+pymysql://user:pass@db-host:3306/production_test
CLOUD_UPLOAD_ENABLED=true
CLOUD_API_URL=https://your-cloud-api.com/upload
CLOUD_API_KEY=your-secret-key
UPLOAD_SCHEDULE_HOURS=1
CORS_ORIGINS=https://your-domain.com

# Frontend
REACT_APP_API_URL=https://your-domain.com
REACT_APP_WS_URL=wss://your-domain.com/ws
```

## 資料庫遷移

使用 Alembic 進行資料庫版本控制:

```bash
cd backend

# 初始化（首次）
alembic init alembic

# 建立遷移
alembic revision --autogenerate -m "Initial migration"

# 執行遷移
alembic upgrade head
```

## 監控與日誌

### 1. 應用程式日誌

```bash
# 後端日誌
tail -f /var/log/production-test/backend.log

# 前端 Nginx 日誌
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

### 2. 資料庫監控

```bash
# 連線數
docker exec production_test_db mysql -u root -p -e "SHOW STATUS LIKE 'Threads_connected';"

# 資料庫大小
docker exec production_test_db mysql -u root -p -e "SELECT table_schema, SUM(data_length + index_length) / 1024 / 1024 AS 'Size (MB)' FROM information_schema.tables GROUP BY table_schema;"
```

## 效能優化

### 1. MySQL 優化

```sql
-- 新增索引
CREATE INDEX idx_test_time ON test_records(test_time);
CREATE INDEX idx_device_result ON test_records(device_id, test_result);

-- 定期清理舊資料
DELETE FROM test_records WHERE test_time < DATE_SUB(NOW(), INTERVAL 1 YEAR);
```

### 2. 快取設定

考慮使用 Redis 快取熱門查詢結果。

## 備份策略

```bash
# 每日備份腳本
#!/bin/bash
BACKUP_DIR="/backup/production-test"
DATE=$(date +%Y%m%d)

# 備份資料庫
docker exec production_test_db mysqldump -u testuser -ptestpassword production_test | gzip > $BACKUP_DIR/db_$DATE.sql.gz

# 保留最近 30 天
find $BACKUP_DIR -name "db_*.sql.gz" -mtime +30 -delete
```

設定 crontab:
```bash
0 2 * * * /opt/scripts/backup.sh
```
