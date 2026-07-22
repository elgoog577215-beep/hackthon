#!/usr/bin/env bash

set -Eeuo pipefail

BASE_DIR="${LINGZHI_BASE_DIR:-/opt/lingzhi}"
CURRENT_LINK="${LINGZHI_CURRENT_LINK:-$BASE_DIR/hackthon}"
RELEASES_DIR="${LINGZHI_RELEASES_DIR:-$BASE_DIR/releases}"
STATE_DIR="${LINGZHI_STATE_DIR:-$BASE_DIR/state}"
BACKUP_DIR="${LINGZHI_BACKUP_DIR:-$BASE_DIR/backups}"
VENV="${LINGZHI_VENV:-$BASE_DIR/.venv}"
TARGET_COMMIT="${LINGZHI_TARGET_COMMIT:-}"
ARTIFACT_PATH="${LINGZHI_ARTIFACT_PATH:-}"
ARTIFACT_SHA256="${LINGZHI_ARTIFACT_SHA256:-}"
HEALTH_URL="${LINGZHI_HEALTH_URL:-http://127.0.0.1:7862/api/health}"
TASKS_URL="${LINGZHI_TASKS_URL:-${HEALTH_URL%/health}/tasks?limit=100}"
SERVICE_NAME="${LINGZHI_SERVICE_NAME:-lingzhi}"
LOCK_FILE="${LINGZHI_DEPLOY_LOCK:-/var/lock/lingzhi-deploy.lock}"
KEEP_RELEASES="${LINGZHI_KEEP_RELEASES:-2}"
KEEP_BACKUPS="${LINGZHI_KEEP_BACKUPS:-10}"
MIN_FREE_MB="${LINGZHI_MIN_FREE_MB:-2048}"
HEALTH_ATTEMPTS="${LINGZHI_HEALTH_ATTEMPTS:-60}"
HEALTH_INTERVAL_SECONDS="${LINGZHI_HEALTH_INTERVAL_SECONDS:-2}"

timestamp="$(date +%Y%m%d-%H%M%S)"
service_stopped=0
previous_path=""
release_path=""

log() {
    printf '[%s] %s\n' "$(date -Is)" "$*"
}

validate_settings() {
    if ! [[ "$KEEP_RELEASES" =~ ^[0-9]+$ ]] || [ "$KEEP_RELEASES" -lt 2 ]; then
        log "LINGZHI_KEEP_RELEASES 必须是不小于 2 的整数"
        exit 1
    fi
    if ! [[ "$KEEP_BACKUPS" =~ ^[0-9]+$ ]] || [ "$KEEP_BACKUPS" -lt 1 ]; then
        log "LINGZHI_KEEP_BACKUPS 必须是正整数"
        exit 1
    fi
    if ! [[ "$MIN_FREE_MB" =~ ^[0-9]+$ ]] || [ "$MIN_FREE_MB" -lt 1 ]; then
        log "LINGZHI_MIN_FREE_MB 必须是正整数"
        exit 1
    fi
    if ! [[ "$HEALTH_ATTEMPTS" =~ ^[0-9]+$ ]] || [ "$HEALTH_ATTEMPTS" -lt 1 ]; then
        log "LINGZHI_HEALTH_ATTEMPTS 必须是正整数"
        exit 1
    fi
    if ! [[ "$HEALTH_INTERVAL_SECONDS" =~ ^[0-9]+$ ]] || [ "$HEALTH_INTERVAL_SECONDS" -lt 1 ]; then
        log "LINGZHI_HEALTH_INTERVAL_SECONDS 必须是正整数"
        exit 1
    fi
    if ! [[ "$TARGET_COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
        log "LINGZHI_TARGET_COMMIT 必须是完整提交哈希"
        exit 1
    fi
    if [ ! -f "$ARTIFACT_PATH" ]; then
        log "找不到构建机上传的发布包：$ARTIFACT_PATH"
        exit 1
    fi
    if ! [[ "$ARTIFACT_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
        log "LINGZHI_ARTIFACT_SHA256 必须是完整 SHA-256"
        exit 1
    fi
}

current_release() {
    if [ -e "$CURRENT_LINK" ] || [ -L "$CURRENT_LINK" ]; then
        readlink -f -- "$CURRENT_LINK"
    fi
    return 0
}

cleanup_backups() {
    local index
    local -a backups=()

    mapfile -t backups < <(
        find "$BACKUP_DIR" -maxdepth 1 -type f -name 'data-*.tgz' -printf '%T@ %p\n' \
            | LC_ALL=C sort -nr \
            | cut -d' ' -f2-
    )

    for ((index = KEEP_BACKUPS; index < ${#backups[@]}; index++)); do
        log "清理旧数据备份：${backups[index]}"
        rm -f -- "${backups[index]}"
    done
}

cleanup_releases() {
    local active_path=""
    local directory
    local real_path
    local rollback_slots="$KEEP_RELEASES"
    local rollback_kept=0
    local -a ordered_releases=()

    active_path="$(current_release)"
    if [[ "$active_path" == "$RELEASES_DIR"/* ]]; then
        rollback_slots=$((KEEP_RELEASES - 1))
    fi

    mapfile -t ordered_releases < <(
        find "$RELEASES_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
            | LC_ALL=C sort -nr \
            | cut -d' ' -f2-
    )

    for directory in "${ordered_releases[@]}"; do
        real_path="$(readlink -f -- "$directory")"
        if [ "$real_path" = "$active_path" ]; then
            continue
        fi
        if [ -f "$directory/.deploy-ready" ] && [ "$rollback_kept" -lt "$rollback_slots" ]; then
            rollback_kept=$((rollback_kept + 1))
            continue
        fi

        log "清理旧版本：$(basename "$directory")"
        rm -rf --one-file-system -- "$directory"
    done
}

ensure_free_space() {
    local available_kb
    local required_kb=$((MIN_FREE_MB * 1024))

    available_kb="$(df -Pk "$BASE_DIR" | awk 'NR == 2 {print $4}')"
    if [ -z "$available_kb" ] || [ "$available_kb" -lt "$required_kb" ]; then
        log "可用磁盘不足：需要至少 ${MIN_FREE_MB}MB"
        df -h "$BASE_DIR"
        exit 1
    fi
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
    for attempt in $(seq 1 "$HEALTH_ATTEMPTS"); do
        if curl --fail --silent --show-error --max-time 2 "$HEALTH_URL" >/dev/null; then
            return 0
        fi
        sleep "$HEALTH_INTERVAL_SECONDS"
    done
    return 1
}

active_generation_task_ids() {
    local payload
    if ! payload="$(curl --fail --silent --show-error --max-time 5 "$TASKS_URL")"; then
        return 1
    fi
    printf '%s' "$payload" | "$VENV/bin/python" -c '
import json
import sys

tasks = json.load(sys.stdin)
if not isinstance(tasks, list):
    raise SystemExit("task list response must be an array")
print(" ".join(sorted(
    str(task.get("id") or "")
    for task in tasks
    if str(task.get("status") or "") in {"pending", "running"}
)))
'
}

rollback() {
    local exit_code=$?
    local active_path=""
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
    active_path="$(current_release)"
    if [ -n "$release_path" ] \
        && [ -d "$release_path" ] \
        && [ "$release_path" != "$active_path" ] \
        && [ "$release_path" != "$previous_path" ]; then
        log "清理失败版本：$release_path"
        rm -rf --one-file-system -- "$release_path" || true
    fi
    exit "$exit_code"
}

trap rollback ERR

validate_settings

exec 9>"$LOCK_FILE"
flock -n 9 || {
    log "已有部署任务正在运行"
    exit 1
}

mkdir -p "$RELEASES_DIR" "$STATE_DIR/backend-data" "$BACKUP_DIR"

cleanup_backups
cleanup_releases
ensure_free_space

printf '%s  %s\n' "$ARTIFACT_SHA256" "$ARTIFACT_PATH" | sha256sum --check --status
artifact_listing="$(tar -tzf "$ARTIFACT_PATH")"
if grep -Eq '(^|/)\.\.(/|$)|^/' <<< "$artifact_listing"; then
    log "发布包包含不安全路径"
    exit 1
fi

release_path="$RELEASES_DIR/$TARGET_COMMIT"

if [ -e "$CURRENT_LINK" ]; then
    previous_path="$(readlink -f "$CURRENT_LINK")"
fi

if [ ! -f "$release_path/.deploy-ready" ]; then
    if [ "$previous_path" = "$release_path" ]; then
        log "当前活动版本缺少部署完成标记，拒绝原地重建"
        exit 1
    fi
    rm -rf "$release_path"
    log "解压构建机发布包：$TARGET_COMMIT"
    mkdir -p "$release_path"
    tar -xzf "$ARTIFACT_PATH" -C "$release_path" --no-same-owner

    if [ "$(cat "$release_path/.release-commit" 2>/dev/null || true)" != "$TARGET_COMMIT" ]; then
        log "发布包提交标记与目标提交不一致"
        exit 1
    fi
    if [ ! -f "$release_path/backend/static/index.html" ]; then
        log "发布包缺少前端构建产物"
        exit 1
    fi
    if [ -n "$previous_path" ] \
        && [ -f "$previous_path/backend/requirements.txt" ] \
        && ! cmp -s "$previous_path/backend/requirements.txt" "$release_path/backend/requirements.txt"; then
        log "后端依赖发生变化；标准发布禁止在低性能服务器安装依赖"
        exit 1
    fi

    rm -rf "$release_path/backend/data"
    ln -s "$STATE_DIR/backend-data" "$release_path/backend/data"

    if [ -f "$STATE_DIR/.env" ]; then
        rm -f "$release_path/.env"
        ln -s "$STATE_DIR/.env" "$release_path/.env"
    fi
    touch "$release_path/.deploy-ready"
fi

rm -f "$ARTIFACT_PATH"

if systemctl is-active --quiet "$SERVICE_NAME"; then
    if ! active_task_ids="$(active_generation_task_ids)"; then
        log "无法读取任务状态，拒绝停止当前服务：$TASKS_URL"
        exit 75
    fi
    if [ -n "$active_task_ids" ]; then
        log "检测到正在生成的任务，取消本次发布：$active_task_ids"
        exit 75
    fi
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

if [ ! -f "$STATE_DIR/backend-data/generation_jobs.json" ] \
    && [ -f "$CURRENT_LINK/backend/tasks.json" ]; then
    log "迁移旧任务历史到持久化数据目录"
    install -m 600 "$CURRENT_LINK/backend/tasks.json" \
        "$STATE_DIR/backend-data/generation_jobs.json"
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
log "部署完成：$TARGET_COMMIT"

cleanup_backups
cleanup_releases
