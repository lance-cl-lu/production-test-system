#!/bin/bash

# Production Test System - 客戶部署設置腳本

set -e

echo "🚀 生產測試系統 - 部署設置"
echo "================================"
echo ""

# 檢查 Docker
if ! command -v docker &> /dev/null; then
    echo "❌ 錯誤: 未安裝 Docker"
    echo "請訪問 https://docs.docker.com/get-docker/ 安裝 Docker"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ 錯誤: 未安裝 Docker Compose"
    echo "請訪問 https://docs.docker.com/compose/install/ 安裝 Docker Compose"
    exit 1
fi

echo "✅ Docker 和 Docker Compose 已安裝"
echo ""

# 檢查 .env 文件
if [ ! -f .env ]; then
    echo "📝 創建 .env 文件..."
    cp .env.example .env
    echo "✅ .env 文件已創建"
    echo ""
    echo "⚠️  請編輯 .env 文件並修改以下敏感信息:"
    echo "   - MYSQL_ROOT_PASSWORD"
    echo "   - MYSQL_PASSWORD"
    echo "   - REACT_APP_API_URL (設置為你的伺服器地址)"
    echo ""
    read -p "按 Enter 鍵繼續..."
fi

# GitHub Login
echo ""
echo "🔐 登錄到 GitHub Container Registry..."
echo "需要你的 GitHub 用戶名和 Personal Access Token"
echo "Token 獲取: GitHub → Settings → Developer settings → Personal access tokens"
echo ""

read -p "GitHub 用戶名: " github_user
read -sp "Personal Access Token: " github_token
echo ""

if docker login ghcr.io -u "$github_user" -p "$github_token"; then
    echo "✅ 登錄成功"
else
    echo "❌ 登錄失敗，請檢查用戶名和 token"
    exit 1
fi

echo ""
echo "📥 拉取最新 Docker 鏡像..."
docker-compose pull

echo ""
echo "🎬 啟動應用..."
docker-compose up -d

echo ""
echo "⏳ 等待服務啟動..."
sleep 5

echo ""
echo "✅ 部署完成！"
echo ""
echo "📋 服務狀態:"
docker-compose ps
echo ""
echo "🌐 訪問應用:"
echo "   - Frontend-SMAC: http://localhost:3000"
echo "   - Frontend-NL:   http://localhost:3001"
echo "   - API 文檔:      http://localhost:8000/docs"
echo ""
echo "📖 更多幫助請參考 CUSTOMER_DEPLOYMENT.md"
