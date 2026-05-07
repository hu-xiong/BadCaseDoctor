import sqlite3

conn = sqlite3.connect('instance/badcase_doctor.db')
cursor = conn.cursor()

# 查找所有包含 card 的表
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%card%'")
tables = cursor.fetchall()
print('包含 card 的表:', [t[0] for t in tables])

# 查看每个 card 相关表的数据
for table_name in ['card', 'Card', 'cards', 'Cards', 'bad_case', 'badcase']:
    try:
        cursor.execute(f"SELECT id, title, type FROM {table_name} LIMIT 10")
        rows = cursor.fetchall()
        if rows:
            print(f'\n{table_name} 表数据:')
            for r in rows:
                print(f'  ID: {r[0]}, 标题: {r[1]}, 类型: {r[2] if len(r) > 2 else "N/A"}')
    except Exception as e:
        pass

conn.close()
