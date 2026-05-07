import urllib.parse as up

import pymysql

from config import Config


def main() -> None:
    uri = Config.SQLALCHEMY_DATABASE_URI
    uri = uri.replace("mysql+pymysql://", "mysql://", 1)
    p = up.urlparse(uri)

    conn = pymysql.connect(
        host=p.hostname,
        port=p.port or 3306,
        user=up.unquote(p.username or ""),
        password=up.unquote(p.password or ""),
        database=(p.path or "/")[1:],
        connect_timeout=10,
        read_timeout=10,
        write_timeout=10,
        charset="utf8mb4",
    )
    cur = conn.cursor()

    cur.execute("SELECT DATABASE()")
    print("DB =", cur.fetchone()[0])

    cur.execute("SHOW TABLES")
    tabs = [r[0] for r in cur.fetchall()]
    print("tables =", len(tabs))

    for name in [
        "project",
        "plan",
        "card",
        "bad_case",
        "badcase",
        "bug",
        "test_case",
        "testcase",
        "cards",
    ]:
        if name not in tabs:
            continue
        try:
            cur.execute(f"SELECT COUNT(*) FROM `{name}`")
            print(f"{name} count =", cur.fetchone()[0])
        except Exception as e:
            print(f"{name} count_err =", repr(e))

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()

