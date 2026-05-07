"""为 bug 表添加 card_id 列"""
import sqlite3

conn = sqlite3.connect('instance/badcase_doctor.db')
cursor = conn.cursor()

# 检查 card_id 列是否已存在
cursor.execute("PRAGMA table_info(bug)")
columns = [col[1] for col in cursor.fetchall()]
print('Bug 表当前列:', columns)

if 'card_id' not in columns:
    print('添加 card_id 列到 bug 表...')
    cursor.execute("ALTER TABLE bug ADD COLUMN card_id INTEGER")
    conn.commit()
    print('[OK] card_id 列添加成功')
else:
    print('card_id 列已存在')

# 验证
cursor.execute("PRAGMA table_info(bug)")
columns = [col[1] for col in cursor.fetchall()]
print('Bug 表更新后列:', columns)

conn.close()
print('\n完成!')
