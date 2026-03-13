"""
本地启动沙箱服务（不依赖 Docker），用于本机调试云端同款接口。

在项目根目录执行:
  python sandbox/run_local_sandbox.py

默认端口 5000，可用环境变量覆盖:
  PORT=5000
  SANDBOX_DB_DIR=...
  SANDBOX_USE_DIRECT_SQLITE=1
"""

from __future__ import annotations

import os
import pathlib


def main():
    # 本地：贴近云端接口，且用完即清理（job 结果短保留、sync 后立即清理旧版本）
    os.environ.setdefault("SANDBOX_USE_DIRECT_SQLITE", "1")
    os.environ.setdefault("SANDBOX_DB_DIR", str(pathlib.Path.cwd() / ".local_sandbox_db"))
    os.environ.setdefault("PORT", os.getenv("PORT", "5000"))
    os.environ.setdefault("SANDBOX_JOB_RETENTION_FINISHED_S", "60")
    os.environ.setdefault("SANDBOX_CLEANUP_AFTER_SYNC", "1")
    os.environ.setdefault("SANDBOX_CLEANUP_KEEP_AFTER_SYNC", "2")

    db_dir = pathlib.Path(os.environ["SANDBOX_DB_DIR"])
    (db_dir / "default").mkdir(parents=True, exist_ok=True)

    # 从 sandbox 包中导入 server_sandbox（已移动到 sandbox/ 目录）
    from sandbox import server_sandbox

    port = int(os.getenv("PORT", "5000"))
    print("=" * 60)
    print("本地沙箱服务已启动")
    print(f"- URL: http://127.0.0.1:{port}")
    print("- Healthz: GET /healthz")
    print("=" * 60)
    server_sandbox.app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()

