# UID 搜尋測試 - 快速啟動指南

## 問題已解決 ✓

404 錯誤是因為後端容器需要重啟以載入新的 `/api/pcba/uid-search` 端點。

## 快速測試流程

### 1. 確保後端已重啟（如果剛修改程式碼）

```bash
cd /Users/lance/Documents/GitHub/production-test-system
docker-compose restart backend
sleep 3
```

### 2. 驗證端點可用

```bash
curl -X POST http://localhost:8000/api/pcba/uid-search \
  -H "Content-Type: application/json" \
  -d '{"uid":"TEST-123"}'

# 預期輸出：
# {"status":"accepted","uid":"TEST-123","message":"UID broadcasted to frontend"}
```

### 3. 啟動前端（如果尚未啟動）

```bash
cd frontend-nl
npm start
# 在瀏覽器開啟 http://localhost:3001
```

### 4. 執行完整測試

1. **前端操作**：
   - 進入 `http://localhost:3001`
   - 點選「PCBA進料檢驗」
   - 點擊「搜尋」按鈕

2. **執行 uid_searcher**：
   ```bash
   cd tester
   ./uid_searcher
   # 或指定 UID
   ./uid_searcher NL-20251204-9999
   ```

3. **確認結果**：
   - ✓ 前端 UID 欄位自動填入
   - ✓ 序號欄位同步更新
   - ✓ 顯示「UID 已接收」訊息

4. **開始測試**：
   - 點擊「開始測試」按鈕
   - 測試流程維持原有邏輯

## 測試成功範例

```
lance@LudeMac-mini tester % ./uid_searcher NL-20251204-TEST
Using specified UID: NL-20251204-TEST
Sending UID to backend: NL-20251204-TEST
API URL: http://localhost:8000/api/pcba/uid-search
Payload: {"uid":"NL-20251204-TEST"}
Response: {"status":"accepted","uid":"NL-20251204-TEST","message":"UID broadcasted to frontend"}
HTTP Response Code: 200
✓ UID sent successfully

✓ UID search completed successfully
  The UID should now appear in the frontend UI
```

## 常用指令

```bash
# 重新編譯（如果修改程式碼）
make uid_searcher

# 自動產生 UID
./uid_searcher

# 指定 UID
./uid_searcher NL-20251204-0001

# 測試後端健康狀態
curl http://localhost:8000/health

# 查看後端日誌
docker-compose logs -f backend

# 重啟所有服務
docker-compose restart
```

## 完整架構流程

```
前端點擊「搜尋」
    ↓
等待 UID (searchingUid = true)
    ↓
執行 ./uid_searcher
    ↓
POST /api/pcba/uid-search
    ↓
後端廣播 WebSocket {type: "uid_search", data: {uid: "..."}}
    ↓
前端接收並填入 UID
    ↓
點擊「開始測試」
    ↓
正常測試流程（維持原有邏輯）
```

## 下一步

所有功能已正常運作！可以：
- 整合實際硬體讀取 UID
- 新增更多測試項目
- 客製化 UID 格式驗證
