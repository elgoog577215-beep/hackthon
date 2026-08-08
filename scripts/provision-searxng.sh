#!/usr/bin/env bash

set -Eeuo pipefail

STATE_DIR="${LINGZHI_SEARXNG_STATE_DIR:-/opt/lingzhi/state/searxng}"
SOURCE_DIR="${LINGZHI_SEARXNG_SOURCE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../deploy/searxng" && pwd)}"
COMPOSE_FILE="$STATE_DIR/compose.yml"
ENV_FILE="$STATE_DIR/.env"
CONFIG_DIR="$STATE_DIR/config"
CACHE_DIR="$STATE_DIR/cache"
IMAGE_ARCHIVE="$SOURCE_DIR/searxng-image.tar.gz"
IMAGE_CHECKSUM="$SOURCE_DIR/searxng-image.tar.gz.sha256"
ARCHIVE_IMAGE_TAG="lingzhi/searxng:f4c8e59de166"
APP_ENV_FILE="${LINGZHI_APP_ENV_FILE:-/opt/lingzhi/state/.env}"
APP_SERVICE_NAME="${LINGZHI_APP_SERVICE_NAME:-lingzhi}"
APP_HEALTH_URL="${LINGZHI_APP_HEALTH_URL:-http://127.0.0.1:7862/api/health}"
RETRIEVAL_MODE="${LINGZHI_WEB_RETRIEVAL_MODE:-allowlist}"
RETRIEVAL_USER_IDS="${LINGZHI_WEB_RETRIEVAL_USER_IDS:-}"
app_env_backup=""
app_env_changed=0

log() {
    printf '[%s] %s\n' "$(date -Is)" "$*"
}

require_file() {
    local file="$1"
    if [ ! -f "$file" ]; then
        log "缺少部署文件：$file"
        exit 1
    fi
}

upsert_env_value() {
    local file="$1"
    local key="$2"
    local value="$3"
    local temporary

    temporary="$(mktemp "${file}.tmp.XXXXXX")"
    awk -v key="$key" 'index($0, key "=") != 1 { print }' "$file" > "$temporary"
    printf '%s=%s\n' "$key" "$value" >> "$temporary"
    install -m 600 "$temporary" "$file"
    rm -f "$temporary"
}

rollback_app_env() {
    local status="$?"
    if [ "$status" -ne 0 ] && [ "$app_env_changed" -eq 1 ] && [ -f "$app_env_backup" ]; then
        log "SearXNG 激活失败，回滚应用联网配置"
        install -m 600 "$app_env_backup" "$APP_ENV_FILE"
        systemctl restart "$APP_SERVICE_NAME" || true
    fi
    if [ -n "$app_env_backup" ]; then
        rm -f "$app_env_backup"
    fi
    exit "$status"
}

trap rollback_app_env EXIT

if ! docker compose version >/dev/null 2>&1; then
    log "服务器未安装可用的 Docker Compose"
    exit 1
fi

require_file "$SOURCE_DIR/compose.yml"
require_file "$SOURCE_DIR/settings.yml"
require_file "$APP_ENV_FILE"

if [ "$RETRIEVAL_MODE" != "off" ] \
    && [ "$RETRIEVAL_MODE" != "allowlist" ] \
    && [ "$RETRIEVAL_MODE" != "on" ]; then
    log "LINGZHI_WEB_RETRIEVAL_MODE 必须为 off、allowlist 或 on"
    exit 1
fi
if ! [[ "$RETRIEVAL_USER_IDS" =~ ^[A-Za-z0-9_.,:-]*$ ]]; then
    log "LINGZHI_WEB_RETRIEVAL_USER_IDS 包含非法字符"
    exit 1
fi

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

if docker image inspect "$ARCHIVE_IMAGE_TAG" >/dev/null 2>&1; then
    log "复用服务器已校验加载的固定摘要镜像"
else
    require_file "$IMAGE_ARCHIVE"
    require_file "$IMAGE_CHECKSUM"
    log "校验并加载 GitHub Runner 传输的固定摘要镜像"
    (
        cd "$SOURCE_DIR"
        sha256sum --check --strict "$(basename "$IMAGE_CHECKSUM")"
    )
    gzip --decompress --stdout "$IMAGE_ARCHIVE" | docker image load
fi
image_id="$(docker image inspect --format '{{.Id}}' "$ARCHIVE_IMAGE_TAG")"
if ! [[ "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    log "无法确认已加载的 SearXNG 镜像"
    exit 1
fi
upsert_env_value "$ENV_FILE" "SEARXNG_IMAGE" "$image_id"

log "校验 SearXNG Compose 配置"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config --quiet

log "从本地镜像启动固定版本的 SearXNG"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --remove-orphans --force-recreate --pull never

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
smoke_ready=0
for attempt in $(seq 1 3); do
    if curl --fail --silent --show-error --max-time 12 \
        --request POST \
        --data-urlencode 'q=Unity MonoBehaviour GameObject 中文教程' \
        --data 'format=json' \
        --data 'categories=general' \
        --data 'safesearch=2' \
        --data 'language=zh-CN' \
        --data 'timeout_limit=4' \
        http://127.0.0.1:8080/search \
        | python3 -c 'import json, sys; payload=json.load(sys.stdin); assert isinstance(payload.get("results"), list); assert payload.get("results")'; then
        smoke_ready=1
        break
    fi
    log "JSON 搜索冒烟第 $attempt 次未通过"
    sleep 3
done
if [ "$smoke_ready" -ne 1 ]; then
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs --tail=120
    log "SearXNG JSON 搜索冒烟未通过"
    exit 1
fi

log "执行图片搜索冒烟"
image_smoke_ready=0
for attempt in $(seq 1 3); do
    if curl --fail --silent --show-error --max-time 20 \
        --request POST \
        --data-urlencode 'q=human heart anatomy' \
        --data 'format=json' \
        --data 'categories=images' \
        --data 'engines=wikicommons.images' \
        --data 'safesearch=2' \
        --data 'language=all' \
        --data 'timeout_limit=12' \
        http://127.0.0.1:8080/search \
        | python3 -c 'import json, sys; payload=json.load(sys.stdin); assert isinstance(payload.get("results"), list); assert not payload.get("unresponsive_engines"); assert payload.get("results")'; then
        image_smoke_ready=1
        break
    fi
    log "图片搜索冒烟第 $attempt 次未通过"
    sleep 3
done
if [ "$image_smoke_ready" -ne 1 ]; then
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs --tail=120
    log "SearXNG 图片搜索冒烟未通过"
    exit 1
fi

log "写入应用联网配置并重启服务"
app_env_backup="$(mktemp "${APP_ENV_FILE}.backup.XXXXXX")"
cp --preserve=mode,ownership,timestamps "$APP_ENV_FILE" "$app_env_backup"
upsert_env_value "$APP_ENV_FILE" "WEB_RETRIEVAL_PROVIDER" "searxng"
upsert_env_value "$APP_ENV_FILE" "SEARXNG_BASE_URL" "http://127.0.0.1:8080"
upsert_env_value "$APP_ENV_FILE" "SEARXNG_REQUEST_TIMEOUT_SECONDS" "12"
upsert_env_value "$APP_ENV_FILE" "WEB_RETRIEVAL_V2_MODE" "$RETRIEVAL_MODE"
upsert_env_value "$APP_ENV_FILE" "WEB_RETRIEVAL_V2_USER_IDS" "$RETRIEVAL_USER_IDS"
app_env_changed=1
systemctl restart "$APP_SERVICE_NAME"

log "等待应用识别 SearXNG 配置"
app_ready=0
for _ in $(seq 1 30); do
    if curl --fail --silent --show-error --max-time 5 "$APP_HEALTH_URL" \
        | python3 -c '
import json
import sys

expected_mode = sys.argv[1]
payload = json.load(sys.stdin)
state = payload["web_retrieval_v2"]
assert state["provider"] == "searxng"
assert state["provider_configured"] is True
assert state["mode"] == expected_mode
' "$RETRIEVAL_MODE"; then
        app_ready=1
        break
    fi
    sleep 2
done
if [ "$app_ready" -ne 1 ]; then
    journalctl -u "$APP_SERVICE_NAME" -n 120 --no-pager || true
    log "应用未正确识别 SearXNG 配置"
    exit 1
fi

log "SearXNG provisioning 完成，仅监听 127.0.0.1:8080"
app_env_changed=0
rm -f "$app_env_backup"
app_env_backup=""
trap - EXIT
