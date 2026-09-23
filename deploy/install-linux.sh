#!/usr/bin/env bash
# 最小 Linux 安装：venv + 依赖 + systemd 单元（不写业务密钥）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="${BADCASE_APP_DIR:-/opt/badcase-doctor}"
SERVICE_USER="${BADCASE_USER:-badcase}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "请以 root 运行（需要写 /opt 与 systemd）" >&2
  exit 1
fi

id -u "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"

mkdir -p "$APP_DIR"
rsync -a --delete \
  --exclude '.git' --exclude 'venv' --exclude 'electron-vue3/node_modules' \
  --exclude '__pycache__' --exclude '.venv' \
  "$ROOT/" "$APP_DIR/"

if [[ ! -f "$APP_DIR/.env" ]]; then
  if [[ -f "$APP_DIR/.env.example" ]]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo "已生成 $APP_DIR/.env，请先填写密钥后再启动"
  else
    echo "缺少 .env.example，请手动创建 $APP_DIR/.env" >&2
    exit 1
  fi
fi

python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

install -m 644 "$APP_DIR/deploy/badcase-doctor.service" /etc/systemd/system/badcase-doctor.service
# 本机浏览器 CDP 桥服务（反连隧道 Hub + CDP 网关；无 BADCASE_TUNNEL_SECRET 时启动后不接收隧道，可先只 enable 不 start）
install -m 644 "$APP_DIR/deploy/badcase-local-bridge.service" /etc/systemd/system/badcase-local-bridge.service
systemctl daemon-reload
systemctl enable badcase-doctor.service
systemctl enable badcase-local-bridge.service

echo "安装完成。编辑 $APP_DIR/.env（含 BADCASE_TUNNEL_SECRET）后执行: systemctl start badcase-doctor badcase-local-bridge"
echo "健康检查: curl -fsS http://127.0.0.1:5000/health"
