#!/usr/bin/env bash
set -euo pipefail

ROOT="${LINGZHI_ROOT:-/opt/lingzhi/hackthon}"
VENV="${LINGZHI_VENV:-/opt/lingzhi/.venv}"

if [ -d /opt/nodejs/node-v24.12.0-linux-x64/bin ]; then
  export PATH="/opt/nodejs/node-v24.12.0-linux-x64/bin:$PATH"
fi

cd "$ROOT/frontend"
npm ci
VITE_BASE_PATH=/lingzhi/ npm run build

rm -rf "$ROOT/backend/static"
mkdir -p "$ROOT/backend/static"
cp -a dist/. "$ROOT/backend/static/"

if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi

"$VENV/bin/pip" install -r "$ROOT/backend/requirements.txt"

systemctl restart lingzhi
systemctl is-active --quiet lingzhi

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:7862/api/health >/dev/null; then
    exit 0
  fi
  sleep 1
done

curl -fsS http://127.0.0.1:7862/api/health >/dev/null
