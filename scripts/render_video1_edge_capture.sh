#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h}"
ffmpeg_bin="/Applications/Recordly.app/Contents/Resources/app.asar.unpacked/node_modules/ffmpeg-static/ffmpeg"
frame_dir="${VIDEO1_FRAME_DIR:?缺少 VIDEO1_FRAME_DIR}"
output_file="${VIDEO1_OUTPUT:-$repo_root/demo_videos/01_人工智能通识课_课程随知识更新_91秒.mp4}"
frame_rate="${VIDEO1_FRAME_RATE:-15}"

mkdir -p "${output_file:h}"
"$ffmpeg_bin" \
  -hide_banner \
  -loglevel error \
  -y \
  -framerate "$frame_rate" \
  -i "$frame_dir/frame-%05d.jpg" \
  -t 91 \
  -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0f172a" \
  -c:v libx264 \
  -preset medium \
  -crf 18 \
  -pix_fmt yuv420p \
  -movflags +faststart \
  "$output_file"

print "$output_file"
