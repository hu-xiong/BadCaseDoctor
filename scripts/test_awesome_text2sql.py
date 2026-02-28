"""
GLM Text2SQL 测试脚本
验证GLM Text2SQL集成是否正常工作
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.tools.glm_text2sql_agent import GLMText2SQLAgent

def main():
    print("=" * 50)
    print("🔍 测试GLM Text2SQL集成")
    print("=" * 50)
    
    try:
        # 初始化GLM Text2SQL
        text2sql = GLMText2SQLAgent()
        
        # 测试查询
        test_queries = [
            "查询所有Bug数量",
            "查找最近创建的5个Bug",
            "统计每个项目的Bug数量"
        ]
        
        for query in test_queries:
            print(f"\n📝 测试查询: '{query}'")
            
            # 生成SQL
            sql = text2sql.generate_sql(query)
            print(f"生成的SQL: {sql}")
            
            # 执行SQL
            result = text2sql.execute_sql(sql, limit=5)
            
            if result['success']:
                print(f"✅ 查询成功")
                print(f"返回行数: {result['row_count']}")
                print("前5条结果:")
                for i, row in enumerate(result['data'][:5]):
                    print(f"  {i+1}. {row}")
            else:
                print(f"❌ 查询失败: {result['error']}")
                
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")

if __name__ == "__main__":
    main()