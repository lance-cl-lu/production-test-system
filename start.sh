#!/bin/bash

# 默認開發模式
COMPOSE_FILE="docker-compose.yml"

# 如果傳入 'prod' 參數則使用生產配置
if [ "$1" = "prod" ]; then
    COMPOSE_FILE="docker-compose.prod.yml"
    echo "🚀 啟動生產測試系統 (Docker Compose - 生產模式)..."
else
    echo "🚀 啟動生產測試系統 (Docker Compose - 開發模式)..."
fi

echo ""

# 啟動所有 Docker 容器
echo "📦 啟動所有服務 (MySQL + Backend + Frontend)..."
docker-compose -f "$COMPOSE_FILE" up -d --build

echo ""
echo "⏳ 等待服務啟動..."
sleep 5

echo ""
echo "✅ 系統啟動完成！"
echo ""
echo "📍 服務網址:"
echo "   前端 SMAC: http://localhost:3000"
echo "   前端 NL:   http://localhost:3001"
echo "   後端 API:  http://localhost:8000"
echo "   API 文檔:  http://localhost:8000/docs"
echo ""
echo "💡 提示:"
echo "   - 開發模式: ./start.sh"
echo "   - 生產模式: ./start.sh prod"
echo "   - 查看日誌: docker-compose logs -f backend"
echo "   MySQL: localhost:3306"
echo ""
echo "💡 提示:"
echo "   - 查看所有容器狀態: docker compose ps"
echo "   - 查看後端日誌: docker compose logs -f backend"
echo "   - 查看前端日誌: docker compose logs -f frontend"
echo "   - 查看 MySQL 日誌: docker compose logs -f mysql"
echo "   - 停止服務: ./stop.sh"
echo ""
