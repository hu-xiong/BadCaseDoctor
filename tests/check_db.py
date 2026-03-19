import sqlite3

conn = sqlite3.connect('instance/badcase_doctor.db')
cursor = conn.cursor()

# 查询 Bug 表
print('Bug 表所有记录:')
cursor.execute('SELECT id, title, expected_result FROM bug')
rows = cursor.fetchall()
print(f'共 {len(rows)} 条')
for r in rows:
    print(f'  ID={r[0]}, title={r[1]}, expected={r[2]}')
    
# 查询包含"登录"的记录
print('\n包含"登录"关键词的 Bug:')
cursor.execute("SELECT id, title, expected_result FROM bug WHERE title LIKE '%登录%' OR expected_result LIKE '%登录%'")
rows = cursor.fetchall()
print(f'找到 {len(rows)} 条')
for r in rows:
    print(f'  ID={r[0]}, title={r[1]}, expected={r[2]}')

conn.close()

