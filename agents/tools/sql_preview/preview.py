"""
通用 Text2SQL 沙箱预览主入口

使用方式：
    from agents.tools.sql_preview import preview_select

    # 本地数据源（SQLite/MySQL 采样）
    result = preview_select(sql, src_dialect="mysql", data_source={"type": "mysql", ...})

    # 云端沙箱（使用已同步的 DB 副本）
    result = preview_select(sql, data_source={"type": "sandbox"})
"""

import os
from typing import Any, Dict, Optional

from .dialect_adapter import SqlDialectAdapter, SUPPORTED_DIALECTS
from .complexity import SqlComplexityAnalyzer, SqlComplexityLevel
from .dml_preview import parse_single_table_update_or_delete
from .insert_preview import parse_single_table_insert
from .executor import SqlPreviewExecutor
from .sampler import DataSourceSampler
from .subset_builder import build_subset_sqlite_file, fetch_table_columns, create_empty_subset_sqlite, fetch_rows_by_select
from .diff_utils import diff_rows


def _simulate_dml_and_diff(
    subset_path: str,
    dml_sqlite: str,
    impact_select_sqlite: str,
    pk: str = "id",
    max_rows: int = 200,
) -> Dict[str, Any]:
    """
    在子集 SQLite 上模拟执行 DML（在临时副本上），并返回字段级 diff。

    说明：
    - 这一步不在云端沙箱执行（因为云端只读接口不允许 UPDATE/DELETE）
    - 仅对“子集库”执行，数据量很小
    """
    import os
    import sqlite3
    import tempfile
    import uuid

    tmp_copy = os.path.join(tempfile.gettempdir(), f"subset_sim_{uuid.uuid4().hex[:8]}.db")
    try:
        # 复制子集库
        src = sqlite3.connect(subset_path)
        dst = sqlite3.connect(tmp_copy)
        src.backup(dst)
        src.close()

        # before：在原 subset 上取影响行
        before_conn = sqlite3.connect(subset_path)
        before_conn.row_factory = sqlite3.Row
        before_rows = [dict(r) for r in before_conn.execute(impact_select_sqlite).fetchall()]
        before_conn.close()

        # apply：在副本上执行 DML
        dst.execute("BEGIN")
        dst.execute(dml_sqlite)
        dst.commit()

        # after：在副本上取影响行（同 WHERE）
        dst.row_factory = sqlite3.Row
        after_rows = [dict(r) for r in dst.execute(impact_select_sqlite).fetchall()]

        # 建 map
        def _key(r: Dict[str, Any]) -> Any:
            return r.get(pk)

        before_map = { _key(r): r for r in before_rows if _key(r) is not None }
        after_map = { _key(r): r for r in after_rows if _key(r) is not None }
        all_ids = list(dict.fromkeys(list(before_map.keys()) + list(after_map.keys())))

        diffs = []
        for rid in all_ids[:max_rows]:
            b = before_map.get(rid)
            a = after_map.get(rid)
            if b is None and a is not None:
                diffs.append({"row_id": rid, "op": "inserted", "before": None, "after": a, "changed_fields": list(a.keys()), "changes": {k: {"before": None, "after": v} for k, v in a.items()}})
            elif b is not None and a is None:
                diffs.append({"row_id": rid, "op": "deleted", "before": b, "after": None, "changed_fields": list(b.keys()), "changes": {k: {"before": v, "after": None} for k, v in b.items()}})
            elif b is not None and a is not None:
                d = diff_rows(b, a)
                diffs.append({"row_id": rid, "op": "updated" if d["changed_fields"] else "unchanged", "before": b, "after": a, **d})

        return {
            "success": True,
            "before_row_count": len(before_rows),
            "after_row_count": len(after_rows),
            "diffs": diffs,
        }
    finally:
        try:
            dst.close()
        except Exception:
            pass


def _simulate_insert_rows_and_diff(
    subset_path: str,
    table: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    impact_select_sqlite: str,
    pk: str = "id",
    max_rows: int = 200,
) -> Dict[str, Any]:
    """
    专用于 INSERT...SELECT：将已抓取的 rows 插入子集库副本并生成 diff。
    """
    import os
    import sqlite3
    import tempfile
    import uuid

    tmp_copy = os.path.join(tempfile.gettempdir(), f"subset_sim_{uuid.uuid4().hex[:8]}.db")
    try:
        src = sqlite3.connect(subset_path)
        dst = sqlite3.connect(tmp_copy)
        src.backup(dst)
        src.close()

        # before：空表
        before_rows: list[dict[str, Any]] = []

        # apply：插入 rows（仅插入指定 columns）
        col_list = ", ".join([f"\"{c}\"" for c in columns])
        placeholders = ", ".join(["?"] * len(columns))
        ins_sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})'
        dst.execute("BEGIN")
        for r in rows:
            vals = []
            for c in columns:
                v = r.get(c)
                if isinstance(v, (dict, list)):
                    v = str(v)
                vals.append(v)
            dst.execute(ins_sql, vals)
        dst.commit()

        dst.row_factory = sqlite3.Row
        after_rows = [dict(rr) for rr in dst.execute(impact_select_sqlite).fetchall()]

        # diffs：全部视为 inserted
        diffs = []
        for rr in after_rows[:max_rows]:
            rid = rr.get(pk)
            if rid is None:
                rid = len(diffs) + 1
            diffs.append({
                "row_id": rid,
                "op": "inserted",
                "before": None,
                "after": rr,
                "changed_fields": list(rr.keys()),
                "changes": {k: {"before": None, "after": v} for k, v in rr.items()},
            })

        return {"success": True, "before_row_count": 0, "after_row_count": len(after_rows), "diffs": diffs}
    finally:
        try:
            dst.close()
        except Exception:
            pass
        try:
            if os.path.exists(tmp_copy):
                os.remove(tmp_copy)
        except Exception:
            pass
        try:
            if os.path.exists(tmp_copy):
                os.remove(tmp_copy)
        except Exception:
            pass


def _preview_via_cloud_sandbox(
    sql: str,
    src_dialect: str,
    max_rows: int,
    data_source: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """走云端沙箱执行只读 SQL，返回与 preview_select 一致的结构。"""
    try:
        from sandbox.utils.cloud_sandbox_client import CloudSandboxHttpConfig, execute_sql
    except ImportError:
        return {
            "success": False,
            "previewable": False,
            "level": "complex",
            "rows": [],
            "columns": [],
            "row_count": 0,
            "warning": None,
            "message": "未配置云端沙箱客户端（sandbox.utils.cloud_sandbox_client）",
            "error": "未配置云端沙箱客户端",
        }

    analyzer = SqlComplexityAnalyzer()
    if analyzer.analyze(sql) == SqlComplexityLevel.COMPLEX:
        return {
            "success": False,
            "previewable": False,
            "level": "complex",
            "rows": [],
            "columns": [],
            "row_count": 0,
            "warning": None,
            "message": "SQL 过于复杂（可能包含 DDL/DML 等），无法在沙箱中预览，请人工确认。",
            "error": "SQL 过于复杂，无法预览",
        }

    adapter = SqlDialectAdapter(src_dialect=src_dialect)
    sqlite_sql = adapter.to_sqlite(sql)

    cfg = CloudSandboxHttpConfig.from_env()
    # 允许通过 data_source 覆盖云端连接信息（便于按 proposal 分租户、或指定不同沙箱地址）
    data_source = data_source or {}
    if data_source.get("base_url"):
        cfg.base_url = str(data_source.get("base_url")).rstrip("/")
    if data_source.get("token"):
        cfg.token = str(data_source.get("token"))
    if data_source.get("tenant_id"):
        cfg.tenant_id = str(data_source.get("tenant_id"))
    if not cfg.base_url:
        return {
            "success": False,
            "previewable": False,
            "level": "complex",
            "rows": [],
            "columns": [],
            "row_count": 0,
            "warning": None,
            "message": "未配置 SANDBOX_REMOTE_URL，无法使用云端沙箱预览",
            "error": "未配置 SANDBOX_REMOTE_URL",
        }

    result = execute_sql(cfg, sqlite_sql)
    rows = (result.get("data") or [])[:max_rows]
    columns = result.get("columns") or []
    return {
        "success": result.get("success", False),
        "previewable": result.get("success", False),
        "level": "simple",
        "rows": rows,
        "columns": columns,
        "row_count": len(rows),
        "warning": None,
        "message": result.get("error") if not result.get("success") else None,
        "error": result.get("error"),
    }


def preview_select(
    sql: str,
    src_dialect: str = "mysql",
    data_source: Optional[Dict[str, Any]] = None,
    sqlite_path: Optional[str] = None,
    max_rows: int = 200,
    sample_rows: int = 500,
) -> Dict[str, Any]:
    """
    通用 SQL 只读预览（SELECT）

    Args:
        sql: 原始 SQL（源方言）
        src_dialect: 源方言，如 mysql / oracle / sqlite
        data_source: 数据源配置
            - type: sqlite | mysql | sandbox | ...
            - sqlite: {"path": "/path/to/db.sqlite"}
            - mysql: {"host": "...", "port": 3306, "user": "...", "password": "...", "database": "..."}
            - sandbox: 使用云端沙箱内已同步的 DB 副本执行（需配置 SANDBOX_REMOTE_URL）
        sqlite_path: 若为 sqlite 且直接给路径，可简化传此参数
        max_rows: 返回预览行数上限
        sample_rows: 从 MySQL 等采样时每表行数

    Returns:
        {
            "success": bool,
            "previewable": bool,
            "level": "simple" | "medium" | "complex",
            "rows": [...],
            "columns": [...],
            "row_count": int,
            "warning": str | None,
            "message": str | None,
            "error": str | None,
        }
    """
    data_source = data_source or {}
    if sqlite_path:
        data_source = {"type": "sqlite", "path": sqlite_path}
    ds_type = (data_source.get("type") or "sqlite").strip().lower()

    if ds_type == "sandbox":
        if src_dialect not in SUPPORTED_DIALECTS:
            src_dialect = "mysql"
        return _preview_via_cloud_sandbox(sql, src_dialect, max_rows, data_source=data_source)

    if src_dialect not in SUPPORTED_DIALECTS:
        src_dialect = "mysql"  # 默认

    try:
        adapter = SqlDialectAdapter(src_dialect=src_dialect)
        sampler = DataSourceSampler(sample_rows=sample_rows)
        conn = sampler.build_sqlite(db_type=ds_type, config=data_source)

        executor = SqlPreviewExecutor(adapter=adapter, max_rows=max_rows)
        out = executor.preview(sql, conn)
        conn.close()

        return {
            "success": out["previewable"],
            "previewable": out["previewable"],
            "level": out["level"],
            "rows": out["rows"],
            "columns": out["columns"],
            "row_count": out["row_count"],
            "warning": out.get("warning"),
            "message": out.get("message"),
            "error": None if out["previewable"] else (out.get("message") or "预览失败"),
        }

    except Exception as e:
        return {
            "success": False,
            "previewable": False,
            "level": "complex",
            "rows": [],
            "columns": [],
            "row_count": 0,
            "warning": None,
            "message": str(e),
            "error": str(e),
        }


def preview_auto(
    sql: str,
    src_dialect: str = "mysql",
    data_source: Optional[Dict[str, Any]] = None,
    source: Optional[Dict[str, Any]] = None,
    sandbox: Optional[Dict[str, Any]] = None,
    max_rows: int = 200,
    sample_rows: int = 500,
) -> Dict[str, Any]:
    """
    通用预览入口（方案2）：
    - SELECT：复用 preview_select
    - UPDATE/DELETE：转为“影响行 SELECT”，抽取子集 SQLite → 上传云端沙箱（可选）→ 返回影响行

    约束：
    - 仅支持单表 UPDATE/DELETE（复杂 SQL 返回无法预览）
    """
    # 兼容旧入参 data_source；新版用 source + sandbox
    data_source = data_source or {}
    source = source or None
    sandbox = sandbox or None
    source_cfg: Dict[str, Any] = dict(source or {})
    sandbox_cfg: Dict[str, Any] = dict(sandbox or {})
    if not source_cfg and data_source:
        # 旧版：data_source 作为 source（抓取命中行/抽样）
        source_cfg = dict(data_source)
    if not sandbox_cfg and data_source:
        # 旧版：如果 data_source.type=sandbox 或携带 base_url/token/tenant_id，则作为 sandbox 配置
        if (data_source.get("type") or "").strip().lower() == "sandbox" or any(k in data_source for k in ("base_url", "token", "tenant_id")):
            sandbox_cfg = {k: data_source.get(k) for k in ("base_url", "token", "tenant_id", "type") if k in data_source}

    sql_clean = (sql or "").strip()
    if not sql_clean:
        return {"success": False, "previewable": False, "level": "complex", "rows": [], "columns": [], "row_count": 0, "error": "SQL 为空", "message": "SQL 为空"}

    upper = sql_clean.upper()
    if upper.startswith("SELECT"):
        # SELECT：仍沿用 preview_select（source_cfg 作为数据源；若需要走云端，用户应直接 mode=select + data_source.type=sandbox）
        return preview_select(sql, src_dialect=src_dialect, data_source=source_cfg, max_rows=max_rows, sample_rows=sample_rows)

    impact = parse_single_table_update_or_delete(sql_clean)
    ins = parse_single_table_insert(sql_clean)
    if not impact and not ins:
        return {
            "success": False,
            "previewable": False,
            "level": "complex",
            "rows": [],
            "columns": [],
            "row_count": 0,
            "warning": None,
            "message": "仅支持单表 UPDATE/DELETE 的自动预览；复杂 SQL（JOIN/子查询/无 WHERE/多语句）需人工确认。",
            "error": "SQL 过于复杂，无法自动预览",
        }

    if src_dialect not in SUPPORTED_DIALECTS:
        src_dialect = "mysql"

    adapter = SqlDialectAdapter(src_dialect=src_dialect)

    # 方案2必须要有 source（源库），否则无法抓命中行/获取 schema
    if not source_cfg or not (source_cfg.get("type") or "").strip():
        return {
            "success": False,
            "previewable": False,
            "level": "complex",
            "rows": [],
            "columns": [],
            "row_count": 0,
            "warning": None,
            "message": "DML 预览需要提供 source（源库连接）以抓取命中行/构建子集库。",
            "error": "缺少 source（源库）配置",
        }

    subset_path = ""
    impact_select_src = ""
    if impact:
        # UPDATE/DELETE：影响行查询：在源库上执行（只读）
        impact_select_src = impact.to_select_sql(columns="*")
        subset_path = build_subset_sqlite_file(
            data_source=source_cfg,
            table=impact.table.strip("`\""),
            select_sql=impact_select_src,
        )
    else:
        # INSERT：先根据源库 schema 创建空子集库，再在子集上模拟执行 INSERT
        table = ins.table.strip("`\"")  # type: ignore[union-attr]
        cols = fetch_table_columns(source_cfg, table=table)
        subset_path = create_empty_subset_sqlite(table=table, columns=cols)
        impact_select_src = f"SELECT * FROM {ins.table}"  # type: ignore[union-attr]

        # INSERT...SELECT：在源库执行 SELECT 抽样，改写为 INSERT...VALUES（在子集库模拟）
        if getattr(ins, "select_sql", None):
            sel = str(ins.select_sql)  # type: ignore[attr-defined]
            # 给 select 加 limit（若已有 LIMIT 则不追加）
            if " LIMIT " not in sel.upper():
                sel_limited = sel.rstrip(";") + f" LIMIT {int(max_rows)}"
            else:
                sel_limited = sel
            rows, sel_cols = fetch_rows_by_select(source_cfg, sel_limited)
            if not rows:
                return {
                    "success": False,
                    "previewable": False,
                    "level": "simple",
                    "rows": [],
                    "columns": [],
                    "row_count": 0,
                    "warning": "INSERT...SELECT 的 SELECT 未命中任何行，预览为空。",
                    "message": None,
                    "error": None,
                    "impact": {"action": "insert", "table": ins.table, "where": "", "limit": None},  # type: ignore[union-attr]
                    "diff": {"success": True, "before_row_count": 0, "after_row_count": 0, "diffs": []},
                }

            # 生成 INSERT...VALUES（按列映射）
            insert_cols = ins.columns if ins.has_columns else sel_cols  # type: ignore[union-attr]
            # 若未显式列且 SELECT 列数与表列不一致，则判复杂
            if not ins.has_columns and cols and len(insert_cols) != len(cols):
                return {
                    "success": False,
                    "previewable": False,
                    "level": "complex",
                    "rows": [],
                    "columns": [],
                    "row_count": 0,
                    "warning": None,
                    "message": "INSERT...SELECT 预览失败：未指定插入列且 SELECT 列数与目标表列数不一致。",
                    "error": "INSERT...SELECT 列映射不明确",
                }

            # 用参数化执行更安全：后续模拟时直接 executemany
            # 这里将 rows 和 insert_cols 附带给后续模拟执行逻辑
            # 通过在 sql_clean 上覆盖为一个标记，后面走专门插入
            sql_clean = "__INSERT_SELECT_SIM__"
            insert_select_payload = {"table": table, "columns": insert_cols, "rows": rows}
        else:
            insert_select_payload = None

    # 2) 是否走云端沙箱：新版看 sandbox 是否提供 base_url 或 tenant_id；旧版仍兼容
    want_sandbox = bool(sandbox_cfg) or bool(data_source.get("sandbox"))
    sandbox_ds = sandbox_cfg or {}

    # 3) 在子集库上执行一个只读 SELECT（SQLite 方言）
    impact_select_sqlite = adapter.to_sqlite(impact_select_src)
    dml_sqlite = adapter.to_sqlite(sql_clean) if sql_clean != "__INSERT_SELECT_SIM__" else "__INSERT_SELECT_SIM__"

    # 4) 字段级 diff（本地模拟执行）
    if impact:
        diff_ret = _simulate_dml_and_diff(
            subset_path=subset_path,
            dml_sqlite=dml_sqlite,
            impact_select_sqlite=impact_select_sqlite,
            pk="id",
            max_rows=max_rows,
        )
    else:
        # INSERT：用空子集库模拟执行
        if dml_sqlite == "__INSERT_SELECT_SIM__":
            diff_ret = _simulate_insert_rows_and_diff(
                subset_path=subset_path,
                table=table,
                columns=insert_select_payload["columns"],  # type: ignore[index]
                rows=insert_select_payload["rows"],  # type: ignore[index]
                impact_select_sqlite=impact_select_sqlite,
                pk="id",
                max_rows=max_rows,
            )
        else:
            diff_ret = _simulate_dml_and_diff(
                subset_path=subset_path,
                dml_sqlite=dml_sqlite,
                impact_select_sqlite=impact_select_sqlite,
                pk="id",
                max_rows=max_rows,
            )

    if want_sandbox:
        if not sandbox_ds.get("base_url") and not os.getenv("SANDBOX_REMOTE_URL"):
            return {
                "success": False,
                "previewable": False,
                "level": "complex",
                "rows": [],
                "columns": [],
                "row_count": 0,
                "warning": None,
                "message": "已请求走云端沙箱预览，但未提供 sandbox.base_url 且未配置 SANDBOX_REMOTE_URL。",
                "error": "缺少云端沙箱 base_url",
                "impact": {"action": impact.action, "table": impact.table, "where": impact.where, "limit": impact.limit},
            }

        # 云端：先上传子集库，再执行
        from sandbox.utils.cloud_sandbox_client import CloudSandboxHttpConfig, upload_sqlite_db_and_switch, execute_sql

        cfg = CloudSandboxHttpConfig.from_env()
        if sandbox_ds.get("base_url"):
            cfg.base_url = str(sandbox_ds.get("base_url")).rstrip("/")
        if sandbox_ds.get("token"):
            cfg.token = str(sandbox_ds.get("token"))
        if sandbox_ds.get("tenant_id"):
            cfg.tenant_id = str(sandbox_ds.get("tenant_id"))

        up = upload_sqlite_db_and_switch(cfg, db_path=subset_path)
        ex = execute_sql(cfg, impact_select_sqlite)
        rows = (ex.get("data") or [])[:max_rows]
        return {
            "success": ex.get("success", False),
            "previewable": ex.get("success", False),
            "level": "simple",
            "rows": rows,
            "columns": ex.get("columns") or [],
            "row_count": len(rows),
            "warning": "这是对 UPDATE/DELETE 将影响行的预览（只读）。未展示变更后的值，仅展示命中行（修改前）。",
            "message": None if ex.get("success") else ex.get("error"),
            "error": ex.get("error"),
            "impact": {"action": (impact.action if impact else "insert"), "table": (impact.table if impact else ins.table), "where": (impact.where if impact else ""), "limit": (impact.limit if impact else None)},
            "subset_db_uploaded": up,
            "diff": diff_ret if diff_ret.get("success") else None,
        }

    # 本地：直接用 subset sqlite 文件执行
    local = preview_select(
        sql=impact_select_sqlite,
        src_dialect="sqlite",
        data_source={"type": "sqlite", "path": subset_path},
        max_rows=max_rows,
        sample_rows=sample_rows,
    )
    if impact:
        local["warning"] = "这是对 UPDATE/DELETE 将影响行的预览（只读）。未展示变更后的值，仅展示命中行（修改前）。"
    else:
        local["warning"] = "这是对 INSERT 将插入行的预览（只读）。未展示写入主库，仅展示插入行的模拟结果。"
    local["impact"] = {"action": (impact.action if impact else "insert"), "table": (impact.table if impact else ins.table), "where": (impact.where if impact else ""), "limit": (impact.limit if impact else None)}
    local["diff"] = diff_ret if diff_ret.get("success") else None
    return local
