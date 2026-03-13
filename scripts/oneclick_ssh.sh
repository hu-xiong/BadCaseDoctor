#!/bin/bash
# 本地一键：上传沙箱所需文件到云端 → 云端构建并启动 → 本地自检（会提示输入 SSH 密码）
# 在项目根目录执行: bash scripts/oneclick_ssh.sh
# 或: SANDBOX_SSH=root@117.72.33.38 bash scripts/oneclick_ssh.sh

set -e
SSH="${SANDBOX_SSH:-root@117.72.33.38}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=============================================="
echo "沙箱一键（本地执行，会提示输入 SSH 密码）"
echo "=============================================="
echo "SSH 目标: $SSH"
echo ""

# 1) 打一个只含沙箱部署用文件的 tar（保持目录结构）
echo "[1/4] 打包沙箱部署文件..."
TAR="/tmp/sandbox-deploy-$$.tar.gz"
mkdir -p "$ROOT/.oneclick_bundle/sandbox" "$ROOT/.oneclick_bundle/routers" "$ROOT/.oneclick_bundle/agents/tools/text2sql" "$ROOT/.oneclick_bundle/scripts"
cp Dockerfile.sandbox requirements-sandbox.txt "$ROOT/.oneclick_bundle/"
# 放入 sandbox/ 以匹配 Dockerfile 的 COPY sandbox/server_sandbox.py
cp sandbox/server_sandbox.py "$ROOT/.oneclick_bundle/sandbox/"
cp routers/sandbox.py "$ROOT/.oneclick_bundle/routers/"
touch "$ROOT/.oneclick_bundle/routers/__init__.py"
cp agents/tools/text2sql/sandbox_executor.py agents/tools/text2sql/sql_code_wrapper.py agents/tools/text2sql/__init__.py "$ROOT/.oneclick_bundle/agents/tools/text2sql/"
touch "$ROOT/.oneclick_bundle/agents/__init__.py" "$ROOT/.oneclick_bundle/agents/tools/__init__.py"
cp scripts/cloud_deploy_sandbox.sh "$ROOT/.oneclick_bundle/scripts/"
tar -czf "$TAR" -C "$ROOT/.oneclick_bundle" .
rm -rf "$ROOT/.oneclick_bundle"
echo "    已生成 $TAR"

# 2) 上传并解压到云端，执行部署脚本
echo ""
echo "[2/4] 上传并 SSH 执行部署（需输入 SSH 密码）..."
scp -o StrictHostKeyChecking=accept-new "$TAR" "$SSH:/tmp/sandbox-deploy.tar.gz"
ssh "$SSH" "rm -rf /tmp/sandbox-deploy && mkdir -p /tmp/sandbox-deploy && tar -xzf /tmp/sandbox-deploy.tar.gz -C /tmp/sandbox-deploy && cd /tmp/sandbox-deploy && bash scripts/cloud_deploy_sandbox.sh"
rm -f "$TAR"
echo "    云端部署完成"

# 3) 本地自检
echo ""
echo "[3/4] 本地自检（同步 DB + 执行 SQL + 预览）..."
python sandbox/sandbox_oneclick.py

echo ""
echo "[4/4] 一键流程结束"
