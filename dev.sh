#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
ENV_FILE="$ROOT_DIR/.env"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
EVOLUTION_DEMO_MODE="${EVOLUTION_DEMO_MODE:-0}"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    local exit_code="$1"
    trap - EXIT INT TERM
    if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    [ -z "$FRONTEND_PID" ] || wait "$FRONTEND_PID" 2>/dev/null || true
    [ -z "$BACKEND_PID" ] || wait "$BACKEND_PID" 2>/dev/null || true
    exit "$exit_code"
}

trap 'cleanup $?' EXIT
trap 'cleanup 130' INT TERM

fail() {
    printf '启动失败：%s\n' "$1" >&2
    exit 1
}

port_is_busy() {
    lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

wait_for_url() {
    local name="$1"
    local url="$2"
    local pid="$3"
    local attempt
    for attempt in $(seq 1 80); do
        if ! kill -0 "$pid" 2>/dev/null; then
            fail "$name 进程提前退出"
        fi
        if curl --fail --silent --show-error --max-time 1 "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.25
    done
    fail "$name 在 20 秒内没有通过健康检查：$url"
}

if [[ ! "$EVOLUTION_DEMO_MODE" =~ ^(1|true|yes|on)$ ]]; then
    [ -f "$ENV_FILE" ] || fail "缺少 $ENV_FILE，请先配置 AI_API_KEY"
    grep -Eq '^[[:space:]]*AI_API_KEY[[:space:]]*=[[:space:]]*[^[:space:]#]+' "$ENV_FILE" \
        || fail "$ENV_FILE 中缺少有效的 AI_API_KEY"
fi

if [ -x "$BACKEND_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$BACKEND_DIR/.venv/bin/python"
else
    PYTHON_BIN="$(command -v python3 || true)"
fi
[ -n "$PYTHON_BIN" ] || fail "未找到 Python 3"
"$PYTHON_BIN" -c 'import fastapi, uvicorn, openai' >/dev/null 2>&1 \
    || fail "后端依赖不完整，请在 backend/.venv 中安装 requirements.txt"

command -v npm >/dev/null 2>&1 || fail "未找到 npm"
[ -x "$FRONTEND_DIR/node_modules/.bin/vite" ] \
    || fail "前端依赖未安装，请先在 frontend 目录执行 npm install"

port_is_busy "$BACKEND_PORT" && fail "后端端口 $BACKEND_PORT 已被占用"
port_is_busy "$FRONTEND_PORT" && fail "前端端口 $FRONTEND_PORT 已被占用"

mkdir -p "$BACKEND_DIR/data"

printf '正在启动后端：http://%s:%s\n' "$BACKEND_HOST" "$BACKEND_PORT"
(
    cd "$BACKEND_DIR"
    exec "$PYTHON_BIN" -m uvicorn main:app \
        --host "$BACKEND_HOST" \
        --port "$BACKEND_PORT" \
        --reload
) &
BACKEND_PID=$!

wait_for_url "后端" "http://$BACKEND_HOST:$BACKEND_PORT/health" "$BACKEND_PID"

printf '正在启动前端：http://%s:%s\n' "$FRONTEND_HOST" "$FRONTEND_PORT"
(
    cd "$FRONTEND_DIR"
    export VITE_API_PROXY_TARGET="http://$BACKEND_HOST:$BACKEND_PORT"
    exec npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
) &
FRONTEND_PID=$!

wait_for_url "前端" "http://$FRONTEND_HOST:$FRONTEND_PORT/" "$FRONTEND_PID"

printf '\n本地环境已就绪\n'
printf '前端：http://%s:%s\n' "$FRONTEND_HOST" "$FRONTEND_PORT"
printf '后端：http://%s:%s\n' "$BACKEND_HOST" "$BACKEND_PORT"
printf 'API 文档：http://%s:%s/docs\n' "$BACKEND_HOST" "$BACKEND_PORT"
printf '按 Ctrl+C 停止全部服务\n\n'

while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
    sleep 1
done

fail "前端或后端进程意外退出"
