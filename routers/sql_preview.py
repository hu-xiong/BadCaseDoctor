"""
通用 Text2SQL 沙箱预览 API

支持用户提供的 MySQL/Oracle 等连接，在本地 SQLite 上做安全预览：
- 90% 简单 SQL：精确预览
- 9% 复杂 SQL：带警告的预览
- 1% 极端 SQL：无法预览，提示人工确认

接口：POST /api/v1/sql-preview
"""

from flask import Blueprint, jsonify, request

try:
    from agents.tools.sql_preview import preview_select
    from agents.tools.sql_preview.preview import preview_auto
    SQL_PREVIEW_AVAILABLE = True
except ImportError:
    SQL_PREVIEW_AVAILABLE = False

sql_preview_bp = Blueprint("sql_preview", __name__)


@sql_preview_bp.route("/api/v1/sql-preview", methods=["POST"])
def api_sql_preview():
    """
    通用 SQL 只读预览

    Request JSON:
        sql: str - 原始 SQL（源方言）
        src_dialect: str - 源方言，默认 mysql
        mode: str - select（只预览 SELECT）| auto（默认，支持 UPDATE/DELETE 方案2）

        # 新版推荐：明确区分源库与沙箱
        source: dict - 源数据源（用于抓取命中行/抽样）
            - type: sqlite | mysql | ...
            - sqlite: { "path": "/path/to/db.sqlite" }
            - mysql: { "host": "...", "port": 3306, "user": "...", "password": "...", "database": "..." }
        sandbox: dict - 云端沙箱配置（用于上传子集与执行预览）
            - base_url: "http://your-sandbox-host:5000"
            - token: "..."（可选）
            - tenant_id: "..."（可选）

        # 兼容旧版：仍可使用 data_source
        data_source: dict - 旧版数据源配置（不建议继续使用）

        max_rows: int - 返回行数上限，默认 200
        sample_rows: int - MySQL 采样每表行数，默认 500
    """
    if not SQL_PREVIEW_AVAILABLE:
        return jsonify({
            "success": False,
            "error": "SQL 预览模块未安装或不可用",
            "rows": [],
            "columns": [],
        }), 500

    data = request.get_json(force=True, silent=True) or {}
    sql = data.get("sql", "").strip()
    if not sql:
        return jsonify({
            "success": False,
            "error": "缺少参数 sql",
            "rows": [],
            "columns": [],
        }), 400

    src_dialect = data.get("src_dialect", "mysql")
    data_source = data.get("data_source") or {}
    source = data.get("source") or None
    sandbox = data.get("sandbox") or None
    max_rows = int(data.get("max_rows", 200))
    sample_rows = int(data.get("sample_rows", 500))
    mode = (data.get("mode") or "auto").strip().lower()

    if mode == "select":
        # select 模式：优先用 source 作为数据源（兼容旧 data_source）
        if source and not data_source:
            data_source = source
        result = preview_select(
            sql=sql,
            src_dialect=src_dialect,
            data_source=data_source,
            max_rows=max_rows,
            sample_rows=sample_rows,
        )
    else:
        result = preview_auto(
            sql=sql,
            src_dialect=src_dialect,
            data_source=data_source,
            source=source,
            sandbox=sandbox,
            max_rows=max_rows,
            sample_rows=sample_rows,
        )

    return jsonify(result)
