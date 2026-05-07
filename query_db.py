import sqlite3

conn = sqlite3.connect('instance/badcase_doctor.db')
cursor = conn.cursor()

# 查看所有表
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print('数据库中的表:')
for t in tables:
    print(f'  - {t[0]}')

print()

# 查看 bug 相关表
for table_name in ['bug', 'Bug', 'Bugs', 'badcase', 'bad_case', 'card', 'Card']:
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f'{table_name} 表有 {count} 条记录')
    except:
        pass

print()

# 查询 bug 表（如果存在）
try:
    cursor.execute('SELECT id, title, card_id, plan_id, project_id FROM bug')
    rows = cursor.fetchall()
    print('Bug表数据:')
    if rows:
        for r in rows:
            print(f'  ID: {r[0]}, 标题: {r[1]}, card_id: {r[2]}, plan_id: {r[3]}, project_id: {r[4]}')
    else:
        print('  (空)')
except Exception as e:
    print(f'查询 bug 表失败: {e}')

print()

# 查询 card 表（如果存在）
try:
    cursor.execute('SELECT id, title, type, plan_id, project_id FROM card')
    rows = cursor.fetchall()
    print('Card表数据:')
    if rows:
        for r in rows:
            print(f'  ID: {r[0]}, 标题: {r[1]}, 类型: {r[2]}, plan_id: {r[3]}, project_id: {r[4]}')
    else:
        print('  (空)')
except Exception as e:
    print(f'查询 card 表失败: {e}')

conn.close()
