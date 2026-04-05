#!/usr/bin/env python3
"""
将本地 SQLite（默认 instance/badcase_doctor.db）的表与数据同步到 DATABASE_URL 指向的 MySQL。

- 结构：在 MySQL 上对当前 app 模型执行 create_all()（仅创建缺失表，不删不改已有表结构）。
- 数据：按依赖顺序逐表 INSERT IGNORE，主键已存在则跳过，不覆盖生产已有行。

用法（在项目根目录）:
  python scripts/migrate_sqlite_to_mysql.py              # 建表 + 导数据
  python scripts/migrate_sqlite_to_mysql.py --schema-only
  python scripts/migrate_sqlite_to_mysql.py --data-only --sqlite instance/badcase_doctor.db

依赖: .env 中配置 DATABASE_URL（mysql+pymysql://...）
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.chdir(ROOT)


def main() -> None:
    parser = argparse.ArgumentParser(description="SQLite -> MySQL 对齐表结构并迁移数据")
    parser.add_argument(
        "--sqlite",
        default=os.path.join(ROOT, "instance", "badcase_doctor.db"),
        help="源 SQLite 文件路径",
    )
    parser.add_argument("--schema-only", action="store_true", help="仅在 MySQL 上 create_all，不拷数据")
    parser.add_argument("--data-only", action="store_true", help="跳过 create_all，只拷数据")
    args = parser.parse_args()

    if not os.path.isfile(args.sqlite):
        print(f"[错误] 找不到 SQLite 文件: {args.sqlite}")
        sys.exit(1)

    from dotenv import load_dotenv

    load_dotenv(os.path.join(ROOT, ".env"))

    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.engine import Engine

    from app import app, db

    # 与 Flask 一致的 MySQL（或 .env 中的 URI）
    with app.app_context():
        mysql_uri = app.config["SQLALCHEMY_DATABASE_URI"]
        if not args.data_only:
            print("[schema] db.create_all() ->", str(mysql_uri).split("@")[-1] if "@" in str(mysql_uri) else mysql_uri)
            db.create_all()
            db.session.commit()
            print("[schema] 完成")

        if args.schema_only:
            return

        sqlite_uri = f"sqlite:///{os.path.abspath(args.sqlite)}"
        src: Engine = create_engine(sqlite_uri, future=True)
        dst: Engine = db.engine

        # 外键大致顺序（子表在后）。plan 自引用在 FK_CHECKS=0 下可批量插入。
        TABLE_ORDER = [
            "user",
            "user_credits",
            "payment_history",
            "project",
            "project_permission",
            "team",
            "team_member",
            "plan",
            "bad_case",
            "bug",
            "test_case",
            "comment",
            "bug_comment",
            "proposal",
            "proposal_snapshot",
            "chat_session",
            "chat_message",
            "diff_review_state",
            "prompt_template",
            "agent_tasks",
        ]

        si = inspect(src)
        di = inspect(dst)
        src_tables = set(si.get_table_names())
        dst_tables = set(di.get_table_names())

        def copy_table(table: str) -> tuple[int, int]:
            if table not in src_tables:
                return 0, 0
            if table not in dst_tables:
                print(f"[跳过] MySQL 无表 {table}（请先做 schema）")
                return 0, 0
            scols = [c["name"] for c in si.get_columns(table)]
            dcolset = {c["name"] for c in di.get_columns(table)}
            cols = [c for c in scols if c in dcolset]
            if not cols:
                return 0, 0
            col_sql = ", ".join(f"`{c}`" for c in cols)
            placeholders = ", ".join(["%s"] * len(cols))
            # MySQL INSERT IGNORE：主键/唯一冲突则跳过
            ins_sql = f"INSERT IGNORE INTO `{table}` ({col_sql}) VALUES ({placeholders})"
            sel_cols = ", ".join(f"`{c}`" for c in cols)
            select_sql = f"SELECT {sel_cols} FROM `{table}`"

            inserted = 0
            with src.connect() as sconn:
                rows = sconn.execute(text(select_sql)).fetchall()

            raw = dst.raw_connection()
            try:
                cur = raw.cursor()
                try:
                    cur.execute("SET SESSION foreign_key_checks=0")
                    batch = []
                    for row in rows:
                        batch.append(tuple(row))
                        if len(batch) >= 500:
                            cur.executemany(ins_sql, batch)
                            inserted += cur.rowcount
                            batch.clear()
                    if batch:
                        cur.executemany(ins_sql, batch)
                        inserted += cur.rowcount
                    cur.execute("SET SESSION foreign_key_checks=1")
                    raw.commit()
                except Exception:
                    raw.rollback()
                    raise
            finally:
                raw.close()

            return len(rows), inserted

        print("[data] 源 SQLite:", os.path.abspath(args.sqlite))
        total_rows = 0
        total_ins = 0
        for tn in TABLE_ORDER:
            n, ins = copy_table(tn)
            if n:
                print(f"  {tn}: 读取 {n} 行, IGNORE 插入 {ins} 行（其余为已存在主键）")
            total_rows += n
            total_ins += ins
        print(f"[data] 结束: 共读取 {total_rows} 行, 新插入约 {total_ins} 行（INSERT IGNORE 累计 rowcount）")


if __name__ == "__main__":
    main()
