#!/bin/bash

echo "🚀 啟動生產測試系統 (Docker Compose 全容器化模式)..."
echo ""

# 啟動所有 Docker 容器
echo "📦 啟動所有服務 (MySQL + Backend + Frontend)..."
docker compose up -d --build

echo ""
echo "⏳ 等待服務啟動..."
sleep 5

echo ""
echo "✅ 系統啟動完成！"
echo ""
echo "📍 服務網址:"
echo "   前端: http://localhost:3000"
echo "   後端 API: http://localhost:8000"
echo "   API 文檔: http://localhost:8000/docs"
echo "   MySQL: localhost:3306"
echo ""
echo "💡 提示:"
echo "   - 查看所有容器狀態: docker compose ps"
echo "   - 查看後端日誌: docker compose logs -f backend"
echo "   - 查看前端日誌: docker compose logs -f frontend"
echo "   - 查看 MySQL 日誌: docker compose logs -f mysql"
echo "   - 停止服務: ./stop.sh"
echo ""
