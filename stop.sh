#!/bin/bash

# 默認開發模式
COMPOSE_FILE="docker-compose.yml"

# 如果傳入 'prod' 參數則使用生產配置
if [ "$1" = "prod" ]; then
    COMPOSE_FILE="docker-compose.prod.yml"
    echo "⏹️  停止生產測試系統 (Docker Compose - 生產模式)..."
else
    echo "⏹️  停止生產測試系統 (Docker Compose - 開發模式)..."
fi

echo ""

# 停止所有 Docker 容器
echo "停止所有容器..."
docker-compose -f "$COMPOSE_FILE" down

echo ""
echo "✅ 系統已停止"
echo ""
echo "💡 提示:"
echo "   - 完全清除容器與資料卷: docker-compose -f $COMPOSE_FILE down -v"
echo "   - 重新啟動: ./start.sh"
echo ""
