#!/bin/bash
# 在云端服务器（有 Docker）上执行的一键部署
# 用法：在项目根目录执行  bash scripts/cloud_deploy_sandbox.sh
# 注意：本文件请保持 LF 换行，否则在 Linux 上会报 $'\r': command not found

set -e
cd "$(dirname "$0")/.."
echo "[1/4] 构建镜像..."
docker build -f Dockerfile.sandbox -t badcase-sandbox:latest .
echo "[2/4] 停止旧容器并释放 5000 端口..."
docker stop sandbox 2>/dev/null || true
docker rm sandbox 2>/dev/null || true
# 若有其他容器占用 5000 端口也一并停掉（旧容器可能不叫 sandbox）
for cid in $(docker ps -q --filter "publish=5000" 2>/dev/null); do docker stop "$cid" 2>/dev/null || true; done
sleep 1
for cid in $(docker ps -aq --filter "publish=5000" 2>/dev/null); do docker rm -f "$cid" 2>/dev/null || true; done
sleep 1
echo "[3/4] 创建数据目录..."
mkdir -p /opt/sandbox_db/default
echo "[4/4] 启动新容器..."

# 若存在 scripts/sandbox_env.sh（一键部署时从本地环境写入），则注入
[ -f scripts/sandbox_env.sh ] && . ./scripts/sandbox_env.sh
# 鉴权（可选）：若设置了 SANDBOX_SERVER_TOKEN 则自动开启鉴权
AUTH_REQUIRED="${SANDBOX_AUTH_REQUIRED:-}"
if [ -n "${SANDBOX_SERVER_TOKEN:-}" ]; then
  AUTH_REQUIRED="true"
fi

docker run -d -p 5000:5000 \
  -e SANDBOX_USE_DIRECT_SQLITE=1 \
  -e SANDBOX_AUTH_REQUIRED="${AUTH_REQUIRED:-false}" \
  -e SANDBOX_SERVER_TOKEN="${SANDBOX_SERVER_TOKEN:-}" \
  -e SANDBOX_REDIS_URL="${SANDBOX_REDIS_URL:-}" \
  -e SANDBOX_RATE_RPM="${SANDBOX_RATE_RPM:-120}" \
  -e SANDBOX_RATE_BURST="${SANDBOX_RATE_BURST:-60}" \
  -e SANDBOX_MAX_DB_MB="${SANDBOX_MAX_DB_MB:-200}" \
  -v /opt/sandbox_db:/opt/sandbox_db \
  --name sandbox \
  --restart unless-stopped \
  badcase-sandbox:latest
echo "完成。健康检查: curl -s http://127.0.0.1:5000/healthz"
