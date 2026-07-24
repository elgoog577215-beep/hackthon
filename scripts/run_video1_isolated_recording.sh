#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h}"
frame_dir="${VIDEO1_FRAME_DIR:-$(mktemp -d /tmp/lingzhi-video1-frames.XXXXXX)}"
duration="${VIDEO1_DURATION:-70}"
output_file="${VIDEO1_OUTPUT:-$repo_root/demo_videos/01_人工智能通识课_课程随知识更新_${duration}秒.mp4}"
cdp_url="${EDGE_CDP_URL:-http://127.0.0.1:9224}"
mouse_lock="/tmp/lingzhi-global-mouse-recording.lock"

if pgrep -f 'record_video2_project_path.mjs|lingzhi-video2-recordly-debug' >/dev/null; then
  print -u2 '检测到视频二仍在控制真实鼠标，视频一不启动。'
  exit 3
fi

recordly_pid="$(pgrep -x Recordly | head -n 1 || true)"
if [[ -n "$recordly_pid" ]] && lsof -p "$recordly_pid" 2>/dev/null \
  | grep -E 'recording-[0-9]+\.mp4$' \
  | awk '$4 ~ /w/ {found=1} END {exit !found}'; then
  print -u2 '检测到 Recordly 仍在写视频，视频一不启动。'
  exit 4
fi

if ! mkdir "$mouse_lock" 2>/dev/null; then
  print -u2 '真实鼠标正被另一个录制任务占用，视频一不启动。'
  exit 5
fi

PYTHONPATH=backend backend/.venv/bin/python -c \
  "from video1_demo_preset import prepare_video1_demo; prepare_video1_demo('backend/data')"

VIDEO1_FRAME_DIR="$frame_dir" \
VIDEO1_DURATION="$duration" \
VIDEO1_FRAME_RATE=15 \
EDGE_CDP_URL="$cdp_url" \
node scripts/capture_video1_edge_page.mjs &
capture_pid=$!

cleanup() {
  if kill -0 "$capture_pid" 2>/dev/null; then kill "$capture_pid" 2>/dev/null || true; fi
  rmdir "$mouse_lock" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

sleep 0.4
ALLOW_GLOBAL_RECORDING=1 \
VIDEO1_DURATION="$duration" \
EDGE_CDP_URL="$cdp_url" \
node scripts/record_video1_real_mouse.mjs
wait "$capture_pid"

VIDEO1_FRAME_DIR="$frame_dir" \
VIDEO1_DURATION="$duration" \
VIDEO1_OUTPUT="$output_file" \
scripts/render_video1_edge_capture.sh

print "视频一完成：$output_file"
