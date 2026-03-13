"""
方案2：通用 DML（UPDATE/DELETE）预览支持

目标：
- 不执行写入 SQL
- 将 UPDATE/DELETE 转为只读 SELECT，用于抓取“将被影响的行”
- 后续可将命中行抽取成 SQLite 子集并上传云端沙箱执行预览

约束：
- 仅支持单表 UPDATE/DELETE（90% 场景）
- JOIN / 子查询 / 多语句 归为复杂，不做自动预览
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class DmlImpactQuery:
    action: str  # update|delete
    table: str
    where: str
    limit: Optional[int] = None

    def to_select_sql(self, columns: str = "*") -> str:
        sql = f"SELECT {columns} FROM {self.table}"
        if self.where:
            sql += f" WHERE {self.where}"
        if self.limit is not None:
            sql += f" LIMIT {int(self.limit)}"
        return sql


_RE_MULTI_STMT = re.compile(r";\\s*\\S", re.S)


def _strip_trailing_semicolon(sql: str) -> str:
    s = sql.strip()
    if s.endswith(";"):
        s = s[:-1].strip()
    return s


def parse_single_table_update_or_delete(sql: str) -> Optional[DmlImpactQuery]:
    """
    解析单表 UPDATE/DELETE。

    支持：
    - UPDATE t SET ... WHERE ... [LIMIT n]
    - DELETE FROM t WHERE ... [LIMIT n]
    """
    s = _strip_trailing_semicolon(sql)
    if not s:
        return None
    if _RE_MULTI_STMT.search(s):
        return None

    upper = s.upper()

    # UPDATE
    # 尽量宽松：table 允许 `t` / "t" / t
    m = re.match(r"(?is)^UPDATE\\s+([`\"\\w\\.]+)\\s+SET\\s+(.+)$", s)
    if m:
        table = m.group(1)
        rest = m.group(2).strip()

        # 拆 WHERE（不做完整 SQL 解析，适配 90%）
        where = ""
        limit = None
        where_m = re.search(r"(?is)\\bWHERE\\b\\s+(.+)$", rest)
        if where_m:
            where = where_m.group(1).strip()
            # 提取 LIMIT
            limit_m = re.search(r"(?is)\\bLIMIT\\b\\s+(\\d+)\\s*$", where)
            if limit_m:
                limit = int(limit_m.group(1))
                where = re.sub(r"(?is)\\bLIMIT\\b\\s+\\d+\\s*$", "", where).strip()
        else:
            # 没 WHERE：风险太大，不预览
            return None

        # 如果 where 里包含 JOIN/SELECT 等，认为复杂
        if re.search(r"(?is)\\bJOIN\\b|\\bSELECT\\b|\\bUNION\\b", where):
            return None

        return DmlImpactQuery(action="update", table=table, where=where, limit=limit)

    # DELETE
    m = re.match(r"(?is)^DELETE\\s+FROM\\s+([`\"\\w\\.]+)\\s+(.+)$", s)
    if m:
        table = m.group(1)
        rest = m.group(2).strip()

        where = ""
        limit = None
        where_m = re.search(r"(?is)^WHERE\\s+(.+)$", rest)
        if where_m:
            where = where_m.group(1).strip()
            limit_m = re.search(r"(?is)\\bLIMIT\\b\\s+(\\d+)\\s*$", where)
            if limit_m:
                limit = int(limit_m.group(1))
                where = re.sub(r"(?is)\\bLIMIT\\b\\s+\\d+\\s*$", "", where).strip()
        else:
            return None

        if re.search(r"(?is)\\bJOIN\\b|\\bSELECT\\b|\\bUNION\\b", where):
            return None

        return DmlImpactQuery(action="delete", table=table, where=where, limit=limit)

    return None

