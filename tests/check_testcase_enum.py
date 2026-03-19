import sqlite3

conn = sqlite3.connect('instance/badcase_doctor.db')
cursor = conn.cursor()

# 获取所有表
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print('数据库表列表:')
for t in tables:
    print(f'  {t[0]}')
    
# 检查 test_case 表
cursor.execute("SELECT COUNT(*) FROM test_case")
print(f'\ntest_case 表总数：{cursor.fetchone()[0]}')

# 检查 execution_result 字段
cursor.execute("SELECT execution_result, COUNT(*) FROM test_case GROUP BY execution_result")
rows = cursor.fetchall()
print('\ntest_case 表 execution_result 值统计:')
for r in rows:
    print(f'  {repr(r[0])}: {r[1]} 条')

# 查找非法值
cursor.execute("""
    SELECT id, title, execution_result 
    FROM test_case 
    WHERE execution_result IS NULL 
       OR execution_result = '' 
       OR execution_result NOT IN ('pass', 'fail', 'blocked', 'skip')
""")
rows = cursor.fetchall()
if rows:
    print(f'\n找到 {len(rows)} 条非法记录:')
    for r in rows:
        print(f'  ID={r[0]}, title={r[1]}, execution_result={repr(r[2])}')
else:
    print('\n没有发现非法记录')

conn.close()

