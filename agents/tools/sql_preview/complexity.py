"""
SQL 复杂度检测器：将 SQL 分为 SIMPLE / MEDIUM / COMPLEX 三档

- SIMPLE (90%)：单表、无子查询、无窗口函数 → 精确预览
- MEDIUM (9%)：多表 JOIN、子查询、窗口函数 → 带警告预览
- COMPLEX (1%)：存储过程、触发器、DDL、DML → 无法预览，提示人工确认
"""

import enum
import re


class SqlComplexityLevel(enum.Enum):
    """SQL 复杂度等级"""
    SIMPLE = 0   # 90%：单表、简单条件，可精确预览
    MEDIUM = 1   # 9%：JOIN/子查询/窗口，预览可能不准
    COMPLEX = 2  # 1%：存储过程/DDL/DML 等，无法预览


class SqlComplexityAnalyzer:
    """SQL 复杂度分析器"""

    # 立即判为 COMPLEX 的关键字（不区分大小写）
    _COMPLEX_KEYWORDS = (
        "CREATE ", "ALTER ", "DROP ", "TRUNCATE ", "MERGE ",
        " PROCEDURE ", " FUNCTION ", " TRIGGER ", " EXEC ",
        " INSERT ", " UPDATE ", " DELETE ",
        " GRANT ", " REVOKE ", " COMMIT ", " ROLLBACK ",
    )

    def analyze(self, sql: str) -> SqlComplexityLevel:
        """
        分析 SQL 复杂度

        Args:
            sql: 原始 SQL 字符串

        Returns:
            SqlComplexityLevel
        """
        s = sql.strip()
        if not s:
            return SqlComplexityLevel.COMPLEX

        upper = s.upper()

        # 1) 立即判为 COMPLEX（1%）
        for kw in self._COMPLEX_KEYWORDS:
            if kw.strip() + " " in upper or upper.strip().startswith(kw.strip()):
                return SqlComplexityLevel.COMPLEX

        # 仅处理 SELECT（预览只支持只读）
        if not upper.strip().startswith("SELECT"):
            return SqlComplexityLevel.COMPLEX

        # 2) 统计 JOIN / 子查询 / 窗口函数
        join_count = upper.count(" JOIN ")
        has_window = " OVER(" in upper
        # 简单子查询检测：SELECT 出现多次（不含注释）
        clean_sql = re.sub(r"--[^\n]*", "", s)
        clean_sql = re.sub(r"/\*.*?\*/", "", clean_sql, flags=re.DOTALL)
        select_count = len(re.findall(r"\bSELECT\b", clean_sql, re.I))

        has_subquery = select_count > 1
        has_union = " UNION " in upper

        # 3) 判 MEDIUM（9%）
        if join_count >= 1 or has_window or has_subquery or has_union:
            return SqlComplexityLevel.MEDIUM

        return SqlComplexityLevel.SIMPLE
