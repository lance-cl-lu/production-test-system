# 資料庫架構

## 資料表

### test_records (測試記錄)

| 欄位 | 類型 | 說明 | 約束 |
|------|------|------|------|
| id | INTEGER | 主鍵 | PRIMARY KEY, AUTO_INCREMENT |
| device_id | VARCHAR(100) | 設備ID | NOT NULL, INDEX |
| product_name | VARCHAR(200) | 產品名稱 | NOT NULL |
| serial_number | VARCHAR(100) | 序號 | NOT NULL, UNIQUE, INDEX |
| test_station | VARCHAR(100) | 測試站別 | NOT NULL |
| test_result | VARCHAR(20) | 測試結果 (PASS/FAIL) | NOT NULL |
| test_time | DATETIME | 測試時間 | NOT NULL |
| test_data | TEXT | 測試數據 (JSON格式) | - |
| voltage | FLOAT | 電壓 | - |
| current | FLOAT | 電流 | - |
| temperature | FLOAT | 溫度 | - |
| uploaded_to_cloud | BOOLEAN | 是否已上傳雲端 | DEFAULT FALSE |
| created_at | DATETIME | 建立時間 | DEFAULT NOW() |
| updated_at | DATETIME | 更新時間 | DEFAULT NOW(), ON UPDATE NOW() |

### cloud_upload_logs (雲端上傳日誌)

| 欄位 | 類型 | 說明 | 約束 |
|------|------|------|------|
| id | INTEGER | 主鍵 | PRIMARY KEY, AUTO_INCREMENT |
| upload_time | DATETIME | 上傳時間 | DEFAULT NOW() |
| records_count | INTEGER | 上傳記錄數 | - |
| status | VARCHAR(20) | 狀態 (SUCCESS/FAILED) | - |
| error_message | TEXT | 錯誤訊息 | - |

## 索引

- `test_records.device_id` - 加速依設備查詢
- `test_records.serial_number` - 唯一索引，防止重複
- `test_records.id` - 主鍵索引

## 關聯

目前版本為簡化設計，沒有外鍵關聯。未來可擴展:
- 設備資料表 (devices)
- 產品資料表 (products)
- 測試站別資料表 (test_stations)

## 查詢範例

### 1. 查詢特定設備的所有測試記錄
```sql
SELECT * FROM test_records 
WHERE device_id = 'TESTER_001' 
ORDER BY test_time DESC;
```

### 2. 查詢今日測試統計
```sql
SELECT 
    test_result,
    COUNT(*) as count
FROM test_records
WHERE DATE(test_time) = CURDATE()
GROUP BY test_result;
```

### 3. 查詢良率
```sql
SELECT 
    COUNT(CASE WHEN test_result = 'PASS' THEN 1 END) * 100.0 / COUNT(*) as pass_rate
FROM test_records
WHERE test_time >= DATE_SUB(NOW(), INTERVAL 7 DAY);
```

### 4. 查詢未上傳雲端的記錄
```sql
SELECT * FROM test_records
WHERE uploaded_to_cloud = FALSE
ORDER BY test_time ASC;
```

## 備份與還原

### 備份
```bash
docker exec production_test_db mysqldump -u testuser -ptestpassword production_test > backup.sql
```

### 還原
```bash
docker exec -i production_test_db mysql -u testuser -ptestpassword production_test < backup.sql
```
