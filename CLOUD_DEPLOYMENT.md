# Cloud 正式部署指南

本文件說明如何先在本機模擬 Cloud，再將相同程式部署到
`ota.twentyfouri.net`。本機與正式環境使用相同的 Docker image，差異只在
環境變數、網域、密碼及反向代理設定。

## 架構

```text
工廠端 Sensor 測試
  -> Local Backend / Local MySQL / durable outbox
  -> HTTPS POST https://ota.twentyfouri.net/api/v1/sync/batch
  -> Cloud Receiver
  -> Cloud MySQL

瀏覽器
  -> https://ota.twentyfouri.net/
  -> Cloud Frontend
  -> /api/v1/sensor-runs 及 /api/v1/dashboard/stats
```

工廠端永遠先將紀錄寫入 Local MySQL。Cloud 暫時離線時，outbox 會保留資料並
定時重試，因此 Cloud 故障不會中斷現場測試。

> 如果 `ota.twentyfouri.net` 已有既有 OTA 網站，請優先使用獨立子網域，例如
> `iqc.ota.twentyfouri.net`，並將本文中的網域全部替換。

## 一、本機模擬

複製本機範例設定：

```bash
cp .env.cloud.example .env.cloud.local
```

至少修改 API key，不要把 `.env.cloud.local` commit：

```env
CLOUD_UPLOAD_ENABLED=true
CLOUD_API_URL=http://cloud-receiver:8100/api/v1/sync/batch
CLOUD_API_KEY=local-development-key
CLOUD_SYNC_INTERVAL_SECONDS=10

CLOUD_PUBLIC_API_URL=http://localhost:8100
CLOUD_API_PORT=8100
CLOUD_FRONTEND_PORT=3100
CLOUD_MYSQL_PORT=3307
```

啟動：

```bash
docker compose --env-file .env.cloud.local up -d --build
```

本機網址：

- Factory UI：<http://localhost:3000>
- Cloud UI：<http://localhost:3100>
- Cloud API 文件：<http://localhost:8100/docs>
- Cloud health：<http://localhost:8100/health>

驗證同步：

```bash
docker compose exec mysql mysql -utestuser -ptestpassword production_test \
  -e "SELECT status, COUNT(*) FROM cloud_sync_outbox GROUP BY status;"

docker compose exec cloud-mysql mysql \
  -uclouduser -pcloudpassword production_test_cloud \
  -e "SELECT test_result, COUNT(*) FROM cloud_sensor_test_runs GROUP BY test_result;"
```

## 二、準備正式 Server

以下範例以 Ubuntu 為例。Server 需要：

- Docker 與 Docker Compose
- Git
- Nginx
- Certbot
- `ota.twentyfouri.net` DNS A/AAAA record 指向 Server
- 防火牆對外只開 SSH、80、443

安裝主機套件：

```bash
sudo apt update
sudo apt install -y git nginx apache2-utils certbot python3-certbot-nginx
```

Docker 請依 Docker 官方安裝流程安裝，完成後確認：

```bash
docker --version
docker compose version
```

## 三、下載程式

```bash
sudo mkdir -p /opt/production-test-system
sudo chown "$USER":"$USER" /opt/production-test-system
git clone -b upload_cloud <REPOSITORY_URL> /opt/production-test-system
cd /opt/production-test-system
```

之後更新版本：

```bash
cd /opt/production-test-system
git switch upload_cloud
git pull --ff-only
```

## 四、建立正式環境設定

產生不同的隨機密鑰：

```bash
openssl rand -hex 32
openssl rand -hex 24
openssl rand -hex 24
```

建立 `/opt/production-test-system/.env.cloud.production`：

```env
CLOUD_API_KEY=<32-byte-random-api-key>

CLOUD_MYSQL_DATABASE=production_test_cloud
CLOUD_MYSQL_USER=production_cloud_user
CLOUD_MYSQL_PASSWORD=<random-database-password>
CLOUD_MYSQL_ROOT_PASSWORD=<different-random-root-password>

CLOUD_MYSQL_PORT=3307
CLOUD_API_PORT=8100
CLOUD_FRONTEND_PORT=3100
CLOUD_PUBLIC_API_URL=https://ota.twentyfouri.net
```

保護設定檔：

```bash
chmod 600 .env.cloud.production
```

Cloud MySQL、Receiver 和 Frontend 的 port 在 Compose 中只綁定
`127.0.0.1`，不能直接從 Internet 連線；外部流量必須經過 Nginx。

## 五、啟動 Cloud 服務

正式 Server 不需要啟動工廠端服務，只啟動以下三項：

```bash
docker compose --env-file .env.cloud.production up -d --build \
  cloud-mysql cloud-receiver cloud-frontend
```

檢查：

```bash
docker compose ps
docker compose logs --tail=100 cloud-receiver
curl http://127.0.0.1:8100/health
curl -I http://127.0.0.1:3100/
```

## 六、加入登入密碼

Cloud 讀取 API 目前沒有應用程式帳號系統，因此正式環境先由 Nginx Basic Auth
保護 Cloud UI 與查詢 API。建立第一個帳號：

```bash
sudo htpasswd -c /etc/nginx/.production-test-users admin
```

之後新增帳號時不要使用 `-c`：

```bash
sudo htpasswd /etc/nginx/.production-test-users another-user
```

## 七、設定 Nginx

建立 `/etc/nginx/sites-available/production-test-cloud`：

```nginx
server {
    listen 80;
    server_name ota.twentyfouri.net;

    # 工廠端背景同步使用 API key，不使用瀏覽器 Basic Auth。
    location = /api/v1/sync/batch {
        proxy_pass http://127.0.0.1:8100/api/v1/sync/batch;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Cloud UI 呼叫的查詢 API 需要登入。
    location /api/ {
        auth_basic "Production Test Cloud";
        auth_basic_user_file /etc/nginx/.production-test-users;
        proxy_pass http://127.0.0.1:8100/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location = /health {
        proxy_pass http://127.0.0.1:8100/health;
    }

    location / {
        auth_basic "Production Test Cloud";
        auth_basic_user_file /etc/nginx/.production-test-users;
        proxy_pass http://127.0.0.1:3100/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

啟用並檢查：

```bash
sudo ln -s /etc/nginx/sites-available/production-test-cloud \
  /etc/nginx/sites-enabled/production-test-cloud
sudo nginx -t
sudo systemctl reload nginx
```

若同名 symlink 已存在，不需要再次執行 `ln -s`。

## 八、啟用 HTTPS

```bash
sudo certbot --nginx -d ota.twentyfouri.net
```

驗證：

```bash
curl https://ota.twentyfouri.net/health
curl -u admin https://ota.twentyfouri.net/api/v1/dashboard/stats
```

瀏覽器開啟：

```text
https://ota.twentyfouri.net/
```

## 九、將工廠端切換到正式 Cloud

在工廠電腦的環境檔設定：

```env
CLOUD_UPLOAD_ENABLED=true
CLOUD_API_URL=https://ota.twentyfouri.net/api/v1/sync/batch
CLOUD_API_KEY=<與 Server 相同的 API key>
CLOUD_SYNC_INTERVAL_SECONDS=10
```

只需重建工廠端 Backend：

```bash
docker compose --env-file .env.production up -d --build backend
```

本機 Factory UI 仍然是 <http://localhost:3000>，Cloud 紀錄改到
<https://ota.twentyfouri.net/> 查看。

## 十、端到端驗證

1. 在工廠端執行一次 Sensor 測試。
2. 等待至少一個同步週期，預設為 10 秒。
3. 在工廠端檢查 outbox：

```bash
docker compose exec mysql mysql -utestuser -ptestpassword production_test \
  -e "SELECT status, COUNT(*) FROM cloud_sync_outbox GROUP BY status;"
```

4. `UPLOADED` 數量應增加。
5. 登入 <https://ota.twentyfouri.net/>，確認新紀錄、台北時間、中英文切換與
   `+` 展開內容。

斷線重試測試：暫時停止正式 Cloud Receiver，在工廠端執行測試，再恢復服務。

```bash
# Cloud Server
docker compose stop cloud-receiver
docker compose start cloud-receiver
```

Receiver 恢復後，工廠端 outbox 應由 `FAILED` 自動轉成 `UPLOADED`，且 Cloud
不應產生重複測試紀錄。

## 十一、日常更新與備份

更新 Cloud：

```bash
cd /opt/production-test-system
git pull --ff-only
docker compose --env-file .env.cloud.production up -d --build \
  cloud-mysql cloud-receiver cloud-frontend
```

查看 log：

```bash
docker compose logs -f --tail=100 cloud-receiver
```

建立資料庫備份：

```bash
docker compose exec -T cloud-mysql mysqldump \
  sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
  > production_test_cloud_$(date +%Y%m%d_%H%M%S).sql
```

建議以排程定期備份到 Server 以外的位置，並定期實際測試還原流程。
