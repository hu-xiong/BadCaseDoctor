"""
本项目侧：触发云端沙盒 DB 副本同步

用途：
- 将本地 sqlite 副本（例如 instance/badcase_doctor.db）上传到云端沙盒
- 云端收到后保存版本并切换 current.db
"""

from __future__ import annotations

import os
from flask import Blueprint, jsonify, request

from sandbox.utils.cloud_sandbox_client import CloudSandboxHttpConfig, healthz, upload_sqlite_db_and_switch


sandbox_client_bp = Blueprint("sandbox_client", __name__, url_prefix="/api/sandbox")


@sandbox_client_bp.route("/healthz", methods=["GET"])
def cloud_healthz():
    cfg = CloudSandboxHttpConfig.from_env()
    try:
        data = healthz(cfg)
        return jsonify({"success": True, "cloud": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@sandbox_client_bp.route("/db/sync", methods=["POST"])
def sync_db_to_cloud():
    """
    触发上传本地 sqlite 到云端沙盒

    请求 JSON（可选）：
    - tenant_id: 覆盖 SANDBOX_TENANT_ID
    - db_path: 覆盖默认 instance/badcase_doctor.db
    """
    cfg = CloudSandboxHttpConfig.from_env()
    # 如果环境变量未配置，默认使用当前云端沙盒地址，确保可用
    if not cfg.base_url:
        cfg.base_url = "http://117.72.33.38:5000"
    data = request.get_json(silent=True) or {}

    tenant_id = (data.get("tenant_id") or "").strip()
    if tenant_id:
        cfg.tenant_id = tenant_id

    db_path = (data.get("db_path") or "").strip() or os.getenv("LOCAL_DB_PATH", "") or "instance/badcase_doctor.db"

    try:
        ret = upload_sqlite_db_and_switch(cfg, db_path=db_path)
        return jsonify({"success": True, "cloud_result": ret})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "db_path": db_path}), 500

