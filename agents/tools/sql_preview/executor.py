"""
预览执行器：在 SQLite 上执行转换后的 SQL，按复杂度返回不同策略结果

- SIMPLE：精确预览
- MEDIUM：带警告的预览（可能不准）
- COMPLEX：不执行，返回“无法预览”提示
"""

from typing import Any, Dict, List, Optional

from .dialect_adapter import SqlDialectAdapter
from .complexity import SqlComplexityAnalyzer, SqlComplexityLevel


class SqlPreviewExecutor:
    """SQL 预览执行器"""

    def __init__(
        self,
        adapter: SqlDialectAdapter,
        max_rows: int = 200,
    ):
        self.adapter = adapter
        self.max_rows = max_rows
        self.analyzer = SqlComplexityAnalyzer()

    def preview(
        self,
        sql: str,
        conn,  # sqlite3.Connection
    ) -> Dict[str, Any]:
        """
        执行预览

        Args:
            sql: 原始 SQL（源方言）
            conn: SQLite 连接（已包含 schema + 抽样数据）

        Returns:
            {
                "previewable": bool,
                "level": "simple" | "medium" | "complex",
                "rows": [...],
                "columns": [...],
                "row_count": int,
                "warning": str | None,
                "message": str | None,
            }
        """
        complexity = self.analyzer.analyze(sql)

        if complexity == SqlComplexityLevel.COMPLEX:
            return {
                "previewable": False,
                "level": "complex",
                "rows": [],
                "columns": [],
                "row_count": 0,
                "warning": None,
                "message": "SQL 过于复杂（可能包含存储过程/DDL/DML 等），无法自动预览，请人工确认。",
            }

        sqlite_sql = self.adapter.to_sqlite(sql)
        warning = None
        if complexity == SqlComplexityLevel.MEDIUM:
            warning = "该 SQL 较复杂（多表 JOIN/子查询/窗口函数），预览结果可能不完全准确，仅供参考。"

        try:
            cur = conn.cursor()
            cur.execute(sqlite_sql)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows_raw = cur.fetchall()
            rows: List[Dict[str, Any]] = []
            for r in rows_raw:
                if hasattr(r, "keys"):
                    rows.append(dict(r))
                else:
                    rows.append({cols[i]: r[i] for i in range(len(cols))})

            rows = rows[: self.max_rows]

            return {
                "previewable": True,
                "level": "simple" if complexity == SqlComplexityLevel.SIMPLE else "medium",
                "rows": rows,
                "columns": cols,
                "row_count": len(rows),
                "warning": warning,
                "message": None,
            }

        except Exception as e:
            return {
                "previewable": False,
                "level": complexity.name.lower(),
                "rows": [],
                "columns": [],
                "row_count": 0,
                "warning": None,
                "message": f"在 SQLite 中预览失败: {e}",
            }
