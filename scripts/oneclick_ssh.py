"""
本地一键（会提示输入 SSH 密码）：上传沙箱文件到云端 → 云端构建并启动 → 本地自检

在项目根目录执行: python scripts/oneclick_ssh.py
可选环境变量:
  SANDBOX_SSH=root@your-host
  SANDBOX_SERVER_TOKEN=xxx  # 会透传到云端，开启鉴权
  SANDBOX_AUTH_REQUIRED=true
  SANDBOX_RATE_RPM / SANDBOX_RATE_BURST / SANDBOX_MAX_DB_MB  # 限流与上传限制
"""
import os
import subprocess
import sys
import tempfile
import shutil

def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)
    ssh = (os.getenv("SANDBOX_SSH") or "").strip()
    if not ssh:
        print("请设置 SANDBOX_SSH，例如: SANDBOX_SSH=root@your-host", file=sys.stderr)
        raise SystemExit(2)

    print("=" * 60)
    print("沙箱一键（会提示输入 SSH 密码）")
    print("=" * 60)
    print("SSH 目标:", ssh)
    print()

    # 1) 打包
    print("[1/4] 打包沙箱部署文件...")
    bundle = os.path.join(tempfile.gettempdir(), "sandbox_deploy_bundle")
    if os.path.exists(bundle):
        shutil.rmtree(bundle)
    os.makedirs(os.path.join(bundle, "sandbox"), exist_ok=True)
    os.makedirs(os.path.join(bundle, "routers"), exist_ok=True)
    os.makedirs(os.path.join(bundle, "agents", "tools", "text2sql"), exist_ok=True)
    os.makedirs(os.path.join(bundle, "scripts"), exist_ok=True)

    for f in ["Dockerfile.sandbox", "requirements-sandbox.txt"]:
        shutil.copy2(os.path.join(root, f), os.path.join(bundle, f))
    # 放入 sandbox/ 以匹配 Dockerfile 的 COPY sandbox/server_sandbox.py
    shutil.copy2(os.path.join(root, "sandbox", "server_sandbox.py"), os.path.join(bundle, "sandbox", "server_sandbox.py"))
    shutil.copy2(os.path.join(root, "routers", "sandbox.py"), os.path.join(bundle, "routers", "sandbox.py"))
    for f in ["sandbox_executor.py", "sql_code_wrapper.py", "__init__.py"]:
        shutil.copy2(
            os.path.join(root, "agents", "tools", "text2sql", f),
            os.path.join(bundle, "agents", "tools", "text2sql", f),
        )
    # 复制部署脚本并转为 Unix 换行(LF)，避免 Windows CRLF 在云端报错
    with open(os.path.join(root, "scripts", "cloud_deploy_sandbox.sh"), "rb") as f:
        sh_cont = f.read().decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    with open(os.path.join(bundle, "scripts", "cloud_deploy_sandbox.sh"), "w", newline="\n", encoding="utf-8") as f:
        f.write(sh_cont)
    # 把本地环境变量写入 sandbox_env.sh，部署时 source 后云端容器可开启鉴权/限流等
    env_vars = [
        "SANDBOX_SERVER_TOKEN",
        "SANDBOX_AUTH_REQUIRED",
        "SANDBOX_REDIS_URL",
        "SANDBOX_RATE_RPM",
        "SANDBOX_RATE_BURST",
        "SANDBOX_MAX_DB_MB",
    ]
    def sh_escape(s):
        return str(s).replace("\\", "\\\\").replace('"', '\\"')

    lines = []
    for k in env_vars:
        v = os.environ.get(k)
        if v is not None and str(v).strip():
            lines.append(f'export {k}="{sh_escape(v)}"')
    with open(os.path.join(bundle, "scripts", "sandbox_env.sh"), "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    for d, name in [(bundle, "routers"), (bundle, "agents"), (os.path.join(bundle, "agents"), "tools")]:
        open(os.path.join(d, name, "__init__.py"), "w").close()

    tar_path = os.path.join(tempfile.gettempdir(), "sandbox_deploy.tar.gz")
    if sys.platform == "win32":
        import tarfile
        with tarfile.open(tar_path, "w:gz") as tf:
            for n in os.listdir(bundle):
                tf.add(os.path.join(bundle, n), arcname=n)
    else:
        subprocess.run(["tar", "-czf", tar_path, "-C", bundle, "."], check=True)
    shutil.rmtree(bundle)
    print("    已生成", tar_path)

    # 2) scp + ssh（会提示密码）
    print()
    print("[2/4] 上传并 SSH 执行部署（需输入 SSH 密码）...")
    remote_tar = "/tmp/sandbox-deploy.tar.gz"
    remote_dir = "/tmp/sandbox-deploy"
    scp = subprocess.run(["scp", "-o", "StrictHostKeyChecking=accept-new", tar_path, f"{ssh}:{remote_tar}"])
    if scp.returncode != 0:
        print("    scp 失败，请检查 SSH 地址与密码")
        sys.exit(1)
    ssh_cmd = f"rm -rf {remote_dir} && mkdir -p {remote_dir} && tar -xzf {remote_tar} -C {remote_dir} && cd {remote_dir} && bash scripts/cloud_deploy_sandbox.sh"
    run = subprocess.run(["ssh", ssh, ssh_cmd])
    try:
        os.remove(tar_path)
    except Exception:
        pass
    if run.returncode != 0:
        print("    云端部署失败")
        sys.exit(1)
    print("    云端部署完成")

    # 3) 本地自检
    print()
    print("[3/4] 本地自检...")
    sys.path.insert(0, root)
    # sandbox_oneclick 已迁移到 sandbox 包
    from sandbox import sandbox_oneclick
    sandbox_oneclick.main()

    print()
    print("[4/4] 一键流程结束")

if __name__ == "__main__":
    main()
