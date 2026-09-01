#!/bin/bash

# 優先使用 Docker Compose v2 (docker compose)，找不到才退回 v1 (docker-compose)
if docker compose version >/dev/null 2>&1; then
    COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE=(docker-compose)
else
    echo "❌ 找不到 Docker Compose，請先安裝 Docker Desktop。"
    exit 1
fi

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
"${COMPOSE[@]}" -f "$COMPOSE_FILE" down

echo ""
echo "✅ 系統已停止"
echo ""
echo "💡 提示:"
echo "   - 完全清除容器與資料卷: ${COMPOSE[*]} -f $COMPOSE_FILE down -v"
echo "   - 重新啟動: ./start.sh"
echo ""
