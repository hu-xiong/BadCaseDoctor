import sqlite3

conn = sqlite3.connect('instance/badcase_doctor.db')
cursor = conn.cursor()
cursor.execute("DELETE FROM test_case WHERE title='测试多步骤'")
conn.commit()
print(f'删除了 {cursor.rowcount} 条记录')
conn.close()
