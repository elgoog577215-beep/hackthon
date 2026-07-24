#!/usr/bin/env bash

set -euo pipefail

tracked_ignored="$(git ls-files -ci --exclude-standard)"

if [[ -n "$tracked_ignored" ]]; then
  echo "错误：以下文件已被 .gitignore 忽略，但仍处于 Git 跟踪中："
  printf '%s\n' "$tracked_ignored"
  echo
  echo "请使用 git rm --cached 取消跟踪，并保留本地运行数据。"
  exit 1
fi

echo "Git 跟踪卫生检查通过：没有被忽略但仍被跟踪的文件。"
