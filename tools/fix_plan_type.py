#!/usr/bin/env python3
"""修复计划的 plan_type 字段"""

from sqlalchemy import create_engine, text
from config import Config

# 创建数据库连接
engine = create_engine(Config.DATABASE_URL)

with engine.connect() as conn:
    # 查询所有计划
    result = conn.execute(text("SELECT id, name, plan_type, status FROM plan"))
    plans = result.fetchall()
    
    print("=== 数据库中的所有计划 ===")
    for plan in plans:
        print(f"ID: {plan[0]}, 名称: {plan[1]}, plan_type: {plan[2]}, status: {plan[3]}")
    
    # 查找名为 'bug计划' 的计划
    result = conn.execute(text("SELECT id, name, plan_type FROM plan WHERE name = 'bug计划'"))
    bug_plan = result.fetchone()
    
    if bug_plan:
        print(f"\n找到bug计划: ID={bug_plan[0]}, plan_type={bug_plan[2]}")
        if bug_plan[2] != 'bug':
            print(f"❌ bug计划的plan_type错误! 应该是 bug，实际是 {bug_plan[2]}")
            print("正在修复...")
            conn.execute(text("UPDATE plan SET plan_type = 'bug' WHERE id = :id"), {"id": bug_plan[0]})
            conn.commit()
            print("✅ 已修复为 bug")
        else:
            print("✅ bug计划的plan_type正确")
    else:
        print("\n未找到名为 'bug计划' 的计划")
    
    # 也检查 '计划1'
    result = conn.execute(text("SELECT id, name, plan_type FROM plan WHERE name = '计划1'"))
    plan1 = result.fetchone()
    
    if plan1:
        print(f"\n找到计划1: ID={plan1[0]}, plan_type={plan1[2]}")
        if plan1[2] == 'badcase':
            print("ℹ️ 计划1是badcase类型，这是正确的")
    else:
        print("\n未找到名为 '计划1' 的计划")
