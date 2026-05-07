import sqlite3

conn = sqlite3.connect('instance/badcase_doctor.db')
cursor = conn.cursor()

# 查看 bug 表结构
cursor.execute("PRAGMA table_info(bug)")
columns = cursor.fetchall()
print('Bug表结构:')
for col in columns:
    print(f'  {col[1]}: {col[2]}')

print()

# 查看 bug 表数据
cursor.execute('SELECT * FROM bug')
rows = cursor.fetchall()
print(f'Bug表数据 ({len(rows)} 条):')
for r in rows:
    print(f'  {r}')

print()

# 查看 bad_case 表结构
cursor.execute("PRAGMA table_info(bad_case)")
columns = cursor.fetchall()
print('Bad_case表结构:')
for col in columns:
    print(f'  {col[1]}: {col[2]}')

print()

# 查看 test_case 表结构
cursor.execute("PRAGMA table_info(test_case)")
columns = cursor.fetchall()
print('Test_case表结构:')
for col in columns:
    print(f'  {col[1]}: {col[2]}')

conn.close()
