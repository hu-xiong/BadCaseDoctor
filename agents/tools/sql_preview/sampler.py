"""
数据源采样器：从 MySQL/Oracle 等拉取 schema + 抽样数据，构建 SQLite 内存库

支持：
- sqlite：直接使用本地文件路径
- mysql：连接 MySQL，拉取 schema + 每表最多 N 行
- 后续可扩展 oracle / postgres
"""

import re
import sqlite3
from typing import Any, Dict, List, Optional

# 每表抽样行数
DEFAULT_SAMPLE_ROWS = 500


def _build_sqlite_from_sqlite_path(path: str) -> sqlite3.Connection:
    """从 SQLite 文件构建内存连接（复制）"""
    src = sqlite3.connect(path)
    dest = sqlite3.connect(":memory:")
    src.backup(dest)
    src.close()
    return dest


def _build_sqlite_from_mysql(
    host: str,
    port: int = 3306,
    user: str = "",
    password: str = "",
    database: str = "",
    sample_rows: int = DEFAULT_SAMPLE_ROWS,
) -> sqlite3.Connection:
    """从 MySQL 拉取 schema + 抽样数据，构建 SQLite 内存库"""
    try:
        import pymysql
    except ImportError:
        raise RuntimeError("MySQL 采样需要 pymysql，请安装: pip install pymysql")

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )

    sqlite_conn = sqlite3.connect(":memory:")
    sqlite_conn.row_factory = sqlite3.Row
    cur = sqlite_conn.cursor()

    with conn.cursor() as mc:
        mc.execute("SHOW TABLES")
        tables = [list(r.values())[0] for r in mc.fetchall()]

        for tbl in tables:
            # 使用 DESCRIBE 构建 SQLite 兼容表（比 SHOW CREATE TABLE 更可靠）
            mc.execute(f"DESCRIBE `{tbl}`")
            cols_info = mc.fetchall()
            ddl_sqlite = _mysql_cols_to_sqlite_create(tbl, cols_info)
            try:
                cur.execute(ddl_sqlite)
            except Exception:
                cur.execute(f'CREATE TABLE "{tbl}" (id INTEGER PRIMARY KEY)')

            # 抽样数据
            mc.execute(f"SELECT * FROM `{tbl}` LIMIT {sample_rows}")
            rows = mc.fetchall()
            if not rows:
                continue

            cols = list(rows[0].keys())
            placeholders = ",".join(["?"] * len(cols))
            col_list = ",".join(f'"{c}"' for c in cols)

            for r in rows:
                vals = [_to_sqlite_val(r[c]) for c in cols]
                try:
                    cur.execute(
                        f'INSERT OR IGNORE INTO "{tbl}" ({col_list}) VALUES ({placeholders})',
                        vals,
                    )
                except Exception:
                    pass

    conn.close()
    sqlite_conn.commit()
    return sqlite_conn


def _mysql_type_to_sqlite(mysql_type: str) -> str:
    """MySQL 类型 -> SQLite 类型"""
    t = (mysql_type or "").upper()
    if re.match(r"INT|BIGINT|TINYINT|SMALLINT|MEDIUMINT", t):
        return "INTEGER"
    if re.match(r"FLOAT|DOUBLE|DECIMAL|NUMERIC", t):
        return "REAL"
    return "TEXT"


def _mysql_cols_to_sqlite_create(table_name: str, cols_info: List[Dict[str, Any]]) -> str:
    """根据 MySQL DESCRIBE 结果构建 SQLite CREATE TABLE"""
    parts = []
    pk_cols = []
    for c in cols_info:
        col_name = (c.get("Field") or c.get("field", "")).replace('"', '""')
        col_type = c.get("Type") or c.get("type", "TEXT")
        key = (c.get("Key") or c.get("key", "")).upper()
        null = (c.get("Null") or c.get("null", "YES")).upper()
        sqlite_type = _mysql_type_to_sqlite(col_type)
        part = f'"{col_name}" {sqlite_type}'
        if "PRI" in key:
            pk_cols.append(col_name)
        if "NO" in null and "PRI" not in key:
            part += " NOT NULL"
        parts.append(part)
    if pk_cols:
        parts.append("PRIMARY KEY (" + ", ".join(f'"{c}"' for c in pk_cols) + ")")
    return f'CREATE TABLE "{table_name.replace(chr(34), "")}" ({", ".join(parts)})'


def _to_sqlite_val(v: Any) -> Any:
    """将 Python 值转为 SQLite 可存储类型"""
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


class DataSourceSampler:
    """数据源采样器"""

    def __init__(self, sample_rows: int = DEFAULT_SAMPLE_ROWS):
        self.sample_rows = sample_rows

    def build_sqlite(
        self,
        db_type: str,
        config: Dict[str, Any],
    ) -> sqlite3.Connection:
        """
        根据数据源类型和配置，构建 SQLite 内存连接

        Args:
            db_type: sqlite | mysql | (后续 oracle, postgres)
            config: 连接配置
                - sqlite: {"path": "/path/to/db.sqlite"}
                - mysql: {"host": "...", "port": 3306, "user": "...", "password": "...", "database": "..."}

        Returns:
            sqlite3.Connection (内存库)
        """
        db_type = (db_type or "sqlite").strip().lower()

        if db_type == "sqlite":
            path = config.get("path", "")
            if not path:
                raise ValueError("sqlite 需要 config.path")
            return _build_sqlite_from_sqlite_path(path)

        if db_type == "mysql":
            return _build_sqlite_from_mysql(
                host=config.get("host", "127.0.0.1"),
                port=int(config.get("port", 3306)),
                user=config.get("user", ""),
                password=config.get("password", ""),
                database=config.get("database", ""),
                sample_rows=int(config.get("sample_rows", self.sample_rows)),
            )

        raise ValueError(f"暂不支持数据源类型: {db_type}")
