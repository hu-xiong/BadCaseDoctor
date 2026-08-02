"""
沙箱功能测试脚本

测试项：
1. 云端 healthz
2. 云端 execute (sql_readonly)
3. 云端 job 轮询
4. 本地 sql-preview (data_source=sandbox) - 需 Flask 运行
"""
import json
import os
import sys
import time

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = (os.getenv("SANDBOX_REMOTE_URL") or "").rstrip("/")
if not BASE_URL:
    print("请设置 SANDBOX_REMOTE_URL", file=sys.stderr)
    raise SystemExit(2)


def req(method: str, path: str, body: bytes = None, headers: dict = None):
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError

    url = f"{BASE_URL.rstrip('/')}{path}"
    h = headers or {}
    if body:
        h = {**h, "Content-Type": "application/json"}
    req_obj = Request(url, data=body, headers=h, method=method.upper())
    try:
        with urlopen(req_obj, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except Exception:
            return {"error": raw or str(e)}
    except URLError as e:
        return {"error": f"连接失败: {e}"}
    except Exception as e:
        return {"error": str(e)}


def main():
    print("=" * 60)
    print("沙箱功能测试")
    print("=" * 60)
    print(f"云端地址: {BASE_URL}")
    print()

    # 1. healthz
    print("[1] GET /healthz")
    r = req("GET", "/healthz")
    if "error" in r:
        print(f"   失败: {r['error']}")
    else:
        print(f"   成功: {r}")
    print()

    # 2. execute
    print("[2] POST /api/v1/execute (task_type=sql_readonly)")
    body = json.dumps({
        "task_type": "sql_readonly",
        "payload": {"sql": "SELECT 1 as x", "db": {"type": "sqlite"}},
        "timeout_ms": 30000,
    }).encode("utf-8")
    r = req("POST", "/api/v1/execute", body=body)
    if "error" in r and "job_id" not in r:
        print(f"   失败: {r}")
        print()
        print("提示: 若返回 unsupported_task_type，说明云端未部署本项目的 sandbox 路由。")
        print("      请将 routers/sandbox.py 部署到云端（与 db/sync 同一服务）")
    elif "job_id" in r:
        job_id = r["job_id"]
        print(f"   已提交 job_id: {job_id}")
        print()
        # 3. 轮询 job
        print("[3] 轮询 GET /api/v1/jobs/...")
        for _ in range(20):
            time.sleep(0.5)
            j = req("GET", f"/api/v1/jobs/{job_id}")
            status = j.get("status", "")
            if status == "succeeded":
                result = j.get("result", {})
                print(f"   成功: data={result.get('data', [])}, columns={result.get('columns', [])}")
                break
            if status == "failed":
                print(f"   失败: {j.get('error', 'unknown')}")
                break
            print(f"   状态: {status} ...")
        else:
            print("   超时")
    print()

    # 4. cloud_sandbox_client.execute_sql
    print("[4] sandbox.utils.cloud_sandbox_client.execute_sql (本地调用云端)")
    try:
        from sandbox.utils.cloud_sandbox_client import CloudSandboxHttpConfig, execute_sql

        cfg = CloudSandboxHttpConfig.from_env()
        r = execute_sql(cfg, "SELECT 1 as x")
        if r.get("success"):
            print(f"   成功: data={r.get('data', [])}")
        else:
            print(f"   失败: {r.get('error', r)}")
    except Exception as e:
        print(f"   异常: {e}")
    print()

    # 5. sql_preview with sandbox
    print("[5] agents.tools.sql_preview.preview_select (data_source=sandbox)")
    try:
        from agents.tools.sql_preview import preview_select

        r = preview_select("SELECT 1 as x", data_source={"type": "sandbox"})
        if r.get("success"):
            print(f"   成功: rows={r.get('rows', [])}, row_count={r.get('row_count')}")
        else:
            print(f"   失败: {r.get('error') or r.get('message')}")
    except Exception as e:
        print(f"   异常: {e}")

    print()
    print("=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
