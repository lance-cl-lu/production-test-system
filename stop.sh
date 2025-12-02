#!/bin/bash

echo "⏹️  停止生產測試系統 (Docker Compose 模式)..."
echo ""

# 停止所有 Docker 容器
echo "停止所有容器..."
docker compose down

echo ""
echo "✅ 系統已停止"
echo ""
echo "💡 提示:"
echo "   - 完全清除容器與資料卷: docker compose down -v"
echo "   - 重新啟動: ./start.sh"
echo ""
