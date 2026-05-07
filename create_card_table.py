"""创建 Card 表并添加测试数据"""
import sqlite3

conn = sqlite3.connect('instance/badcase_doctor.db')
cursor = conn.cursor()

# 检查 card 表是否已存在
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='card'")
if cursor.fetchone():
    print('Card 表已存在')
else:
    print('创建 card 表...')
    cursor.execute("""
    CREATE TABLE card (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title VARCHAR(200) NOT NULL,
        type VARCHAR(20) DEFAULT 'badcase',
        priority VARCHAR(10) DEFAULT 'p3',
        assignee_id INT,
        project_id INT NOT NULL,
        creator_id INT NOT NULL,
        plan_id INT,
        description TEXT,
        source_type VARCHAR(20),
        source_id INT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        -- Bug 特定字段
        severity VARCHAR(20),
        steps_to_reproduce TEXT,
        expected_result TEXT,
        actual_result TEXT,
        bug_type VARCHAR(50),
        environment VARCHAR(100),
        browser VARCHAR(50),
        os VARCHAR(50),
        -- BadCase 特定字段
        case_category VARCHAR(100),
        base_problem TEXT,
        badcase_result TEXT,
        answer TEXT,
        correct_answer TEXT,
        problem_reason TEXT,
        solution TEXT,
        reproduction_steps TEXT,
        -- TestCase 特定字段
        case_type_test VARCHAR(50),
        test_type VARCHAR(20),
        preconditions TEXT,
        steps TEXT,
        remark TEXT,
        requirement_id INT,
        related_defects TEXT,
        baseline VARCHAR(100),
        estimated_time INT,
        actual_time INT,
        remaining_time INT,
        last_executed DATETIME,
        executed_by INT,
        execution_result VARCHAR(20),
        version VARCHAR(20)
    )
    """)
    conn.commit()
    print('Card 表创建成功')

# 为 bug 表添加 card_id 列（如果不存在）
cursor.execute("PRAGMA table_info(bug)")
bug_columns = [col[1] for col in cursor.fetchall()]
if 'card_id' not in bug_columns:
    cursor.execute("ALTER TABLE bug ADD COLUMN card_id INTEGER")
    conn.commit()
    print('Bug 表添加 card_id 列成功')
else:
    print('Bug 表已有 card_id 列')

# 插入测试卡片数据
print('\n插入测试卡片...')
cursor.execute("SELECT COUNT(*) FROM card")
count = cursor.fetchone()[0]
print(f'当前卡片数量: {count}')

if count == 0:
    # 插入一个 bug 类型的测试卡片
    cursor.execute("""
    INSERT INTO card (id, title, type, priority, project_id, creator_id, plan_id, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (2, '卡片测试', 'bug', 'p3', 1, 1, 1, '2026-04-22 01:00:00', '2026-04-22 01:00:00'))
    conn.commit()
    print('测试卡片"卡片测试" (id=2) 插入成功')

# 验证卡片数据
print('\n卡片数据:')
cursor.execute('SELECT id, title, type, project_id FROM card')
for row in cursor.fetchall():
    print(f'  ID: {row[0]}, 标题: {row[1]}, 类型: {row[2]}, 项目ID: {row[3]}')

# 验证 bug 表的 card_id
print('\nBug 数据的 card_id:')
cursor.execute('SELECT id, title, card_id, plan_id FROM bug')
for row in cursor.fetchall():
    print(f'  ID: {row[0]}, 标题: {row[1]}, card_id: {row[2]}, plan_id: {row[3]}')

conn.close()
print('\n完成!')
