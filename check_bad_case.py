import sqlite3

conn = sqlite3.connect('instance/badcase_doctor.db')
cursor = conn.cursor()

# 查看 bad_case 表结构
cursor.execute("PRAGMA table_info(bad_case)")
columns = cursor.fetchall()
print('bad_case 表结构:')
for col in columns:
    print(f'  {col[1]}: {col[2]}')

print()

# 查看 bad_case 表所有数据
cursor.execute('SELECT * FROM bad_case')
rows = cursor.fetchall()
print(f'bad_case 表数据 ({len(rows)} 条):')
for r in rows:
    print(f'  {r}')

conn.close()
