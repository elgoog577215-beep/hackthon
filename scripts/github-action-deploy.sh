#!/usr/bin/env bash

set -Eeuo pipefail

BASE_DIR="${LINGZHI_BASE_DIR:-/opt/lingzhi}"
CURRENT_LINK="${LINGZHI_CURRENT_LINK:-$BASE_DIR/hackthon}"
RELEASES_DIR="${LINGZHI_RELEASES_DIR:-$BASE_DIR/releases}"
STATE_DIR="${LINGZHI_STATE_DIR:-$BASE_DIR/state}"
BACKUP_DIR="${LINGZHI_BACKUP_DIR:-$BASE_DIR/backups}"
REPOSITORY_DIR="${LINGZHI_REPOSITORY_DIR:-$BASE_DIR/repository.git}"
VENV="${LINGZHI_VENV:-$BASE_DIR/.venv}"
REPOSITORY_URL="${LINGZHI_REPOSITORY_URL:-git@github.com-lingzhi:elgoog577215-beep/hackthon.git}"
BRANCH="${LINGZHI_BRANCH:-main}"
HEALTH_URL="${LINGZHI_HEALTH_URL:-http://127.0.0.1:7862/api/health}"
SERVICE_NAME="${LINGZHI_SERVICE_NAME:-lingzhi}"
LOCK_FILE="${LINGZHI_DEPLOY_LOCK:-/var/lock/lingzhi-deploy.lock}"

timestamp="$(date +%Y%m%d-%H%M%S)"
service_stopped=0
previous_path=""
release_path=""

log() {
    printf '[%s] %s\n' "$(date -Is)" "$*"
}

switch_current() {
    local target="$1"
    local next_link="$BASE_DIR/.hackthon-next"
    rm -f "$next_link"
    ln -s "$target" "$next_link"
    mv -Tf "$next_link" "$CURRENT_LINK"
}

wait_for_health() {
    local attempt
    for attempt in $(seq 1 40); do
        if curl --fail --silent --show-error --max-time 2 "$HEALTH_URL" >/dev/null; then
            return 0
        fi
        sleep 1
    done
    return 1
}

rollback() {
    local exit_code=$?
    trap - ERR
    if [ "$service_stopped" -eq 1 ] && [ -n "$previous_path" ] && [ -e "$previous_path" ]; then
        log "部署失败，恢复上一版本：$previous_path"
        if [ -L "$CURRENT_LINK" ]; then
            switch_current "$previous_path"
        elif [ ! -e "$CURRENT_LINK" ]; then
            mv "$previous_path" "$CURRENT_LINK"
        fi
        systemctl restart "$SERVICE_NAME" || true
    fi
    exit "$exit_code"
}

trap rollback ERR

exec 9>"$LOCK_FILE"
flock -n 9 || {
    log "已有部署任务正在运行"
    exit 1
}

mkdir -p "$RELEASES_DIR" "$STATE_DIR/backend-data" "$BACKUP_DIR"

if [ ! -d "$REPOSITORY_DIR" ]; then
    log "创建仓库缓存"
    git clone --bare "$REPOSITORY_URL" "$REPOSITORY_DIR"
fi

git --git-dir="$REPOSITORY_DIR" remote set-url origin "$REPOSITORY_URL"
git --git-dir="$REPOSITORY_DIR" fetch --prune origin \
    "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"

target_commit="$(git --git-dir="$REPOSITORY_DIR" rev-parse "refs/remotes/origin/$BRANCH")"
release_path="$RELEASES_DIR/$target_commit"

if [ -e "$CURRENT_LINK" ]; then
    previous_path="$(readlink -f "$CURRENT_LINK")"
fi

if [ ! -f "$release_path/.deploy-ready" ]; then
    if [ "$previous_path" = "$release_path" ]; then
        log "当前活动版本缺少部署完成标记，拒绝原地重建"
        exit 1
    fi
    rm -rf "$release_path"
    log "准备版本：$target_commit"
    git clone --shared --no-checkout "$REPOSITORY_DIR" "$release_path"
    git -C "$release_path" checkout --detach "$target_commit"

    rm -rf "$release_path/backend/data"
    ln -s "$STATE_DIR/backend-data" "$release_path/backend/data"

    if [ -f "$STATE_DIR/.env" ]; then
        ln -s "$STATE_DIR/.env" "$release_path/.env"
    fi

    if [ -d /opt/nodejs/node-v24.12.0-linux-x64/bin ]; then
        export PATH="/opt/nodejs/node-v24.12.0-linux-x64/bin:$PATH"
    fi

    log "安装前端依赖并构建"
    (
        cd "$release_path/frontend"
        npm ci
        VITE_BASE_PATH=/lingzhi/ npm run build
    )

    rm -rf "$release_path/backend/static"
    mkdir -p "$release_path/backend/static"
    cp -a "$release_path/frontend/dist/." "$release_path/backend/static/"

    if [ ! -x "$VENV/bin/python" ]; then
        python3 -m venv "$VENV"
    fi
    log "安装后端依赖"
    "$VENV/bin/pip" install -r "$release_path/backend/requirements.txt"
    touch "$release_path/.deploy-ready"
fi

if [ -d "$CURRENT_LINK/backend/data" ] && [ ! "$CURRENT_LINK/backend/data" -ef "$STATE_DIR/backend-data" ]; then
    log "冻结服务并迁移持久化数据"
    systemctl stop "$SERVICE_NAME"
    service_stopped=1

    tar -C "$CURRENT_LINK" -czf "$BACKUP_DIR/data-$timestamp.tgz" backend/data
    rsync -a "$CURRENT_LINK/backend/data/" "$STATE_DIR/backend-data/"

    if [ -f "$CURRENT_LINK/.env" ] && [ ! -f "$STATE_DIR/.env" ]; then
        install -m 600 "$CURRENT_LINK/.env" "$STATE_DIR/.env"
        ln -sfn "$STATE_DIR/.env" "$release_path/.env"
    fi
else
    log "停止服务并切换版本"
    systemctl stop "$SERVICE_NAME"
    service_stopped=1
    tar -C "$STATE_DIR" -czf "$BACKUP_DIR/data-$timestamp.tgz" backend-data
fi

if [ -d "$CURRENT_LINK" ] && [ ! -L "$CURRENT_LINK" ]; then
    legacy_path="$BASE_DIR/legacy-hackthon-$timestamp"
    mv "$CURRENT_LINK" "$legacy_path"
    previous_path="$legacy_path"
    ln -s "$release_path" "$CURRENT_LINK"
else
    switch_current "$release_path"
fi

systemctl restart "$SERVICE_NAME"

if ! wait_for_health; then
    log "新版本未通过健康检查：$HEALTH_URL"
    false
fi

service_stopped=0
trap - ERR
log "部署完成：$target_commit"

find "$BACKUP_DIR" -maxdepth 1 -type f -name 'data-*.tgz' -printf '%T@ %p\n' \
    | sort -nr \
    | tail -n +11 \
    | cut -d' ' -f2- \
    | xargs -r rm -f
