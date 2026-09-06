#!/usr/bin/env bash
# Start the complete release image without production data, networking or ports.
set -Eeuo pipefail
if [[ $# -lt 1 || $# -gt 2 ]]; then
  printf 'Usage: %s IMAGE [ENV_FILE]\n' "$0" >&2
  exit 2
fi
image="$1"
container_id=""
cleanup() {
  if [[ -n "$container_id" ]]; then
    docker rm --force "$container_id" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT
options=(--detach --network none)
if [[ $# == 2 ]]; then options+=(--env-file "$2"); fi
container_id="$(docker run "${options[@]}" "$image")"
for attempt in $(seq 1 60); do
  if docker exec "$container_id" python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/api/health', timeout=3)" \
    >/dev/null 2>&1; then
    printf 'Full Lingzhi image startup and readiness passed: %s\n' "$image"
    exit 0
  fi
  if [[ "$(docker inspect --format '{{.State.Running}}' "$container_id")" != true ]]; then
    docker logs --tail 40 "$container_id" >&2
    exit 1
  fi
  sleep 2
done
docker logs --tail 40 "$container_id" >&2
printf 'Lingzhi image did not become ready within the startup window.\n' >&2
exit 1
