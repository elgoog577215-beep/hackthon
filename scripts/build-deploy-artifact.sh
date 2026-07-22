#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_COMMIT="${LINGZHI_TARGET_COMMIT:-$(git -C "$ROOT_DIR" rev-parse HEAD)}"
OUTPUT_PATH="${1:-/tmp/lingzhi-release-$TARGET_COMMIT.tgz}"
STAGING_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "$STAGING_DIR"
}
trap cleanup EXIT

if ! [[ "$TARGET_COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
    printf '无效的目标提交：%s\n' "$TARGET_COMMIT" >&2
    exit 1
fi

printf '[%s] 在构建机生成前端产物：%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$TARGET_COMMIT"
(
    cd "$ROOT_DIR/frontend"
    npm ci
    VITE_BASE_PATH=/lingzhi/ npm run build
)

git -C "$ROOT_DIR" archive "$TARGET_COMMIT" | tar -x -C "$STAGING_DIR"
rm -rf "$STAGING_DIR/backend/static"
mkdir -p "$STAGING_DIR/backend/static"
cp -a "$ROOT_DIR/frontend/dist/." "$STAGING_DIR/backend/static/"
printf '%s\n' "$TARGET_COMMIT" > "$STAGING_DIR/.release-commit"

mkdir -p "$(dirname "$OUTPUT_PATH")"
tar -C "$STAGING_DIR" -czf "$OUTPUT_PATH" .
printf '[%s] 发布包已生成：%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$OUTPUT_PATH"
