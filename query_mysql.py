"""查询 MySQL 数据库中的 bug 和 card 数据"""
import pymysql

# MySQL 连接配置
conn = pymysql.connect(
    host='117.72.33.38',
    port=33106,
    user='root',
    password='hx123456',
    database='bad_case',
    charset='utf8mb4'
)

cursor = conn.cursor()

# 1. 查看所有表
print("=" * 60)
print("数据库中的表:")
cursor.execute("SHOW TABLES")
tables = cursor.fetchall()
for t in tables:
    print(f"  - {t[0]}")

# 2. 检查 bug 表结构
print("\n" + "=" * 60)
print("bug 表结构:")
cursor.execute("DESCRIBE bug")
columns = cursor.fetchall()
for col in columns:
    print(f"  {col[0]}: {col[1]}")

# 3. 查询 bug 数据
print("\n" + "=" * 60)
print("bug 表数据:")
cursor.execute("SELECT id, title, card_id, plan_id, project_id FROM bug")
bugs = cursor.fetchall()
if bugs:
    for b in bugs:
        print(f"  ID: {b[0]}, 标题: {b[1]}, card_id: {b[2]}, plan_id: {b[3]}, project_id: {b[4]}")
else:
    print("  (空)")

# 4. 检查是否有 card 表
print("\n" + "=" * 60)
print("检查 card 相关表:")
cursor.execute("SHOW TABLES LIKE '%card%'")
card_tables = cursor.fetchall()
if card_tables:
    for t in card_tables:
        print(f"  找到表: {t[0]}")
        cursor.execute(f"DESCRIBE {t[0]}")
        cols = cursor.fetchall()
        for col in cols:
            print(f"    {col[0]}: {col[1]}")
        cursor.execute(f"SELECT * FROM {t[0]} LIMIT 10")
        rows = cursor.fetchall()
        for row in rows:
            print(f"    {row}")
else:
    print("  没有找到 card 相关表")

conn.close()
print("\n" + "=" * 60)
print("完成!")
