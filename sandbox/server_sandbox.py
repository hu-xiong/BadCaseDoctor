"""
云端沙箱最小服务入口（仅暴露 sandbox 相关接口）

用于 Docker 部署（python:3.11-slim），不依赖主应用其它模块。
- GET  /healthz
- POST /api/v1/execute
- GET  /api/v1/jobs/<job_id>
- POST /api/v1/db/sync
- GET  /api/v1/db/versions

建议环境变量：
- SANDBOX_USE_DIRECT_SQLITE=1  # 无 Docker 时直接用 sqlite3 执行
- SANDBOX_DB_DIR=/opt/sandbox_db
- SANDBOX_DB_PATH=/opt/sandbox_db/default/current.db  # 可选，单租户
"""
import os
import sys

# 确保项目根在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from routers.sandbox import sandbox_bp

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "sandbox-secret")
app.register_blueprint(sandbox_bp)

@app.route("/")
def index():
    return {"service": "cloud-sandbox", "docs": "GET /healthz, POST /api/v1/execute, GET /api/v1/jobs/<id>, POST /api/v1/db/sync"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
