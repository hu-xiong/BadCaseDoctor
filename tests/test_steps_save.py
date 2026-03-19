import sqlite3
import json

# 连接数据库
conn = sqlite3.connect('instance/badcase_doctor.db')
cursor = conn.cursor()

# 测试插入多个步骤
test_steps = [
    {"step": "第一步操作", "expected": "第一步预期结果"},
    {"step": "第二步操作", "expected": "第二步预期结果"},
    {"step": "第三步操作", "expected": "第三步预期结果"}
]

# 测试 JSON 序列化
try:
    json_str = json.dumps(test_steps, ensure_ascii=False)
    print(f'JSON 序列化成功：{json_str}')
    
    # 测试插入数据库
    cursor.execute("""
        INSERT INTO test_case (title, project_id, steps, creator_id)
        VALUES (?, ?, ?, ?)
    """, ('测试多步骤', 1, json_str, 3))
    
    conn.commit()
    print(f'✅ 插入成功，ID={cursor.lastrowid}')
    
    # 验证读取
    cursor.execute("SELECT id, title, steps FROM test_case WHERE title='测试多步骤'")
    row = cursor.fetchone()
    print(f'\n读取结果:')
    print(f'  ID: {row[0]}')
    print(f'  Title: {row[1]}')
    print(f'  Steps: {row[2]}')
    
    # 测试 JSON 反序列化
    steps_from_db = json.loads(row[2])
    print(f'\n反序列化后的 steps:')
    for i, step in enumerate(steps_from_db):
        print(f'  步骤{i+1}: {step}')
    
except Exception as e:
    print(f'❌ 错误：{e}')
    import traceback
    traceback.print_exc()
finally:
    conn.close()

