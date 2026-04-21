import pymysql
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 数据库配置
DB_CONFIG = {
    'host': '117.72.33.38',
    'port': 33106,
    'user': 'root',
    'password': 'hx123456',
    'database': 'bad_case',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

def clear_projects_and_plans():
    """清除项目和对应计划的数据"""
    try:
        # 连接数据库
        connection = pymysql.connect(**DB_CONFIG)
        cursor = connection.cursor()
        
        print("连接数据库成功")
        
        # 定义需要删除的表（按照依赖关系顺序）
        tables_to_clear = [
            'card_plan_relation',  # 卡片与计划的关联
            'card',  # 卡片
            'bug',  # Bug
            'test_case',  # 测试用例
            'bad_case',  # BadCase
            'plan',  # 计划
            'project_permission',  # 项目权限
            'team',  # 团队
            'team_member',  # 团队成员
            'chat_session',  # 聊天会话
            'chat_message',  # 聊天消息
            'comment',  # 评论
            'bug_comment',  # Bug评论
            'proposal',  # 提案
            'proposal_snapshot',  # 提案快照
            'diff_review_state',  # 差异审查状态
            'quick_command',  # 快速命令
            'terminal_audit',  # 终端审计
            'workflow_in_app_notification',  # 工作流通知
            'project'  # 项目（最后删除）
        ]
        
        # 对每个表执行删除操作
        for table_name in tables_to_clear:
            print(f"\n清空表: {table_name}")
            try:
                # 执行删除操作
                cursor.execute(f"DELETE FROM {table_name}")
                connection.commit()
                print(f"成功清空表: {table_name}")
                
                # 重置自增ID
                cursor.execute(f"ALTER TABLE {table_name} AUTO_INCREMENT = 1")
                connection.commit()
                print(f"成功重置表 {table_name} 的自增ID")
            except Exception as e:
                print(f"清空表 {table_name} 失败: {e}")
                connection.rollback()
        
        print("\n操作完成")
        
    except Exception as e:
        print(f"错误: {e}")
    finally:
        if 'connection' in locals():
            connection.close()
            print("数据库连接已关闭")

if __name__ == "__main__":
    clear_projects_and_plans()