"""Clone test_case id=6 (创建测试用例7) to a new row with title 一个新增的测试用例. Local SQLite only."""
import sqlite3
from datetime import datetime

# 默认路径：仓库根目录下运行
import os

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db_path = os.path.join(_root, "instance", "badcase_doctor.db")


def main():
    c = sqlite3.connect(db_path)
    cur = c.cursor()
    new_title = "一个新增的测试用例"
    if cur.execute("SELECT id FROM test_case WHERE title=?", (new_title,)).fetchone():
        print("already exists, skip")
        return
    cur.execute("SELECT * FROM test_case WHERE id=6")
    row = cur.fetchone()
    if not row:
        print("source id=6 not found")
        return
    cols = [d[0] for d in cur.description]
    d = dict(zip(cols, row))
    del d["id"]
    d["title"] = new_title
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")
    d["created_at"] = now
    d["updated_at"] = now
    keys = list(d.keys())
    ph = ",".join(["?"] * len(keys))
    sql = "INSERT INTO test_case (%s) VALUES (%s)" % (",".join(keys), ph)
    cur.execute(sql, tuple(d.values()))
    c.commit()
    print("inserted id", cur.lastrowid)


if __name__ == "__main__":
    main()
