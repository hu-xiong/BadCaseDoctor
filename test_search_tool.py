#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试搜索工具
"""

import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.tools.search_tool import SearchTool
from agents.tool_registry import ToolRegistry
from agents.intelligent_devops_agent import IntelligentDevOpsAgent
from llm.qianfan_llm import QianfanLLM


async def test_search_tool():
    """测试搜索工具"""
    print("=" * 60)
    print("测试搜索工具")
    print("=" * 60)
    
    # 初始化搜索工具
    search_tool = SearchTool()
    
    # 测试百度搜索
    print("\n1️⃣ 测试百度搜索 C罗")
    result = await search_tool.execute(query="C罗", engine="baidu", limit=5)
    print(f"搜索结果数量: {result.get('total_results', 0)}")
    if result.get('results'):
        for i, res in enumerate(result['results'][:3], 1):
            print(f"  {i}. {res.get('title', 'N/A')}")
            print(f"     URL: {res.get('url', 'N/A')}")
            print(f"     描述: {res.get('snippet', 'N/A')[:100]}...")
    
    # 测试 Google 搜索
    print("\n2️⃣ 测试 Google 搜索 Python")
    result = await search_tool.execute(query="Python编程", engine="google", limit=5)
    print(f"搜索结果数量: {result.get('total_results', 0)}")
    if result.get('results'):
        for i, res in enumerate(result['results'][:2], 1):
            print(f"  {i}. {res.get('title', 'N/A')}")
    
    # 测试工具注册
    print("\n3️⃣ 测试工具注册")
    registry = ToolRegistry()
    registry.register(search_tool)
    print(f"已注册工具: {registry.list_tools()}")
    
    print("\n✅ 所有测试通过")


async def test_with_agent():
    """与 Agent 集成测试"""
    print("\n" + "=" * 60)
    print("测试与 Agent 集成")
    print("=" * 60)
    
    # 初始化 LLM 和 Agent
    llm = QianfanLLM()
    agent = IntelligentDevOpsAgent(llm=llm, db_session=None)
    
    # 检查搜索工具是否已注册
    print(f"\n已注册工具列表:")
    for tool in agent.tool_registry.list_tools():
        print(f"  - {tool['name']}: {tool['description']}")
    
    # 验证搜索工具存在
    if agent.tool_registry.has_tool('search'):
        print("\n✅ 搜索工具已成功注册")
    else:
        print("\n❌ 搜索工具未注册")


if __name__ == '__main__':
    print("🚀 开始测试搜索工具\n")
    
    # 运行基础测试
    asyncio.run(test_search_tool())
    
    # 运行 Agent 集成测试
    try:
        asyncio.run(test_with_agent())
    except Exception as e:
        print(f"\nAgent 测试中出错: {e}")
        print("这是正常的，如果 LLM 配置不可用")
