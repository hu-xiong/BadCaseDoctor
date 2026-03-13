"""
方案2：子集 SQLite 构建器

输入：
- 源数据源配置（sqlite/mysql/oracle）
- 影响行查询（SELECT * FROM table WHERE ... LIMIT n）

输出：
- 一个只包含命中行的小 SQLite 文件路径

说明：
- 目前只做“单表子集”（通用且足够快）
- 对复杂 SQL 可返回提示“可能不准”
- Oracle 需安装: pip install oracledb
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from typing import Any, Dict, List, Tuple, Optional


def _to_sqlite_val(v: Any) -> Any:
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _create_table_from_rows(conn: sqlite3.Connection, table: str, rows: List[Dict[str, Any]]) -> List[str]:
    cols = list(rows[0].keys()) if rows else ["id"]
    if "id" in cols:
        col_defs = ", ".join([("\"id\" INTEGER") if c == "id" else f'\"{c}\" TEXT' for c in cols])
    else:
        col_defs = ", ".join([f'\"{c}\" TEXT' for c in cols])
    conn.execute(f'CREATE TABLE \"{table}\" ({col_defs})')
    return cols


def _fetch_mysql_rows(mysql_cfg: Dict[str, Any], select_sql: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    import pymysql

    conn = pymysql.connect(
        host=mysql_cfg.get("host", "127.0.0.1"),
        port=int(mysql_cfg.get("port", 3306)),
        user=mysql_cfg.get("user", ""),
        password=mysql_cfg.get("password", ""),
        database=mysql_cfg.get("database", ""),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    with conn.cursor() as cur:
        cur.execute(select_sql)
        rows = cur.fetchall() or []
    conn.close()
    cols = list(rows[0].keys()) if rows else []
    return rows, cols


def _fetch_sqlite_rows(sqlite_path: str, select_sql: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(select_sql)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows, cols


def _fetch_oracle_rows(ora_cfg: Dict[str, Any], select_sql: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    try:
        import oracledb
    except ImportError as e:
        raise ValueError("Oracle 源库需要安装 oracledb: pip install oracledb") from e

    dsn = (ora_cfg.get("dsn") or "").strip()
    if not dsn:
        host = ora_cfg.get("host", "127.0.0.1")
        port = int(ora_cfg.get("port", 1521))
        service = (ora_cfg.get("service_name") or ora_cfg.get("service") or "ORCL").strip()
        dsn = f"{host}:{port}/{service}"
    conn = oracledb.connect(
        user=ora_cfg.get("user", ""),
        password=ora_cfg.get("password", ""),
        dsn=dsn,
    )
    cur = conn.cursor()
    try:
        cur.execute(select_sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows_raw = cur.fetchall() or []
        rows = [dict(zip(cols, r)) for r in rows_raw]
        return rows, cols
    finally:
        cur.close()
        conn.close()


def fetch_rows_by_select(
    data_source: Dict[str, Any],
    select_sql: str,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    在源库上执行只读 SELECT 并返回 rows + columns。
    """
    ds_type = (data_source.get("type") or "sqlite").strip().lower()
    if ds_type == "mysql":
        return _fetch_mysql_rows(data_source, select_sql)
    if ds_type == "sqlite":
        path = data_source.get("path", "")
        if not path:
            raise ValueError("sqlite 需要 data_source.path")
        return _fetch_sqlite_rows(path, select_sql)
    if ds_type == "oracle":
        return _fetch_oracle_rows(data_source, select_sql)
    raise ValueError(f"暂不支持数据源类型: {ds_type}")


def build_subset_sqlite_file(
    data_source: Dict[str, Any],
    table: str,
    select_sql: str,
    out_path: str | None = None,
) -> str:
    """
    构建 SQLite 子集文件。

    Args:
        data_source: {"type": "mysql"/"sqlite", ...}
        table: 目标表名（用于在子集中建表）
        select_sql: 用于从源库抓取命中行的 SELECT
        out_path: 指定输出路径（可选）

    Returns:
        subset sqlite file path
    """
    ds_type = (data_source.get("type") or "sqlite").strip().lower()
    if out_path is None:
        out_path = os.path.join(tempfile.gettempdir(), f"subset_{table}_{abs(hash(select_sql))}.db")
    try:
        if os.path.exists(out_path):
            os.remove(out_path)
    except Exception:
        pass

    rows, _ = fetch_rows_by_select(data_source, select_sql)

    conn = sqlite3.connect(out_path)
    if rows:
        cols = _create_table_from_rows(conn, table, rows)
        placeholders = ",".join(["?"] * len(cols))
        col_list = ",".join([f'\"{c}\"' for c in cols])
        ins = f'INSERT INTO \"{table}\" ({col_list}) VALUES ({placeholders})'
        for r in rows:
            conn.execute(ins, [_to_sqlite_val(r.get(c)) for c in cols])
    else:
        conn.execute(f'CREATE TABLE \"{table}\" (id INTEGER)')
    conn.commit()
    conn.close()
    return out_path


def fetch_table_columns(
    data_source: Dict[str, Any],
    table: str,
) -> List[str]:
    """
    从源库获取表列名（用于 INSERT 子集建表）。
    """
    ds_type = (data_source.get("type") or "sqlite").strip().lower()
    if ds_type == "mysql":
        import pymysql
        conn = pymysql.connect(
            host=data_source.get("host", "127.0.0.1"),
            port=int(data_source.get("port", 3306)),
            user=data_source.get("user", ""),
            password=data_source.get("password", ""),
            database=data_source.get("database", ""),
            charset="utf8mb4",
        )
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM `{table}` LIMIT 0")
                cols = [d[0] for d in cur.description] if cur.description else []
                return cols
        finally:
            conn.close()
    if ds_type == "sqlite":
        path = data_source.get("path", "")
        if not path:
            raise ValueError("sqlite 需要 data_source.path")
        conn = sqlite3.connect(path)
        try:
            cur = conn.execute(f'SELECT * FROM "{table}" LIMIT 0')
            cols = [d[0] for d in cur.description] if cur.description else []
            return cols
        finally:
            conn.close()
    if ds_type == "oracle":
        try:
            import oracledb
        except ImportError as e:
            raise ValueError("Oracle 源库需要安装 oracledb: pip install oracledb") from e
        dsn = (data_source.get("dsn") or "").strip()
        if not dsn:
            host = data_source.get("host", "127.0.0.1")
            port = int(data_source.get("port", 1521))
            service = (data_source.get("service_name") or data_source.get("service") or "ORCL").strip()
            dsn = f"{host}:{port}/{service}"
        conn = oracledb.connect(
            user=data_source.get("user", ""),
            password=data_source.get("password", ""),
            dsn=dsn,
        )
        cur = conn.cursor()
        try:
            # Oracle 无 LIMIT，用 ROWNUM
            cur.execute(f'SELECT * FROM "{table}" WHERE ROWNUM < 1')
            cols = [d[0] for d in cur.description] if cur.description else []
            return cols
        finally:
            cur.close()
            conn.close()
    raise ValueError(f"暂不支持数据源类型: {ds_type}")


def create_empty_subset_sqlite(
    table: str,
    columns: List[str],
    out_path: Optional[str] = None,
) -> str:
    """
    创建仅包含 schema 的 SQLite 子集库（用于 INSERT 预览）。
    """
    if out_path is None:
        out_path = os.path.join(tempfile.gettempdir(), f"subset_empty_{table}.db")
    try:
        if os.path.exists(out_path):
            os.remove(out_path)
    except Exception:
        pass
    conn = sqlite3.connect(out_path)
    cols = columns[:] if columns else ["id"]
    if "id" in cols:
        col_defs = ", ".join([("\"id\" INTEGER PRIMARY KEY") if c == "id" else f'\"{c}\" TEXT' for c in cols])
    else:
        col_defs = ", ".join([f'\"{c}\" TEXT' for c in cols])
    conn.execute(f'CREATE TABLE "{table}" ({col_defs})')
    conn.commit()
    conn.close()
    return out_path

