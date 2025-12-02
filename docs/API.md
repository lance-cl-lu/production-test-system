# API 文檔

## Base URL
```
http://localhost:8000
```

## 測試記錄 API

### 1. 建立測試記錄
**POST** `/api/test-records/`

**Request Body:**
```json
{
  "device_id": "TESTER_001",
  "product_name": "產品型號A",
  "serial_number": "SN202512020001",
  "test_station": "STATION_A",
  "test_result": "PASS",
  "test_time": "2025-12-02T10:30:00",
  "test_data": "{\"voltage_ok\": true, \"current_ok\": true}",
  "voltage": 5.01,
  "current": 0.50,
  "temperature": 25.5
}
```

**Response:** `201 Created`
```json
{
  "id": 1,
  "device_id": "TESTER_001",
  "product_name": "產品型號A",
  "serial_number": "SN202512020001",
  "test_station": "STATION_A",
  "test_result": "PASS",
  "test_time": "2025-12-02T10:30:00",
  "test_data": "{\"voltage_ok\": true, \"current_ok\": true}",
  "voltage": 5.01,
  "current": 0.50,
  "temperature": 25.5,
  "uploaded_to_cloud": false,
  "created_at": "2025-12-02T10:30:00",
  "updated_at": "2025-12-02T10:30:00"
}
```

### 2. 取得測試記錄列表
**GET** `/api/test-records/`

**Query Parameters:**
- `skip` (int): 跳過筆數，預設 0
- `limit` (int): 限制筆數，預設 100
- `device_id` (string): 篩選設備 ID
- `test_result` (string): 篩選測試結果 (PASS/FAIL)
- `start_date` (datetime): 開始日期
- `end_date` (datetime): 結束日期

**Example:**
```
GET /api/test-records/?device_id=TESTER_001&test_result=PASS&limit=50
```

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "device_id": "TESTER_001",
    "serial_number": "SN202512020001",
    ...
  }
]
```

### 3. 取得單筆測試記錄
**GET** `/api/test-records/{record_id}`

**Response:** `200 OK`

### 4. 更新測試記錄
**PUT** `/api/test-records/{record_id}`

**Request Body:**
```json
{
  "test_result": "FAIL",
  "test_data": "{\"note\": \"重新測試\"}"
}
```

**Response:** `200 OK`

### 5. 刪除測試記錄
**DELETE** `/api/test-records/{record_id}`

**Response:** `204 No Content`

## WebSocket

### 連接
**WS** `/ws`

### 訊息格式

**接收訊息:**
```json
{
  "type": "test_result",
  "data": {
    "id": 1,
    "serial_number": "SN202512020001",
    "test_result": "PASS",
    ...
  },
  "timestamp": "2025-12-02T10:30:00"
}
```

**發送訊息:**
```json
{
  "action": "ping",
  "data": {}
}
```

## 系統 API

### 健康檢查
**GET** `/health`

**Response:** `200 OK`
```json
{
  "status": "healthy",
  "cloud_upload_enabled": false
}
```

### API 文檔
**GET** `/docs` - Swagger UI
**GET** `/redoc` - ReDoc

## 錯誤回應

### 400 Bad Request
```json
{
  "detail": "Invalid request data"
}
```

### 404 Not Found
```json
{
  "detail": "Record not found"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Internal server error"
}
```
