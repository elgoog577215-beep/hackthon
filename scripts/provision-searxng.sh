#!/usr/bin/env bash

set -Eeuo pipefail

STATE_DIR="${LINGZHI_SEARXNG_STATE_DIR:-/opt/lingzhi/state/searxng}"
SOURCE_DIR="${LINGZHI_SEARXNG_SOURCE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../deploy/searxng" && pwd)}"
COMPOSE_FILE="$STATE_DIR/compose.yml"
ENV_FILE="$STATE_DIR/.env"
CONFIG_DIR="$STATE_DIR/config"
CACHE_DIR="$STATE_DIR/cache"

log() {
    printf '[%s] %s\n' "$(date -Is)" "$*"
}

require_file() {
    local file="$1"
    if [ ! -f "$file" ]; then
        log "缺少 SearXNG 部署文件：$file"
        exit 1
    fi
}

if ! docker compose version >/dev/null 2>&1; then
    log "服务器未安装可用的 Docker Compose"
    exit 1
fi

require_file "$SOURCE_DIR/compose.yml"
require_file "$SOURCE_DIR/settings.yml"

install -d -m 700 "$STATE_DIR"
install -d -m 755 "$CONFIG_DIR"
install -d -m 750 "$CACHE_DIR"
install -m 644 "$SOURCE_DIR/compose.yml" "$COMPOSE_FILE"
install -m 644 "$SOURCE_DIR/settings.yml" "$CONFIG_DIR/settings.yml"
chown -R 977:977 "$CONFIG_DIR" "$CACHE_DIR"

if [ ! -f "$ENV_FILE" ]; then
    umask 077
    secret="$(openssl rand -hex 32)"
    printf 'SEARXNG_SECRET=%s\n' "$secret" > "$ENV_FILE.tmp"
    install -m 600 "$ENV_FILE.tmp" "$ENV_FILE"
    rm -f "$ENV_FILE.tmp"
else
    chmod 600 "$ENV_FILE"
fi

log "校验 SearXNG Compose 配置"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config --quiet

log "拉取并启动固定版本的 SearXNG"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" pull
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --remove-orphans

log "等待 SearXNG 本机健康检查"
ready=0
for _ in $(seq 1 30); do
    if curl --fail --silent --show-error --max-time 3 \
        http://127.0.0.1:8080/config >/dev/null; then
        ready=1
        break
    fi
    sleep 2
done
if [ "$ready" -ne 1 ]; then
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs --tail=120
    log "SearXNG /config 健康检查未通过"
    exit 1
fi

log "执行 JSON 搜索冒烟"
curl --fail --silent --show-error --max-time 12 \
    --request POST \
    --data 'q=Lingzhi retrieval smoke test' \
    --data 'format=json' \
    --data 'categories=general,science' \
    --data 'safesearch=2' \
    --data 'language=en' \
    http://127.0.0.1:8080/search \
    | python3 -c 'import json, sys; payload=json.load(sys.stdin); assert isinstance(payload.get("results"), list)'

log "SearXNG provisioning 完成，仅监听 127.0.0.1:8080"
