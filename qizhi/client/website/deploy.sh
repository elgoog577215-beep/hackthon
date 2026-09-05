#!/usr/bin/env bash
# ============================================================
# MentorAI 前端生产部署脚本
#
# 用法（在服务器 /root/edu_ai_home/client/website 目录下执行）:
#   bash deploy.sh
#
# 做的事情:
#   1. npm install（安装/更新依赖）
#   2. npm run build（Vite 生产构建 → dist/）
#   3. 停掉 Vite dev server（如果还在跑）
#   4. 配置 nginx 反向代理，托管 dist 静态文件
#   5. 重载 nginx
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== [1/5] 安装依赖 ==="
npm install --prefer-offline 2>&1 | tail -3

echo "=== [2/5] 生产构建 ==="
npm run build 2>&1 | tail -5

echo "=== [3/5] 停止 Vite dev server ==="
pkill -f "node.*vite" 2>/dev/null && echo "  已停止 Vite 进程" || echo "  没有运行中的 Vite 进程"

echo "=== [4/5] 部署 nginx 配置 ==="
NGINX_CONF_DIR=""
if [ -d /etc/nginx/conf.d ]; then
    NGINX_CONF_DIR="/etc/nginx/conf.d"
elif [ -d /etc/nginx/sites-enabled ]; then
    NGINX_CONF_DIR="/etc/nginx/sites-enabled"
else
    echo "  [WARN] 找不到 nginx 配置目录，尝试 /etc/nginx/conf.d"
    mkdir -p /etc/nginx/conf.d
    NGINX_CONF_DIR="/etc/nginx/conf.d"
fi

cp nginx.prod.conf "$NGINX_CONF_DIR/mentorai-frontend.conf"
echo "  配置已复制到 $NGINX_CONF_DIR/mentorai-frontend.conf"

# 检查 nginx 配置语法
nginx -t 2>&1

echo "=== [5/5] 重载 nginx ==="
# 如果 nginx 没在运行就启动它，否则 reload
if ! pgrep -x nginx > /dev/null; then
    nginx
    echo "  nginx 已启动"
else
    nginx -s reload
    echo "  nginx 已重载"
fi

echo ""
echo "========================================="
echo "  部署完成！前端地址: http://$(hostname -I | awk '{print $1}'):5173"
echo "  如需回退到 Vite dev server:"
echo "    rm $NGINX_CONF_DIR/mentorai-frontend.conf"
echo "    nginx -s reload"
echo "    npm run dev -- --host 0.0.0.0"
echo "========================================="
