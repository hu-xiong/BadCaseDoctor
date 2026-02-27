"""
统一数据库中的状态值
- close -> closed
- reopen -> reopened
"""
import sqlite3

db_path = 'badcase_doctor.db'

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # 检查表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"数据库中的表: {tables}\n")
    
    # 统一 bad_case 表状态
    if 'bad_case' in tables:
        cursor.execute("UPDATE bad_case SET status = 'closed' WHERE status = 'close'")
        affected_badcases = cursor.rowcount
        print(f"bad_case 表：{affected_badcases} 条记录从 'close' 更新为 'closed'")
        
        cursor.execute("UPDATE bad_case SET status = 'reopened' WHERE status = 'reopen'")
        affected_badcases_reopen = cursor.rowcount
        print(f"bad_case 表：{affected_badcases_reopen} 条记录从 'reopen' 更新为 'reopened'")
    
    # 统一 bug 表状态（如果存在）
    if 'bug' in tables:
        cursor.execute("UPDATE bug SET status = 'closed' WHERE status = 'close'")
        affected_bugs = cursor.rowcount
        print(f"bug 表：{affected_bugs} 条记录从 'close' 更新为 'closed'")
        
        cursor.execute("UPDATE bug SET status = 'reopened' WHERE status = 'reopen'")
        affected_bugs_reopen = cursor.rowcount
        print(f"bug 表：{affected_bugs_reopen} 条记录从 'reopen' 更新为 'reopened'")
    
    # 提交更改
    conn.commit()
    print("\n✅ 状态值统一完成！")
    
except Exception as e:
    conn.rollback()
    print(f"\n❌ 错误：{e}")
    
finally:
    conn.close()
