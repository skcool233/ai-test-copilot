#!/usr/bin/env bash
# 在服务器上执行（需 root / sudo）。幂等：可重复运行做更新。
# 前置：代码已位于 /opt/ai-test-copilot，/etc/ai-test-copilot.env 已写好。
set -euo pipefail

APP_DIR=/opt/ai-test-copilot
ENV_FILE=/etc/ai-test-copilot.env

if [[ ! -f "$ENV_FILE" ]]; then
  echo "缺少 $ENV_FILE（需含 ANTHROPIC_API_KEY / PORT，可选 APP_PASSWORD / AI_TEST_COPILOT_MODEL）" >&2
  exit 1
fi

echo "==> 安装系统依赖（python3-venv / git）"
if command -v apt-get >/dev/null; then
  apt-get update -qq
  apt-get install -y -qq python3-venv python3-pip git
elif command -v yum >/dev/null; then
  yum install -y -q python3 git
fi

echo "==> 建/更新 virtualenv 并安装依赖"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -e "$APP_DIR[web]"

echo "==> 安装 systemd 服务"
install -m 644 "$APP_DIR/deploy/ai-test-copilot.service" /etc/systemd/system/ai-test-copilot.service
systemctl daemon-reload
systemctl enable ai-test-copilot >/dev/null 2>&1 || true
systemctl restart ai-test-copilot

sleep 2
echo "==> 健康检查"
PORT=$(grep -E '^PORT=' "$ENV_FILE" | cut -d= -f2)
curl -fsS "http://127.0.0.1:${PORT:-8000}/healthz" && echo
echo "==> 完成。systemctl status ai-test-copilot 查看运行状态。"
