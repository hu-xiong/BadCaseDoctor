from __future__ import annotations

from flask import Blueprint, jsonify, request

from llm.model_registry import list_models


models_bp = Blueprint("models", __name__, url_prefix="/api/models")


@models_bp.route("", methods=["GET"])
@models_bp.route("/", methods=["GET"])
def get_models():
    """
    返回模型注册表（用于前端下拉框/能力展示）。
    Query:
      - include_disabled=1: 也返回 disabled 模型（默认不返回）
    """
    include_disabled = str(request.args.get("include_disabled") or "").strip() in ("1", "true", "yes", "on")
    models = [m.to_public_dict() for m in list_models(include_disabled=include_disabled)]
    return jsonify({"success": True, "models": models})

