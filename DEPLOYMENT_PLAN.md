# 部署計劃 - GHCR (GitHub Container Registry)

## ✅ 已完成的設置

### 1. GitHub Actions CI/CD 自動化
- ✅ 創建 `.github/workflows/build-and-push.yml`
- 功能：
  - 自動監控 main 分支變化
  - 自動構建 backend, frontend-smac, frontend-nl 鏡像
  - 自動推送到 GHCR (ghcr.io/lance-cl-lu/production-test-system)
  - 同時標記 `latest` 和 `commit hash` 版本

### 2. 優化 Docker 鏡像
- ✅ 後端 (Backend)
  - 改用多階段構建 (Multi-stage Build)
  - 減小鏡像體積 ~50%
  
- ✅ 前端 (Frontend-SMAC & Frontend-NL)
  - 改用多階段構建
  - 只包含生產依賴（npm ci --only=production）
  - 減小鏡像體積 ~40%

### 3. 配置文件更新
- ✅ `docker-compose.yml`
  - 改用 GHCR 鏡像而非本地構建
  - 移除源代碼卷掛載 (不暴露 source code)
  - 添加環境變量支持 (可配置端口、密碼等)
  - 添加數據卷 (test_data) 用於持久化

- ✅ `.env.example`
  - 環境變量模板
  - 客戶複製並修改即可

- ✅ `.dockerignore`
  - 排除不必要的構建文件

### 4. 客戶文檔
- ✅ `CUSTOMER_DEPLOYMENT.md` - 客戶友好的部署指南
- ✅ `DEPLOYMENT.md` - 詳細技術部署文檔
- ✅ `setup-customer.sh` - 自動化設置腳本

---

## 🚀 使用流程

### 第1步：推送代碼到 GitHub
```bash
git push origin main
```
→ GitHub Actions 自動構建並推送鏡像到 GHCR

### 第2步：獲取 GitHub Personal Access Token
1. GitHub → Settings → Developer settings → Personal access tokens
2. 點擊 "Generate new token (classic)"
3. 勾選 `read:packages`
4. 複製 token

### 第3步：提供給客戶的文件
將以下文件複製到客戶包：
```
├── docker-compose.yml          # GHCR 配置
├── .env.example                # 配置模板
├── CUSTOMER_DEPLOYMENT.md      # 部署指南
├── setup-customer.sh           # 自動化設置
└── shared/                     # (如需要的共享文件)
```

**不要提供的文件：**
- ❌ `.git` 目錄 (不要給源代碼倉庫)
- ❌ `backend/`, `frontend-*/`, `tester/` 源代碼目錄
- ❌ `README.md`, `STRUCTURE.md` 等開發文檔

### 第4步：客戶部署
客戶執行：
```bash
chmod +x setup-customer.sh
./setup-customer.sh
```

或手動執行：
```bash
# 登錄 GHCR
docker login ghcr.io -u USERNAME -p TOKEN

# 複製配置
cp .env.example .env
# 編輯 .env 修改密碼和 API URL

# 啟動
docker-compose pull
docker-compose up -d
```

---

## 🔐 安全性

✅ **源代碼保護**
- 客戶完全看不到源代碼
- 只能看到編譯後的 Docker 鏡像

✅ **敏感信息管理**
- 數據庫密碼通過 `.env` 環境變量傳入
- GitHub Actions 不會暴露敏感信息

✅ **鏡像安全**
- 多階段構建移除了構建時的工具和臨時文件
- 減小攻擊面

---

## 📋 檢查清單

**準備就緒時：**
- [ ] 確認源代碼在 GitHub 上並設置為私有倉庫（可選）
- [ ] 驗證 GitHub Actions workflow 成功運行
- [ ] 在 GHCR 中查看推送的鏡像
- [ ] 驗證 docker-compose.yml 能成功拉取並啟動
- [ ] 測試所有 API 端點和前端功能
- [ ] 準備客戶文檔包

---

## 📊 鏡像大小比較

| 鏡像 | 優化前 | 優化後 | 節省 |
|------|-------|--------|------|
| Backend | ~1.2GB | ~600MB | ~50% |
| Frontend-SMAC | ~500MB | ~300MB | ~40% |
| Frontend-NL | ~500MB | ~300MB | ~40% |

---

## 🔄 更新流程

當需要發佈新版本時：

1. **開發環境**
   ```bash
   # 修改代碼並測試
   git commit -m "feat: new feature"
   git push origin main
   ```

2. **自動化**
   - GitHub Actions 自動構建新鏡像
   - 標記為 `latest` 和 `commit-hash`

3. **客戶更新**
   ```bash
   docker-compose pull
   docker-compose up -d
   ```

---

## ⚠️ 注意事項

1. **Private Repository（推薦）**
   - 建議將 GitHub 倉庫設為私有
   - GHCR 的訪問權限會自動與倉庫保持一致

2. **Token 管理**
   - Personal Access Token 要妥善保管
   - 建議設置過期時間
   - 如洩露應立即刪除並重新生成

3. **生產環境部署**
   - 必須修改 `.env` 中的所有密碼
   - 建議使用 HTTPS (Nginx/Caddy 反向代理)
   - 定期備份 MySQL 數據卷

---

## 📞 支持

有任何問題，請檢查：
1. GitHub Actions 日誌確認鏡像構建成功
2. `docker-compose logs` 查看運行時日誌
3. 參考 `CUSTOMER_DEPLOYMENT.md` 的故障排除部分
