#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FLASH_AGENT_PID_FILE="${TMPDIR:-/tmp}/production-test-flash-agent.pid"
FLASH_AGENT_LOG_FILE="${TMPDIR:-/tmp}/production-test-flash-agent.log"
PYTHON_COMMAND=()

if command -v python3 >/dev/null 2>&1; then
    PYTHON_COMMAND=(python3)
elif command -v python >/dev/null 2>&1; then
    PYTHON_COMMAND=(python)
elif command -v py >/dev/null 2>&1; then
    PYTHON_COMMAND=(py -3)
fi

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
ENV_FILE=""

# 如果傳入 'prod' 參數則使用生產配置
if [ "$1" = "prod" ]; then
    COMPOSE_FILE="docker-compose.prod.yml"
    ENV_FILE="env.factory.production"
    if [ ! -f "$ENV_FILE" ]; then
        echo "❌ 找不到生產環境設定檔: $ENV_FILE"
        exit 1
    fi
    echo "🚀 啟動生產測試系統 (Docker Compose - 生產模式)..."
else
    echo "🚀 啟動生產測試系統 (Docker Compose - 開發模式)..."
fi

echo ""

# 確認 Docker daemon 可連線
if ! docker info >/dev/null 2>&1; then
    echo "❌ 無法連線到 Docker daemon。"
    echo "   請先啟動 Docker Desktop (open -a Docker)，待其顯示 Running 後再重試。"
    exit 1
fi

# 啟動所有 Docker 容器
echo "📦 啟動預設服務 (MySQL + Backend + Frontend SMAC)..."
COMPOSE_ENV_ARGS=()
if [ -n "$ENV_FILE" ]; then
    COMPOSE_ENV_ARGS=(--env-file "$ENV_FILE")
fi
if ! "${COMPOSE[@]}" "${COMPOSE_ENV_ARGS[@]}" -f "$COMPOSE_FILE" up -d --build; then
    echo ""
    echo "❌ 服務啟動失敗；上方為 Docker Compose 的錯誤訊息。"
    echo "   請先排除錯誤後再重新執行 ./start.sh。"
    exit 1
fi

echo ""
echo "⏳ 等待服務就緒 (前端開發模式首次編譯較久)..."

# 輪詢各服務直到有 HTTP 回應，最多等 300 秒
wait_for() {
    local name="$1" url="$2" timeout=300 elapsed=0
    while [ "$elapsed" -lt "$timeout" ]; do
        if curl -s -o /dev/null --max-time 3 "$url"; then
            echo "   ✅ $name 就緒 (${elapsed}s)"
            return 0
        fi
        sleep 3
        elapsed=$((elapsed + 3))
    done
    echo "   ⚠️  $name 在 ${timeout}s 內未回應，請查看: ${COMPOSE[*]} logs -f"
    return 1
}

wait_for "後端 API  (8000)" "http://localhost:8000/docs"
wait_for "前端 SMAC (3000)" "http://localhost:3000/"

if curl -fsS "http://127.0.0.1:8765/health" 2>/dev/null | grep -q '"flash_script":"flash_smac.sh"'; then
    echo "   ✅ 主機燒錄服務已就緒 (8765)"
else
    echo "🔌 啟動主機 ST-Link 燒錄服務..."
    if [ -f "${FLASH_AGENT_PID_FILE}" ]; then
        OLD_FLASH_AGENT_PID="$(cat "${FLASH_AGENT_PID_FILE}")"
        kill "${OLD_FLASH_AGENT_PID}" 2>/dev/null || true
        sleep 1
    fi
    if [ ${#PYTHON_COMMAND[@]} -eq 0 ]; then
        echo "   ⚠️ 找不到 Python；請安裝 Python 3 後重新執行 ./start.sh。"
    else
        nohup "${PYTHON_COMMAND[@]}" "${SCRIPT_DIR}/flash_agent.py" >>"${FLASH_AGENT_LOG_FILE}" 2>&1 </dev/null &
        echo $! >"${FLASH_AGENT_PID_FILE}"
        for _ in {1..10}; do
            if curl -fsS "http://127.0.0.1:8765/health" >/dev/null 2>&1; then
                echo "   ✅ 主機燒錄服務已就緒 (8765)"
                break
            fi
            sleep 1
        done
        if ! curl -fsS "http://127.0.0.1:8765/health" 2>/dev/null | grep -q '"flash_script":"flash_smac.sh"'; then
            echo "   ⚠️ 主機燒錄服務啟動失敗；請查看 ${FLASH_AGENT_LOG_FILE}"
        fi
    fi
fi

echo ""
echo "✅ 系統啟動完成！"
echo ""
echo "📍 服務網址:"
echo "   前端 SMAC: http://localhost:3000"
echo "   後端 API:  http://localhost:8000"
echo "   API 文檔:  http://localhost:8000/docs"
echo "   NL 前端需手動啟動: ${COMPOSE[*]} -f $COMPOSE_FILE --profile frontend-nl up -d --build frontend-nl"
echo ""
echo "💡 提示:"
echo "   - 開發模式: ./start.sh"
echo "   - 生產模式: ./start.sh prod"
echo "   - 查看日誌: ${COMPOSE[*]} logs -f backend"
echo "   MySQL: localhost:3306"
echo ""
echo "💡 提示:"
echo "   - 查看所有容器狀態: ${COMPOSE[*]} ps"
echo "   - 查看後端日誌: ${COMPOSE[*]} logs -f backend"
echo "   - 查看前端日誌: ${COMPOSE[*]} logs -f frontend"
echo "   - 查看 MySQL 日誌: ${COMPOSE[*]} logs -f mysql"
echo "   - 停止服務: ./stop.sh"
echo ""
