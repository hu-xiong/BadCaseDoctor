"""
本地一键：不依赖 Docker，完成「同步 DB → 调云端执行 SQL → 自检」
在项目根目录执行: python sandbox/sandbox_oneclick.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    base = os.getenv("SANDBOX_REMOTE_URL", "http://117.72.33.38:5000").rstrip("/")
    print("=" * 60)
    print("沙箱一键（本地无 Docker）")
    print("=" * 60)
    print(f"云端: {base}\n")

    # 0. 先探测云端是否已部署
    print("[0] 探测云端 /healthz ...")
    try:
        from sandbox.utils.cloud_sandbox_client import CloudSandboxHttpConfig, healthz

        cfg0 = CloudSandboxHttpConfig.from_env()
        hz = healthz(cfg0)
        print("    OK:", hz.get("service", ""), "auth_required=%s" % hz.get("auth_required"), "rate_backend=%s" % (hz.get("rate_limit") or {}).get("backend"))
    except Exception as e:
        print("    失败:", e)
        print()
        print("云端看起来尚未部署/不可用。你可以用下面任一方式同步部署：")
        print("  - Windows/跨平台: python scripts/oneclick_ssh.py")
        print("  - Linux/macOS:     bash scripts/oneclick_ssh.sh")
        print("然后再重试本脚本。")
        return

    # 1. 同步 DB（可选，本地有 instance/badcase_doctor.db 则上传）
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(root, "instance", "badcase_doctor.db")
    if os.path.isfile(db_path):
        print("[1] 上传 DB 到云端...")
        try:
            from sandbox.utils.cloud_sandbox_client import CloudSandboxHttpConfig, upload_sqlite_db_and_switch
            cfg = CloudSandboxHttpConfig.from_env()
            ret = upload_sqlite_db_and_switch(cfg, db_path=db_path)
            print("    成功:", ret.get("status"), ret.get("current_db", ""))
        except Exception as e:
            print("    跳过(可手动同步):", e)
    else:
        print("[1] 未找到 instance/badcase_doctor.db，跳过上传")

    # 2. 调云端执行 SQL
    print("\n[2] 云端执行 SELECT 1 as x ...")
    try:
        from sandbox.utils.cloud_sandbox_client import CloudSandboxHttpConfig, execute_sql
        cfg = CloudSandboxHttpConfig.from_env()
        r = execute_sql(cfg, "SELECT 1 as x")
        if r.get("success"):
            print("    成功:", r.get("data"))
        else:
            print("    失败:", r.get("error"))
    except Exception as e:
        print("    失败:", e)

    # 3. SQL 预览（走云端 sandbox）
    print("\n[3] SQL 预览(data_source=sandbox)...")
    try:
        from agents.tools.sql_preview import preview_select
        r = preview_select("SELECT 1 as x", data_source={"type": "sandbox"})
        if r.get("success"):
            print("    成功: row_count=%s" % r.get("row_count"))
        else:
            print("    失败:", r.get("error") or r.get("message"))
    except Exception as e:
        print("    失败:", e)

    print("\n" + "=" * 60)
    print("一键流程结束。云端未部署时请先在服务器执行:")
    print("  cd /path/to/BadCaseDoctor && bash scripts/cloud_deploy_sandbox.sh")
    print("=" * 60)

if __name__ == "__main__":
    main()
