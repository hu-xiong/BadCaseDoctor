#!/usr/bin/env python
"""修复数据库缺失列的脚本"""
import sys
sys.path.insert(0, '.')

from app import db, app

def fix_missing_columns():
    """添加数据库表中缺失的列"""
    with app.app_context():
        # 获取数据库类型
        db_url = str(db.engine.url)
        print(f"数据库类型: {db_url}")
        
        if 'postgresql' in db_url or 'postgres' in db_url:
            # PostgreSQL
            def column_exists(table, column):
                result = db.engine.execute(db.text(f"""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = '{table}' AND column_name = '{column}'
                """))
                return result.fetchone() is not None
            
            def add_column(table, column, definition):
                if not column_exists(table, column):
                    db.engine.execute(db.text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
                    print(f"✓ 已添加 {table}.{column} 列")
                else:
                    print(f"✓ {table}.{column} 列已存在")
                    
        elif 'sqlite' in db_url:
            # SQLite - 使用 PRAGMA
            def column_exists(table, column):
                result = db.engine.execute(db.text(f"PRAGMA table_info({table})"))
                columns = [row[1] for row in result.fetchall()]
                return column in columns
            
            def add_column(table, column, definition):
                if not column_exists(table, column):
                    # SQLite 不支持直接 ADD COLUMN 用于某些情况，需要注意
                    db.engine.execute(db.text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
                    print(f"✓ 已添加 {table}.{column} 列")
                else:
                    print(f"✓ {table}.{column} 列已存在")
        else:
            print(f"未知的数据库类型: {db_url}")
            return
        
        # 检查并添加 plan.is_default 列
        add_column('plan', 'is_default', 'BOOLEAN DEFAULT 0')
        
        print("\n数据库列检查完成！")

if __name__ == '__main__':
    fix_missing_columns()
