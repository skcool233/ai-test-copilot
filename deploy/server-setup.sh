#!/usr/bin/env bash
# 在服务器上执行（需 root）。幂等：可重复运行做更新。
# 前置：代码已位于 /opt/ai-test-copilot，/etc/ai-test-copilot.env 已写好。
#
# 用 uv 管理一个独立的 Python 3.12，不依赖系统 Python 版本与发行版包管理器，
# 因此在 CentOS 7 这类老旧/EOL 系统上也能跑起来。
set -euo pipefail

APP_DIR=/opt/ai-test-copilot
ENV_FILE=/etc/ai-test-copilot.env

if [[ ! -f "$ENV_FILE" ]]; then
  echo "缺少 $ENV_FILE（需含 LLM_API_KEY / PORT，可选 LLM_BASE_URL / LLM_MODEL / APP_PASSWORD）" >&2
  exit 1
fi

echo "==> 安装 uv（如未安装）"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

echo "==> 用 uv 准备 Python 3.12 + venv"
uv venv --python 3.12 "$APP_DIR/.venv"

echo "==> 安装依赖（含 web）"
uv pip install --python "$APP_DIR/.venv/bin/python" -e "$APP_DIR[web]"

echo "==> 安装并启动 systemd 服务"
install -m 644 "$APP_DIR/deploy/ai-test-copilot.service" /etc/systemd/system/ai-test-copilot.service
systemctl daemon-reload
systemctl enable ai-test-copilot >/dev/null 2>&1 || true
systemctl restart ai-test-copilot

sleep 3
echo "==> 健康检查"
PORT=$(grep -E '^PORT=' "$ENV_FILE" | cut -d= -f2)
curl -fsS "http://127.0.0.1:${PORT:-8000}/healthz" && echo
echo "==> 完成。systemctl status ai-test-copilot 查看运行状态。"
