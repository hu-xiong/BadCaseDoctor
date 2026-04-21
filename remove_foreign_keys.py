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

def remove_foreign_keys():
    """移除数据库中所有表的外键约束"""
    try:
        # 连接数据库
        connection = pymysql.connect(**DB_CONFIG)
        cursor = connection.cursor()
        
        print("连接数据库成功")
        
        # 获取所有表名
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        table_names = [table[f'Tables_in_{DB_CONFIG["database"]}'] for table in tables]
        
        print(f"找到 {len(table_names)} 个表")
        
        # 对每个表执行操作
        for table_name in table_names:
            print(f"\n处理表: {table_name}")
            
            # 获取表的外键约束
            cursor.execute(f"""
                SELECT CONSTRAINT_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME 
                FROM information_schema.KEY_COLUMN_USAGE 
                WHERE TABLE_SCHEMA = '{DB_CONFIG["database"]}' 
                AND TABLE_NAME = '{table_name}' 
                AND REFERENCED_TABLE_NAME IS NOT NULL
            """)
            foreign_keys = cursor.fetchall()
            
            if foreign_keys:
                print(f"找到 {len(foreign_keys)} 个外键约束")
                
                # 生成并执行移除外键的SQL
                for fk in foreign_keys:
                    constraint_name = fk['CONSTRAINT_NAME']
                    print(f"移除外键约束: {constraint_name}")
                    
                    try:
                        cursor.execute(f"ALTER TABLE {table_name} DROP FOREIGN KEY {constraint_name}")
                        connection.commit()
                        print(f"成功移除外键约束: {constraint_name}")
                    except Exception as e:
                        print(f"移除外键约束 {constraint_name} 失败: {e}")
                        connection.rollback()
            else:
                print("没有找到外键约束")
        
        print("\n操作完成")
        
    except Exception as e:
        print(f"错误: {e}")
    finally:
        if 'connection' in locals():
            connection.close()
            print("数据库连接已关闭")

if __name__ == "__main__":
    remove_foreign_keys()