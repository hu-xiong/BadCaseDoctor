"""
修复 Bug 表的 card_id 关联
根据 Bug 的标题和类型，匹配到对应的卡片

使用方法:
1. 确保后端服务正在运行
2. 修改下面的 project_id 和 bug_title_card_mapping 为你要修复的数据
3. 运行脚本: python fix_bug_card_mapping.py
"""

import requests
import json

BASE_URL = "http://localhost:5000"

# 配置
PROJECT_ID = 1  # 项目ID
BUG_TITLE_CARD_MAPPING = {
    # "Bug标题": "对应的卡片标题",
    # 例如：
    # "登录失败bug": "卡片测试",
}

def login():
    """登录获取会话"""
    session = requests.Session()
    # 如果需要登录，取消下面的注释并填入凭据
    # session.post(f"{BASE_URL}/login", data={"username": "xxx", "password": "xxx"})
    return session

def get_cards(session, project_id):
    """获取项目的所有卡片"""
    response = session.get(f"{BASE_URL}/api/projects/{project_id}/cards", params={"per_page": 100})
    data = response.json()
    if data.get("success"):
        return data.get("data", [])
    return []

def get_bugs(session, project_id):
    """获取项目的所有Bug"""
    response = session.get(f"{BASE_URL}/api/projects/{project_id}/bugs", params={"per_page": 100})
    data = response.json()
    if data.get("success"):
        return data.get("badcases", [])
    return []

def update_bug_card(session, bug_id, card_id):
    """更新Bug的card_id"""
    response = session.put(f"{BASE_URL}/api/bugs/{bug_id}", json={"card_id": card_id})
    return response.json()

def main():
    session = login()
    
    # 获取所有卡片
    cards = get_cards(session, PROJECT_ID)
    print(f"找到 {len(cards)} 个卡片")
    
    # 创建卡片标题到ID的映射
    card_map = {c["title"]: c["id"] for c in cards}
    print(f"卡片映射: {card_map}")
    
    # 获取所有Bug
    bugs = get_bugs(session, PROJECT_ID)
    print(f"找到 {len(bugs)} 个Bug")
    
    # 统计没有card_id的Bug
    bugs_without_card = [b for b in bugs if b.get("card_id") is None]
    print(f"没有card_id的Bug: {len(bugs_without_card)}")
    
    if BUG_TITLE_CARD_MAPPING:
        print("\n开始修复...")
        for bug in bugs_without_card:
            bug_title = bug.get("title", "")
            if bug_title in BUG_TITLE_CARD_MAPPING:
                card_title = BUG_TITLE_CARD_MAPPING[bug_title]
                card_id = card_map.get(card_title)
                if card_id:
                    print(f"修复 Bug {bug['id']} ({bug_title}) -> 卡片 {card_id} ({card_title})")
                    result = update_bug_card(session, bug["id"], card_id)
                    if result.get("success"):
                        print(f"  ✅ 修复成功")
                    else:
                        print(f"  ❌ 修复失败: {result.get('error')}")
                else:
                    print(f"  ⚠️ 找不到卡片: {card_title}")
    else:
        print("\n请设置 BUG_TITLE_CARD_MAPPING 来指定Bug和卡片的对应关系")

if __name__ == "__main__":
    main()
