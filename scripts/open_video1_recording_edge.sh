#!/bin/zsh
set -euo pipefail

port="${VIDEO1_EDGE_PORT:-9224}"
profile_dir="${VIDEO1_EDGE_PROFILE:-$(mktemp -d /tmp/lingzhi-video1-edge.XXXXXX)}"
url="${VIDEO1_DEMO_URL:-http://127.0.0.1:5174/course/demo-ai-literacy-update-v1/ppt}"

open -na 'Microsoft Edge' --args \
  --remote-debugging-port="$port" \
  --user-data-dir="$profile_dir" \
  --disable-extensions \
  --disable-sync \
  --disable-features=Translate,msEdgeSidebarV2,msEdgeAccountConsistency \
  --no-first-run \
  --no-default-browser-check \
  --start-maximized \
  "$url"

print "视频一独立 Edge 已启动：$url"
print "调试端口：http://127.0.0.1:$port"
