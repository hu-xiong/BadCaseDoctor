"""Update card table type column to add 'card' enum value"""
import pymysql

# Database config
config = {
    'host': '117.72.33.38',
    'port': 33106,
    'user': 'root',
    'password': 'hx123456',
    'database': 'bad_case',
    'charset': 'utf8mb4'
}

try:
    connection = pymysql.connect(**config)
    with connection.cursor() as cursor:
        # MySQL enum column modify
        sql = """
        ALTER TABLE card 
        MODIFY COLUMN type ENUM('bug', 'badcase', 'testcase', 'card') 
        NOT NULL DEFAULT 'badcase'
        """
        cursor.execute(sql)
        connection.commit()
        print("[OK] Successfully added 'card' to type enum")
except Exception as e:
    print(f"[ERROR] {e}")
finally:
    connection.close()
