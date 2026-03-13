"""
SQL 方言转换器：将 MySQL / Oracle 等方言的 SQL 转为 SQLite 可执行子集

支持：
- MySQL: 反引号、LIMIT、部分函数映射
- Oracle: ROWNUM、NVL、日期函数简化
- 其余方言可按需扩展
"""

import re
from typing import Optional

SUPPORTED_DIALECTS = ("mysql", "oracle", "postgres", "sqlite")


def _normalize(sql: str) -> str:
    """统一大小写、去掉首尾空白、合并多余空白"""
    sql = sql.strip().rstrip(";")
    sql = re.sub(r"\s+", " ", sql)
    return sql


def _mysql_to_sqlite(sql: str) -> str:
    """MySQL -> SQLite 转换"""
    s = sql

    # 1. 反引号 -> 普通标识符
    s = s.replace("`", "")

    # 2. 函数映射（不区分大小写）
    # IFNULL(a,b) -> COALESCE(a,b)
    s = re.sub(r"\bIFNULL\s*\(([^,]+),([^)]+)\)", r"COALESCE(\1,\2)", s, flags=re.I)
    # DATE_FORMAT 等 -> 简单占位，SQLite 用 strftime
    s = re.sub(r"DATE_FORMAT\s*\(([^,]+),([^)]+)\)", r"strftime('%Y-%m-%d', \1)", s, flags=re.I)
    # NOW() -> datetime('now')
    s = re.sub(r"\bNOW\s*\(\s*\)", "datetime('now')", s, flags=re.I)
    # CURDATE() -> date('now')
    s = re.sub(r"\bCURDATE\s*\(\s*\)", "date('now')", s, flags=re.I)
    # CONCAT(a,b,c) -> a || b || c
    s = re.sub(r"CONCAT\s*\(([^)]+)\)", lambda m: " || ".join(x.strip() for x in m.group(1).split(",")), s, flags=re.I)

    # 3. LIMIT n OFFSET m 已是 SQLite 支持
    # MySQL LIMIT m, n -> LIMIT n OFFSET m
    match = re.search(r"\bLIMIT\s+(\d+)\s*,\s*(\d+)", s, re.I)
    if match:
        s = re.sub(r"\bLIMIT\s+\d+\s*,\s*\d+", f"LIMIT {match.group(2)} OFFSET {match.group(1)}", s, flags=re.I)

    return s


def _oracle_to_sqlite(sql: str) -> str:
    """Oracle -> SQLite 转换（简化版）"""
    s = sql

    # 1. 双引号标识符保留或去掉（SQLite 支持双引号）
    # s = s.replace('"', '')

    # 2. NVL(a,b) -> COALESCE(a,b)
    s = re.sub(r"\bNVL\s*\(([^,]+),([^)]+)\)", r"COALESCE(\1,\2)", s, flags=re.I)

    # 3. ROWNUM 处理：WHERE ROWNUM <= n -> LIMIT n（简化，只处理简单情况）
    rownum_match = re.search(r"\bROWNUM\s*<=\s*(\d+)", s, re.I)
    if rownum_match:
        n = rownum_match.group(1)
        s = re.sub(r"\bAND\s+ROWNUM\s*<=\s*\d+", "", s, flags=re.I)
        s = re.sub(r"\bROWNUM\s*<=\s*\d+\s+AND\s+", "", s, flags=re.I)
        s = re.sub(r"\bWHERE\s+ROWNUM\s*<=\s*\d+", "", s, flags=re.I)
        if "LIMIT" not in s.upper():
            s = s.rstrip() + f" LIMIT {n}"

    # 4. TO_CHAR / TO_DATE 简化（仅保留基础形式）
    s = re.sub(r"TO_CHAR\s*\(([^,)]+)(?:,[^)]+)?\)", r"\1", s, flags=re.I)
    s = re.sub(r"TO_DATE\s*\(([^)]+)\)", r"\1", s, flags=re.I)

    # 5. 双竖线字符串连接 Oracle 已有
    return s


def _postgres_to_sqlite(sql: str) -> str:
    """PostgreSQL -> SQLite 转换（简化版）"""
    s = sql

    # 1. 双引号标识符 SQLite 支持
    # 2. COALESCE 已是 SQLite 函数
    # 3. || 连接已是 SQLite 支持
    # 4. LIMIT / OFFSET 已是 SQLite 支持
    # 5. 去掉 PostgreSQL 特有函数或做简单替换
    s = re.sub(r"\bCOALESCE\b", "COALESCE", s, flags=re.I)

    return s


class SqlDialectAdapter:
    """SQL 方言转换器：源方言 -> SQLite"""

    def __init__(self, src_dialect: str, target: str = "sqlite"):
        self.src = src_dialect.strip().lower()
        self.target = target.strip().lower()
        if self.src not in SUPPORTED_DIALECTS:
            raise ValueError(f"不支持方言 {src_dialect}，支持: {SUPPORTED_DIALECTS}")

    def normalize(self, sql: str) -> str:
        """规范化：统一空白、去末尾分号"""
        return _normalize(sql)

    def to_sqlite(self, sql: str) -> str:
        """转换为 SQLite 可执行子集"""
        sql = self.normalize(sql)

        if self.src == "sqlite":
            return sql
        if self.src == "mysql":
            return _mysql_to_sqlite(sql)
        if self.src == "oracle":
            return _oracle_to_sqlite(sql)
        if self.src == "postgres":
            return _postgres_to_sqlite(sql)

        return sql
