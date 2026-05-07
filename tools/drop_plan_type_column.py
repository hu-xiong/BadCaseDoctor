"""
删除 plan.plan_type 列（SQLite 迁移脚本）。

SQLite 不支持直接 DROP COLUMN，本脚本通过“重建表”实现：
1) 读取 plan 表现有列
2) 新建 plan_new（不含 plan_type）
3) 复制数据
4) 删除旧表，重命名新表
5) 重建常用索引（跳过 idx_plan_type）

默认处理 instance/badcase_doctor.db；可通过参数指定路径：
  python tools/drop_plan_type_column.py instance/badcase_doctor.db
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def _table_columns(cur: sqlite3.Cursor, table: str) -> list[str]:
    cur.execute(f"PRAGMA table_info({table})")
    rows = cur.fetchall()
    return [r[1] for r in rows]  # name


def main() -> int:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("instance/badcase_doctor.db")
    if not db_path.exists():
        print(f"[ERR] db 文件不存在: {db_path}")
        return 2

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cols = _table_columns(cur, "plan")
        if not cols:
            print("[ERR] 未找到 plan 表")
            return 3
        if "plan_type" not in cols:
            print("[OK] plan 表已无 plan_type，无需迁移")
            return 0

        keep = [c for c in cols if c != "plan_type"]
        print("[INFO] plan 原列:", cols)
        print("[INFO] 保留列:", keep)

        # 关闭外键约束（重建表时避免引用失败），完成后恢复
        cur.execute("PRAGMA foreign_keys=OFF")
        conn.commit()

        # plan 表结构（与 app.py 中 Plan 模型一致，不含 plan_type）
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS plan_new (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name VARCHAR(200) NOT NULL,
              description TEXT,
              status VARCHAR(20) DEFAULT "active",
              priority VARCHAR(10) DEFAULT "medium",
              is_pinned BOOLEAN DEFAULT FALSE,
              is_default BOOLEAN DEFAULT FALSE,
              start_date DATE,
              end_date DATE,
              progress FLOAT DEFAULT 0.0,
              parent_id INT,
              project_id INT NOT NULL,
              creator_id INT NOT NULL,
              assignee_id INT,
              scope_notification BOOLEAN DEFAULT FALSE,
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
              updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cols_csv = ", ".join(keep)
        cur.execute(f"INSERT INTO plan_new ({cols_csv}) SELECT {cols_csv} FROM plan")

        cur.execute("DROP TABLE plan")
        cur.execute("ALTER TABLE plan_new RENAME TO plan")

        # 删除旧 idx_plan_type（若存在于 sqlite_master），并重建其它常用索引
        cur.execute("DROP INDEX IF EXISTS idx_plan_type")
        conn.commit()

        cur.execute("PRAGMA foreign_keys=ON")
        conn.commit()

        print("[OK] 迁移完成：已删除 plan.plan_type")
        return 0
    except Exception as e:
        conn.rollback()
        print("[ERR] 迁移失败:", e)
        return 1
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())

