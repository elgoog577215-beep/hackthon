#!/usr/bin/env bash

set -Eeuo pipefail

BASE_DIR="${LINGZHI_BASE_DIR:-/opt/lingzhi}"
CURRENT_LINK="${LINGZHI_CURRENT_LINK:-$BASE_DIR/hackthon}"
STATE_DIR="${LINGZHI_STATE_DIR:-$BASE_DIR/state}"
PREVIOUS_RELEASE="${LINGZHI_PREVIOUS_RELEASE:-}"
ENV_BACKUP="${LINGZHI_ENV_BACKUP:-}"
HEALTH_URL="${LINGZHI_HEALTH_URL:-http://127.0.0.1:7862/health}"
HEALTH_ATTEMPTS="${LINGZHI_HEALTH_ATTEMPTS:-60}"
HEALTH_INTERVAL_SECONDS="${LINGZHI_HEALTH_INTERVAL_SECONDS:-2}"

log() {
    printf '[%s] %s\n' "$(date -Is)" "$*"
}

if ! [[ "$HEALTH_ATTEMPTS" =~ ^[0-9]+$ ]] || [ "$HEALTH_ATTEMPTS" -lt 1 ]; then
    log "LINGZHI_HEALTH_ATTEMPTS 必须是正整数"
    exit 1
fi
if ! [[ "$HEALTH_INTERVAL_SECONDS" =~ ^[0-9]+$ ]] \
    || [ "$HEALTH_INTERVAL_SECONDS" -lt 1 ]; then
    log "LINGZHI_HEALTH_INTERVAL_SECONDS 必须是正整数"
    exit 1
fi
case "$PREVIOUS_RELEASE" in
    "$BASE_DIR"/releases/* | "$BASE_DIR"/legacy-hackthon-*) ;;
    *)
        log "上一版本路径不在允许的 Lingzhi 发布边界内"
        exit 1
        ;;
esac
if [ ! -d "$PREVIOUS_RELEASE" ]; then
    log "上一版本不存在：$PREVIOUS_RELEASE"
    exit 1
fi

next_link="$BASE_DIR/.hackthon-restore-next"
rm -f "$next_link"
ln -s "$PREVIOUS_RELEASE" "$next_link"
mv -Tf "$next_link" "$CURRENT_LINK"

if [ -f "$ENV_BACKUP" ]; then
    install -m 600 "$ENV_BACKUP" "$STATE_DIR/.env"
elif [ -f "$ENV_BACKUP.empty" ]; then
    rm -f "$STATE_DIR/.env"
else
    log "模型配置备份不存在，拒绝伪装成回滚成功"
    exit 1
fi
if [ -f "$STATE_DIR/.env" ]; then
    chown lingzhi:lingzhi "$STATE_DIR/.env"
    chmod 600 "$STATE_DIR/.env"
fi

systemctl reset-failed lingzhi || true
systemctl restart lingzhi

for attempt in $(seq 1 "$HEALTH_ATTEMPTS"); do
    if curl --fail --silent --show-error --max-time 2 "$HEALTH_URL" >/dev/null; then
        log "上一版本已恢复并通过健康检查"
        exit 0
    fi
    if [ "$attempt" -lt "$HEALTH_ATTEMPTS" ]; then
        sleep "$HEALTH_INTERVAL_SECONDS"
    fi
done

log "上一版本在有界等待后仍未恢复：$HEALTH_URL"
systemctl show lingzhi \
    --property=ActiveState \
    --property=SubState \
    --property=Result \
    --property=ExecMainCode \
    --property=ExecMainStatus \
    --no-pager || true
journalctl -u lingzhi -n 120 --no-pager || true
exit 1
