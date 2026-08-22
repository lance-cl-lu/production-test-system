# Local Cloud Simulation

This stack keeps the factory MySQL database authoritative and asynchronously syncs
Sensor sessions to an isolated cloud-like API and MySQL database.

## Start

```bash
docker compose --env-file .env.cloud.example up -d --build
```

Open:

- Factory UI: http://localhost:3000
- Cloud records UI: http://localhost:3100
- Cloud Receiver API docs: http://localhost:8100/docs
- Cloud Receiver health: http://localhost:8100/health

The simulation read APIs are intentionally unauthenticated for local development.
Add user authentication and HTTPS before exposing the receiver or frontend publicly.

Set `CLOUD_UPLOAD_ENABLED=true`. The backend scans the durable outbox every 10
seconds. Existing Sensor sessions are queued automatically the first time sync runs.

## Verify isolation and sync

```bash
docker compose exec mysql mysql -utestuser -ptestpassword production_test \
  -e "SELECT status, COUNT(*) FROM cloud_sync_outbox GROUP BY status"

docker compose exec cloud-mysql mysql -uclouduser -pcloudpassword production_test_cloud \
  -e "SELECT test_result, COUNT(*) FROM cloud_sensor_test_runs GROUP BY test_result"
```

Stop `cloud-receiver`, run a factory test, and start it again to verify retry:

```bash
docker compose stop cloud-receiver
docker compose start cloud-receiver
```

## Later deployment

Deploy the same `cloud-receiver` and `cloud-frontend` images. Replace the receiver's
`DATABASE_URL` with managed MySQL, use a generated `CLOUD_API_KEY`, terminate HTTPS
at the cloud load balancer, and point the factory `CLOUD_API_URL` to that HTTPS URL.
The local factory database and test workflow remain unchanged during an outage.
