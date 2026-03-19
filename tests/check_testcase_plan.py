import sqlite3

conn = sqlite3.connect('instance/badcase_doctor.db')
cursor = conn.cursor()

# 查询测试用例分布
print('=== 测试用例分布 ===')
cursor.execute("""
    SELECT tc.id, tc.title, tc.plan_id, p.name as plan_name, tc.project_id
    FROM test_case tc
    LEFT JOIN plan p ON tc.plan_id = p.id
    WHERE tc.project_id = 1
    ORDER BY tc.plan_id, tc.id
""")
rows = cursor.fetchall()
for r in rows:
    print(f'  ID={r[0]}, title={r[1]}, plan_id={r[2]}, plan_name={r[3] or "未关联计划"}')

# 查询计划信息
print('\n=== 计划信息 ===')
cursor.execute("""
    SELECT id, name, plan_type
    FROM plan
    WHERE project_id = 1
    ORDER BY id
""")
rows = cursor.fetchall()
for r in rows:
    print(f'  ID={r[0]}, name={r[1]}, type={r[2]}')

conn.close()

