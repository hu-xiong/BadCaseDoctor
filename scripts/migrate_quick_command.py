# -*- coding: utf-8 -*-
r"""
快速命令云端同步功能 - 数据库迁移脚本

运行方式:
    cd BadCaseDoctor
    python scripts\migrate_quick_command.py

将会创建 quick_command 表。
"""
import sys
sys.path.insert(0, '.')

from app import app, db

with app.app_context():
    # 检查表是否已存在
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    
    if 'quick_command' in tables:
        print("表 'quick_command' 已存在，无需创建。")
    else:
        db.create_all()
        print("表 'quick_command' 创建成功！")
