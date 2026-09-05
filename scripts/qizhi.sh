#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
qizhi_root="$repo_root/qizhi"
action="${1:-help}"
if [[ $# -gt 0 ]]; then shift; fi

case "$action" in
  help|-h|--help)
    printf '%s\n' \
      'Usage: scripts/qizhi.sh <action> [arguments]' \
      '  check       Validate repository paths and Compose without starting services' \
      '  dev-web     Start Qizhi Vite on port 5174' \
      '  dev-server  Start Qizhi FastAPI on port 8010 (requires server/.venv)' \
      '  build|up|ps|logs|pull  Run the shared Qizhi/Lingzhi Compose project' \
      '  For Lingzhi-only development, continue to use ./dev.sh.'
    ;;
  check)
    python3 "$repo_root/scripts/check_qizhi_layout.py"
    docker compose --env-file "$qizhi_root/deploy/.env.example" \
      -f "$qizhi_root/deploy/docker-compose.yml" config \
      --no-env-resolution --no-interpolate --quiet
    ;;
  dev-web)
    cd "$qizhi_root/client/website"
    exec npm run dev -- --port 5174 --strictPort "$@"
    ;;
  dev-server)
    cd "$qizhi_root/server"
    exec "${QIZHI_PYTHON:-$qizhi_root/server/.venv/bin/python}" \
      -m uvicorn main:app --host 127.0.0.1 --port 8010 "$@"
    ;;
  build|up|ps|logs|pull)
    deploy_env="${QIZHI_DEPLOY_ENV_FILE:-$qizhi_root/deploy/.env}"
    if [[ ! -f "$deploy_env" || ! -f "$qizhi_root/server/.env" ]]; then
      printf '%s\n' 'Create qizhi/deploy/.env and qizhi/server/.env from their examples first.' >&2
      exit 1
    fi
    exec docker compose --env-file "$deploy_env" \
      -f "$qizhi_root/deploy/docker-compose.yml" "$action" "$@"
    ;;
  *)
    printf 'Unknown action: %s\n' "$action" >&2
    exit 2
    ;;
esac
