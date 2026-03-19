import sqlite3

conn = sqlite3.connect('instance/badcase_doctor.db')
cursor = conn.cursor()

# 将所有空字符串和 NULL 设置为 NULL（允许为空）
cursor.execute("""
    UPDATE test_case 
    SET execution_result = NULL 
    WHERE execution_result = '' OR execution_result IS NULL
""")
updated = cursor.rowcount
print(f'修复了 {updated} 条记录')

# 验证修复结果
cursor.execute("SELECT execution_result, COUNT(*) FROM test_case GROUP BY execution_result")
rows = cursor.fetchall()
print('\n修复后 execution_result 值统计:')
for r in rows:
    print(f'  {repr(r[0])}: {r[1]} 条')

conn.commit()
conn.close()
print('\n✅ 数据库修复完成')

