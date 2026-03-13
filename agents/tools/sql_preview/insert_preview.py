"""
方案2：INSERT 预览支持（简化版）

支持：
- INSERT INTO t (a,b,...) VALUES (...),(...)
- INSERT INTO t VALUES (...),(...)

不支持：
- INSERT INTO ... SELECT ...
- ON DUPLICATE KEY / RETURNING 等扩展（判复杂）
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class InsertSpec:
    table: str
    has_columns: bool
    columns: List[str]
    select_sql: Optional[str] = None  # 若为 INSERT...SELECT，则为 SELECT 语句


_RE_MULTI_STMT = re.compile(r";\s*\S", re.S)


def parse_single_table_insert(sql: str) -> Optional[InsertSpec]:
    s = sql.strip().rstrip(";").strip()
    if not s:
        return None
    if _RE_MULTI_STMT.search(s):
        return None
    upper = s.upper()
    if not upper.startswith("INSERT"):
        return None
    # INSERT ... SELECT（近似预览：会执行 SELECT 抽样，再模拟插入）
    if re.search(r"(?is)\bINSERT\b.*\bSELECT\b", s):
        # INSERT INTO t (a,b) SELECT ...
        m = re.match(r"(?is)^INSERT\s+INTO\s+([`\"\w\.]+)\s*\(([^)]+)\)\s*(SELECT.+)$", s)
        if m:
            table = m.group(1)
            cols = [c.strip().strip("`\"") for c in m.group(2).split(",") if c.strip()]
            sel = m.group(3).strip()
            return InsertSpec(table=table, has_columns=True, columns=cols, select_sql=sel)
        # INSERT INTO t SELECT ...
        m = re.match(r"(?is)^INSERT\s+INTO\s+([`\"\w\.]+)\s*(SELECT.+)$", s)
        if m:
            table = m.group(1)
            sel = m.group(2).strip()
            return InsertSpec(table=table, has_columns=False, columns=[], select_sql=sel)
        return None
    if " ON DUPLICATE KEY " in upper or " RETURNING " in upper:
        return None

    # INSERT INTO t (a,b) VALUES ...
    m = re.match(r"(?is)^INSERT\s+INTO\s+([`\"\w\.]+)\s*\(([^)]+)\)\s*VALUES\s*\(", s)
    if m:
        table = m.group(1)
        cols = [c.strip().strip("`\"") for c in m.group(2).split(",") if c.strip()]
        return InsertSpec(table=table, has_columns=True, columns=cols)

    # INSERT INTO t VALUES ...
    m = re.match(r"(?is)^INSERT\s+INTO\s+([`\"\w\.]+)\s*VALUES\s*\(", s)
    if m:
        table = m.group(1)
        return InsertSpec(table=table, has_columns=False, columns=[])

    return None

