"""
沙箱清理：调用云端 POST /api/v1/db/cleanup，按策略清理历史 DB 版本，供定时任务使用。

在项目根目录执行:
  python sandbox/sandbox_cleanup.py

环境变量:
  SANDBOX_REMOTE_URL    沙箱 base URL（必填）
  SANDBOX_REMOTE_TOKEN  鉴权 Bearer（云端开鉴权时必填）
  SANDBOX_TENANT_ID     只清理该租户；不设则清理 default
  SANDBOX_CLEANUP_KEEP_LAST   保留最近 N 个版本（默认 10）
  SANDBOX_CLEANUP_MAX_AGE_HOURS  删除超过 N 小时的版本（默认 72）
  SANDBOX_CLEANUP_ALL_TENANTS   1 时清理所有租户（需鉴权）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def main():
    from sandbox.utils.cloud_sandbox_client import CloudSandboxHttpConfig, cleanup_remote

    cfg = CloudSandboxHttpConfig.from_env()
    if not cfg.base_url:
        print("请设置 SANDBOX_REMOTE_URL", file=sys.stderr)
        raise SystemExit(2)
    keep_last = _int_env("SANDBOX_CLEANUP_KEEP_LAST", 10)
    max_age_hours = _int_env("SANDBOX_CLEANUP_MAX_AGE_HOURS", 72)
    all_tenants = (os.getenv("SANDBOX_CLEANUP_ALL_TENANTS") or "").strip().lower() in ("1", "true", "yes")

    print("沙箱清理: %s keep_last=%s max_age_hours=%s all_tenants=%s" % (cfg.base_url, keep_last, max_age_hours, all_tenants))
    try:
        out = cleanup_remote(cfg, keep_last=keep_last, max_age_hours=max_age_hours, all_tenants=all_tenants)
        if out.get("success"):
            for r in out.get("results") or []:
                deleted = r.get("deleted") or []
                errors = r.get("errors") or []
                print("  tenant=%s deleted=%s errors=%s" % (r.get("tenant_id"), len(deleted), len(errors)))
            print("完成")
        else:
            print("失败:", out)
            sys.exit(1)
    except Exception as e:
        print("异常:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
