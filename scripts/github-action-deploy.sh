#!/usr/bin/env bash

set -Eeuo pipefail

BASE_DIR="${LINGZHI_BASE_DIR:-/opt/lingzhi}"
CURRENT_LINK="${LINGZHI_CURRENT_LINK:-$BASE_DIR/hackthon}"
RELEASES_DIR="${LINGZHI_RELEASES_DIR:-$BASE_DIR/releases}"
INCOMING_DIR="${LINGZHI_INCOMING_DIR:-$BASE_DIR/incoming}"
STATE_DIR="${LINGZHI_STATE_DIR:-$BASE_DIR/state}"
BACKUP_DIR="${LINGZHI_BACKUP_DIR:-$BASE_DIR/backups}"
VENV="${LINGZHI_VENV:-$BASE_DIR/.venv}"
TARGET_COMMIT="${LINGZHI_TARGET_COMMIT:-}"
ARTIFACT_PATH="${LINGZHI_ARTIFACT_PATH:-}"
ARTIFACT_SHA256="${LINGZHI_ARTIFACT_SHA256:-}"
HEALTH_URL="${LINGZHI_HEALTH_URL:-http://127.0.0.1:7862/api/health}"
STATIC_BASE_URL="${LINGZHI_STATIC_BASE_URL:-${HEALTH_URL%/api/health}}"
SERVICE_NAME="${LINGZHI_SERVICE_NAME:-lingzhi}"
LOCK_FILE="${LINGZHI_DEPLOY_LOCK:-/var/lock/lingzhi-deploy.lock}"
KEEP_RELEASES="${LINGZHI_KEEP_RELEASES:-2}"
KEEP_BACKUPS="${LINGZHI_KEEP_BACKUPS:-2}"
MIN_FREE_MB="${LINGZHI_MIN_FREE_MB:-}"
DEPLOY_SAFETY_RESERVE_MB="${LINGZHI_DEPLOY_SAFETY_RESERVE_MB:-176}"
HEALTH_ATTEMPTS="${LINGZHI_HEALTH_ATTEMPTS:-60}"
HEALTH_INTERVAL_SECONDS="${LINGZHI_HEALTH_INTERVAL_SECONDS:-2}"
LOCALE_ATTEMPTS="${LINGZHI_LOCALE_ATTEMPTS:-12}"
LOCALE_INTERVAL_SECONDS="${LINGZHI_LOCALE_INTERVAL_SECONDS:-3}"

timestamp="$(date +%Y%m%d-%H%M%S)"
service_stopped=0
previous_path=""
release_path=""

log() {
    printf '[%s] %s\n' "$(date -Is)" "$*"
}

verify_backend_requirements_compatibility() {
    local previous_requirements="$1"
    local release_requirements="$2"
    local requirements_helper="$release_path/scripts/effective_requirements.py"
    local previous_effective
    local release_effective

    if [ ! -f "$previous_requirements" ] \
        || cmp -s "$previous_requirements" "$release_requirements"; then
        return 0
    fi
    if [ ! -f "$requirements_helper" ]; then
        log "发布包缺少依赖比较工具，无法确认服务器是否需要安装新依赖"
        return 1
    fi

    previous_effective="$(mktemp /tmp/lingzhi-previous-requirements.XXXXXX)"
    release_effective="$(mktemp /tmp/lingzhi-release-requirements.XXXXXX)"
    if ! "$VENV/bin/python" "$requirements_helper" \
        "$previous_requirements" > "$previous_effective" \
        || ! "$VENV/bin/python" "$requirements_helper" \
        "$release_requirements" > "$release_effective"; then
        rm -f -- "$previous_effective" "$release_effective"
        log "无法按服务器 Python 版本解析后端依赖，停止发布"
        return 1
    fi
    if ! cmp -s "$previous_effective" "$release_effective"; then
        rm -f -- "$previous_effective" "$release_effective"
        log "后端有实际生效的依赖变化；标准发布禁止在低性能服务器安装依赖"
        return 1
    fi
    rm -f -- "$previous_effective" "$release_effective"
    log "requirements.txt 的写法已变更，但当前 Python 实际使用的后端依赖未变"
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
    if [ -n "$MIN_FREE_MB" ] \
        && { ! [[ "$MIN_FREE_MB" =~ ^[0-9]+$ ]] || [ "$MIN_FREE_MB" -lt 1 ]; }; then
        log "LINGZHI_MIN_FREE_MB 必须是正整数"
        exit 1
    fi
    if ! [[ "$DEPLOY_SAFETY_RESERVE_MB" =~ ^[0-9]+$ ]] \
        || [ "$DEPLOY_SAFETY_RESERVE_MB" -lt 1 ]; then
        log "LINGZHI_DEPLOY_SAFETY_RESERVE_MB 必须是正整数"
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
    if ! [[ "$LOCALE_ATTEMPTS" =~ ^[0-9]+$ ]] || [ "$LOCALE_ATTEMPTS" -lt 1 ]; then
        log "LINGZHI_LOCALE_ATTEMPTS 必须是正整数"
        exit 1
    fi
    if ! [[ "$LOCALE_INTERVAL_SECONDS" =~ ^[0-9]+$ ]] || [ "$LOCALE_INTERVAL_SECONDS" -lt 1 ]; then
        log "LINGZHI_LOCALE_INTERVAL_SECONDS 必须是正整数"
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
    local keep_count="${1:-$KEEP_BACKUPS}"
    local -a backups=()

    mapfile -t backups < <(
        find "$BACKUP_DIR" -maxdepth 1 -type f -name 'data-*.tgz' -printf '%T@ %p\n' \
            | LC_ALL=C sort -nr \
            | cut -d' ' -f2-
    )

    for ((index = keep_count; index < ${#backups[@]}; index++)); do
        log "清理旧数据备份：${backups[index]}"
        rm -f -- "${backups[index]}"
        rm -f -- "${backups[index]}.sha256"
    done
}

cleanup_incoming() {
    local artifact

    while IFS= read -r -d '' artifact; do
        if [ "$artifact" = "$ARTIFACT_PATH" ]; then
            continue
        fi
        log "清理失败或过期的上传包：$artifact"
        rm -f -- "$artifact"
    done < <(
        find "$INCOMING_DIR" -maxdepth 1 -type f \
            -name 'lingzhi-release-*.tgz' -print0
    )
}

cleanup_releases() {
    local active_path=""
    local directory
    local keep_count="${1:-$KEEP_RELEASES}"
    local real_path
    local rollback_slots="$keep_count"
    local rollback_kept=0
    local -a ordered_releases=()

    active_path="$(current_release)"
    if [[ "$active_path" == "$RELEASES_DIR"/* ]]; then
        rollback_slots=$((keep_count - 1))
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

cleanup_regenerable_caches() {
    local active_path=""
    local cache_path
    local generated_cache
    local -a cache_paths=(
        "${XDG_CACHE_HOME:-$HOME/.cache}/pip"
        "${XDG_CACHE_HOME:-$HOME/.cache}/uv"
        "$HOME/.npm/_cacache"
        "$HOME/.cache/node-gyp"
    )

    for cache_path in "${cache_paths[@]}"; do
        if [ ! -d "$cache_path" ]; then
            continue
        fi
        log "清理可再生成的构建缓存：$cache_path"
        rm -rf --one-file-system -- "$cache_path"
    done

    active_path="$(current_release)"
    if [[ "$active_path" != "$BASE_DIR"/* ]] || [ ! -d "$active_path" ]; then
        return 0
    fi

    while IFS= read -r -d '' generated_cache; do
        log "清理当前版本的运行时缓存：$generated_cache"
        rm -rf --one-file-system -- "$generated_cache"
    done < <(
        find "$active_path" -xdev -type d \
            \( -name '__pycache__' -o -name '.pytest_cache' -o -name '.mypy_cache' -o -name '.ruff_cache' \) \
            -prune -print0
    )
}

cleanup_system_regenerable_caches() {
    if command -v docker >/dev/null 2>&1; then
        log "Cleaning Docker regenerated caches and unused images"
        docker container prune -f >/dev/null 2>&1 || true
        docker image prune -af >/dev/null 2>&1 || true
        docker builder prune -af >/dev/null 2>&1 || true
    fi

    if command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
        log "Cleaning package cache and compacting system journal"
        sudo apt-get clean >/dev/null 2>&1 || true
        sudo journalctl --vacuum-size=128M >/dev/null 2>&1 || true
        sudo find /tmp /var/tmp -xdev -mindepth 1 -maxdepth 1 -type f -mtime +1 -delete >/dev/null 2>&1 || true
    fi
}

required_deploy_free_kb() {
    local artifact_uncompressed_bytes=""
    local artifact_required_kb=0
    local backup_required_kb=0
    local explicit_required_kb=0
    local latest_backup=""
    local required_kb=0

    artifact_uncompressed_bytes="$(gzip -l "$ARTIFACT_PATH" | awk 'NR == 2 {print $2}')"
    if ! [[ "$artifact_uncompressed_bytes" =~ ^[0-9]+$ ]]; then
        log "无法计算发布包解压体积：$ARTIFACT_PATH" >&2
        return 1
    fi
    artifact_required_kb=$(((artifact_uncompressed_bytes + 1023) / 1024))

    latest_backup="$({
        find "$BACKUP_DIR" -maxdepth 1 -type f -name 'data-*.tgz' -printf '%T@ %p\n' 2>/dev/null \
            | LC_ALL=C sort -nr \
            | head -n 1 \
            | cut -d' ' -f2-
    } || true)"
    if [ -n "$latest_backup" ] && [ -f "$latest_backup" ]; then
        backup_required_kb="$(du -k "$latest_backup" | awk 'NR == 1 {print $1}')"
    elif [ -d "$STATE_DIR/backend-data" ]; then
        backup_required_kb="$(du -sk "$STATE_DIR/backend-data" | awk 'NR == 1 {print $1}')"
    fi
    if ! [[ "$backup_required_kb" =~ ^[0-9]+$ ]]; then
        backup_required_kb=0
    fi

    required_kb=$((
        DEPLOY_SAFETY_RESERVE_MB * 1024
        + artifact_required_kb
        + backup_required_kb * 5 / 4
    ))
    if [ -n "$MIN_FREE_MB" ]; then
        explicit_required_kb=$((MIN_FREE_MB * 1024))
        if [ "$explicit_required_kb" -gt "$required_kb" ]; then
            required_kb="$explicit_required_kb"
        fi
    fi

    printf '%s\n' "$required_kb"
}

ensure_free_space() {
    local available_kb
    local required_kb

    required_kb="$(required_deploy_free_kb)"

    available_kb="$(df -Pk "$BASE_DIR" | awk 'NR == 2 {print $4}')"
    if [ -n "$available_kb" ] \
        && [ "$available_kb" -lt "$required_kb" ] \
        && [ "$KEEP_BACKUPS" -gt 1 ]; then
        log "磁盘空间低于发布阈值；仅保留最新一份数据备份后重试"
        cleanup_backups 1
        available_kb="$(df -Pk "$BASE_DIR" | awk 'NR == 2 {print $4}')"
    fi
    if [ -n "$available_kb" ] && [ "$available_kb" -lt "$required_kb" ]; then
        log "磁盘空间仍低于发布阈值；保留当前活动版本并清理更旧的回滚版本后重试"
        cleanup_releases 1
        available_kb="$(df -Pk "$BASE_DIR" | awk 'NR == 2 {print $4}')"
    fi
    if [ -n "$available_kb" ] && [ "$available_kb" -lt "$required_kb" ]; then
        log "磁盘空间仍低于发布阈值；清理可再生成的构建与运行时缓存后重试"
        cleanup_regenerable_caches
        available_kb="$(df -Pk "$BASE_DIR" | awk 'NR == 2 {print $4}')"
    fi
    if [ -n "$available_kb" ] && [ "$available_kb" -lt "$required_kb" ]; then
        log "Disk is still below deploy threshold; cleaning system-level regenerated caches"
        cleanup_system_regenerable_caches
        available_kb="$(df -Pk "$BASE_DIR" | awk 'NR == 2 {print $4}')"
    fi
    if [ -z "$available_kb" ] || [ "$available_kb" -lt "$required_kb" ]; then
        log "可用磁盘不足：本次发布至少需要 $(((required_kb + 1023) / 1024))MB"
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

verify_locale_assets() {
    local attempt
    local locale
    local locale_ready
    local locale_url
    local payload

    for locale in zh en; do
        locale_ready=0
        locale_url="${STATIC_BASE_URL%/}/locales/$locale/translation.json"
        for attempt in $(seq 1 "$LOCALE_ATTEMPTS"); do
            if payload="$(curl --fail --silent --show-error --max-time 10 "$locale_url")" \
                && printf '%s' "$payload" | "$VENV/bin/python" -c '
import json
import sys

locale = sys.argv[1]
payload = json.load(sys.stdin)
expected = {"zh": "我的日历", "en": "My calendar"}[locale]
if payload.get("teacherHome", {}).get("myCalendar") != expected:
    raise SystemExit(f"invalid {locale} teacherHome locale payload")
' "$locale"; then
                locale_ready=1
                break
            fi
            if [ "$attempt" -lt "$LOCALE_ATTEMPTS" ]; then
                log "生产翻译资源尚未就绪，准备重试（$attempt/$LOCALE_ATTEMPTS）：$locale_url"
                sleep "$LOCALE_INTERVAL_SECONDS"
            fi
        done
        if [ "$locale_ready" -ne 1 ]; then
            log "生产翻译资源在重试后仍不可用或内容不完整：$locale_url"
            return 1
        fi
    done
}

assert_no_unsafe_active_tasks() {
    local checker="$release_path/scripts/check_deploy_task_safety.py"
    local result=""
    local status=0
    local task_index="$STATE_DIR/backend-data/generation_jobs.json"

    if [ ! -f "$task_index" ] && [ -f "$CURRENT_LINK/backend/tasks.json" ]; then
        task_index="$CURRENT_LINK/backend/tasks.json"
    fi
    if [ ! -f "$checker" ]; then
        log "发布包缺少只读活动任务检查器；无法证明停止服务安全"
        return 75
    fi
    if result="$("$VENV/bin/python" "$checker" "$task_index")"; then
        log "活动任务检查通过：$result"
        return 0
    fi
    status=$?
    log "发布延迟：存在不可安全中断的任务，或任务索引无法核验：$result"
    return "$status"
}

create_verified_data_backup() {
    local source_dir="$1"
    local backup_path="$BACKUP_DIR/data-$timestamp.tgz"
    local backup_tool="$release_path/scripts/create_verified_data_backup.py"
    local source_release_version=""

    source_release_version="$(cat "$CURRENT_LINK/.release-commit" 2>/dev/null || true)"
    source_release_version="${source_release_version:-legacy-$timestamp}"
    if [ ! -f "$backup_tool" ]; then
        log "发布包缺少数据备份校验工具"
        return 1
    fi
    log "创建带清单和校验和的数据备份，并在隔离目录验证恢复"
    "$VENV/bin/python" "$backup_tool" create \
        --source "$source_dir" \
        --output "$backup_path" \
        --release-version "$source_release_version"
}

deployment_env_value() {
    local key="$1"
    local env_file="$STATE_DIR/.env"
    if [ ! -f "$env_file" ]; then
        env_file="$CURRENT_LINK/.env"
    fi
    if [ ! -f "$env_file" ]; then
        return 0
    fi
    awk -v key="$key" '
        index($0, key "=") == 1 {
            value = substr($0, length(key) + 2)
            sub(/\r$/, "", value)
            if (value ~ /^".*"$/ || value ~ /^\047.*\047$/) {
                value = substr(value, 2, length(value) - 2)
            }
            print value
            exit
        }
    ' "$env_file"
}

preflight_retrieval_runtime() {
    local mode
    local provider
    local base_url

    mode="$(deployment_env_value WEB_RETRIEVAL_V2_MODE)"
    mode="${mode:-off}"
    if [ "$mode" = "off" ]; then
        log "联网检索处于关闭状态，跳过 SearXNG 预检"
        return 0
    fi
    if [ "$mode" != "allowlist" ] && [ "$mode" != "on" ]; then
        log "WEB_RETRIEVAL_V2_MODE 配置非法：$mode"
        return 1
    fi

    provider="$(deployment_env_value WEB_RETRIEVAL_PROVIDER)"
    provider="${provider:-searxng}"
    if [ "$provider" = "exa" ]; then
        log "联网检索使用兼容 Provider exa，不执行 SearXNG 预检"
        return 0
    fi
    if [ "$provider" != "searxng" ]; then
        log "WEB_RETRIEVAL_PROVIDER 配置非法：$provider"
        return 1
    fi

    base_url="$(deployment_env_value SEARXNG_BASE_URL)"
    base_url="${base_url%/}"
    if [ "$base_url" != "http://127.0.0.1:8080" ]; then
        log "SEARXNG_BASE_URL 必须为本机回环地址 http://127.0.0.1:8080"
        return 1
    fi

    log "在停止应用前预检 SearXNG"
    curl --fail --silent --show-error --max-time 6 \
        "$base_url/config" >/dev/null
    curl --fail --silent --show-error --max-time 10 \
        --request POST \
        --data 'q=Lingzhi deployment retrieval smoke test' \
        --data 'format=json' \
        --data 'categories=general,science' \
        --data 'safesearch=2' \
        --data 'language=en' \
        --data 'timeout_limit=4' \
        "$base_url/search" \
        | "$VENV/bin/python" -c '
import json
import sys

payload = json.load(sys.stdin)
if not isinstance(payload.get("results"), list):
    raise SystemExit("SearXNG response must contain a results array")
'
}

preflight_release_runtime() {
    log "预检新版本后端运行时导入：$TARGET_COMMIT"
    (
        if [ -f "$STATE_DIR/.env" ]; then
            set -a
            # shellcheck disable=SC1090
            . "$STATE_DIR/.env"
            set +a
        fi
        cd "$release_path/backend"
        runuser --user lingzhi -- \
            env LINGZHI_TASK_RUNTIME_MODE=read_only \
            "$VENV/bin/python" -c 'import main'
    )
}

normalize_backend_data_permissions() {
    chmod 755 "$STATE_DIR"
    install -d -o lingzhi -g lingzhi -m 750 "$STATE_DIR/backend-data"
    chown -R lingzhi:lingzhi "$STATE_DIR/backend-data"
    chmod 750 "$STATE_DIR/backend-data"
}

bootstrap_runtime() {
    local service_unit="$release_path/deploy/systemd/lingzhi.service"

    if [ ! -x "$VENV/bin/python" ]; then
        if [ "$(id -u)" -ne 0 ]; then
            log "首次部署需要 root 权限创建 Python 环境"
            return 1
        fi
        log "首次部署：创建 Python 环境并安装后端依赖"
        python3 -m venv "$VENV"
        PIP_NO_CACHE_DIR=1 "$VENV/bin/pip" install \
            --disable-pip-version-check \
            -r "$release_path/backend/requirements.txt"
    fi

    if ! getent passwd lingzhi >/dev/null; then
        if [ "$(id -u)" -ne 0 ]; then
            log "首次部署需要 root 权限创建 lingzhi 系统用户"
            return 1
        fi
        log "首次部署：创建隔离的 lingzhi 系统用户"
        useradd --system --home-dir "$BASE_DIR" --shell /usr/sbin/nologin lingzhi
    fi

    if [ ! -f "$service_unit" ]; then
        log "发布包缺少 systemd 服务定义：$service_unit"
        return 1
    fi
    if [ ! -f "/etc/systemd/system/$SERVICE_NAME.service" ] \
        || ! cmp -s "$service_unit" "/etc/systemd/system/$SERVICE_NAME.service"; then
        if [ "$(id -u)" -ne 0 ]; then
            log "安装 systemd 服务定义需要 root 权限"
            return 1
        fi
        log "安装 systemd 服务定义：$SERVICE_NAME"
        install -m 644 "$service_unit" "/etc/systemd/system/$SERVICE_NAME.service"
        systemctl daemon-reload
    fi
    systemctl enable "$SERVICE_NAME" >/dev/null
    normalize_backend_data_permissions
}

log_service_diagnostics() {
    log "输出服务失败诊断：$SERVICE_NAME"
    systemctl show "$SERVICE_NAME" \
        --property=ActiveState \
        --property=SubState \
        --property=Result \
        --property=ExecMainCode \
        --property=ExecMainStatus \
        --no-pager || true
    journalctl -u "$SERVICE_NAME" -n 120 --no-pager || true
}

rollback() {
    local exit_code=$?
    local active_path=""
    trap - ERR
    if [ -n "$previous_path" ] && [ -e "$previous_path" ]; then
        log "部署失败，恢复上一版本：$previous_path"
        if [ -L "$CURRENT_LINK" ]; then
            switch_current "$previous_path"
        elif [ ! -e "$CURRENT_LINK" ]; then
            mv "$previous_path" "$CURRENT_LINK"
        fi
        systemctl reset-failed "$SERVICE_NAME" || true
        systemctl restart "$SERVICE_NAME" || true
        if ! wait_for_health; then
            log "回滚版本未通过健康检查：$HEALTH_URL"
            log_service_diagnostics
        fi
    fi
    active_path="$(current_release)"
    if [ -n "$release_path" ] \
        && [ -d "$release_path" ] \
        && [ "$release_path" != "$active_path" ] \
        && [ "$release_path" != "$previous_path" ]; then
        log "清理失败版本：$release_path"
        rm -rf --one-file-system -- "$release_path" || true
    fi
    case "$ARTIFACT_PATH" in
        "$INCOMING_DIR"/lingzhi-release-*.tgz)
            log "清理失败发布包：$ARTIFACT_PATH"
            rm -f -- "$ARTIFACT_PATH" || true
            ;;
    esac
    exit "$exit_code"
}

trap rollback ERR

validate_settings

exec 9>"$LOCK_FILE"
flock -n 9 || {
    log "已有部署任务正在运行"
    exit 1
}

mkdir -p "$RELEASES_DIR" "$INCOMING_DIR" "$STATE_DIR/backend-data" "$BACKUP_DIR"

cleanup_incoming
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
    chmod 755 "$release_path"

    if [ "$(cat "$release_path/.release-commit" 2>/dev/null || true)" != "$TARGET_COMMIT" ]; then
        log "发布包提交标记与目标提交不一致"
        exit 1
    fi
    if [ ! -f "$release_path/backend/static/index.html" ]; then
        log "发布包缺少前端构建产物"
        exit 1
    fi
    if [ -n "$previous_path" ] \
        && ! verify_backend_requirements_compatibility \
            "$previous_path/backend/requirements.txt" \
            "$release_path/backend/requirements.txt"; then
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

bootstrap_runtime

preflight_release_runtime

preflight_retrieval_runtime

if systemctl is-active --quiet "$SERVICE_NAME"; then
    if assert_no_unsafe_active_tasks; then
        :
    else
        task_safety_status=$?
        trap - ERR
        exit "$task_safety_status"
    fi
fi

if [ -d "$CURRENT_LINK/backend/data" ] && [ ! "$CURRENT_LINK/backend/data" -ef "$STATE_DIR/backend-data" ]; then
    log "冻结服务并迁移持久化数据"
    systemctl stop "$SERVICE_NAME"
    service_stopped=1

    create_verified_data_backup "$CURRENT_LINK/backend/data"
    rsync -a "$CURRENT_LINK/backend/data/" "$STATE_DIR/backend-data/"

    if [ -f "$CURRENT_LINK/.env" ] && [ ! -f "$STATE_DIR/.env" ]; then
        install -m 600 "$CURRENT_LINK/.env" "$STATE_DIR/.env"
        ln -sfn "$STATE_DIR/.env" "$release_path/.env"
    fi
else
    log "停止服务并切换版本"
    systemctl stop "$SERVICE_NAME"
    service_stopped=1
    create_verified_data_backup "$STATE_DIR/backend-data"
fi

if [ ! -f "$STATE_DIR/backend-data/generation_jobs.json" ] \
    && [ -f "$CURRENT_LINK/backend/tasks.json" ]; then
    log "迁移旧任务历史到持久化数据目录"
    install -m 600 "$CURRENT_LINK/backend/tasks.json" \
        "$STATE_DIR/backend-data/generation_jobs.json"
fi

normalize_backend_data_permissions

if [ -d "$CURRENT_LINK" ] && [ ! -L "$CURRENT_LINK" ]; then
    legacy_path="$BASE_DIR/legacy-hackthon-$timestamp"
    mv "$CURRENT_LINK" "$legacy_path"
    previous_path="$legacy_path"
    ln -s "$release_path" "$CURRENT_LINK"
else
    switch_current "$release_path"
fi

systemctl reset-failed "$SERVICE_NAME" || true
systemctl restart "$SERVICE_NAME"

if ! wait_for_health; then
    log "新版本未通过健康检查：$HEALTH_URL"
    log_service_diagnostics
    false
fi

if ! verify_locale_assets; then
    log "新版本未通过翻译资源检查：$STATIC_BASE_URL"
    log_service_diagnostics
    false
fi

service_stopped=0
trap - ERR
log "部署完成：$TARGET_COMMIT"
rm -f "$ARTIFACT_PATH"

cleanup_backups
cleanup_releases
