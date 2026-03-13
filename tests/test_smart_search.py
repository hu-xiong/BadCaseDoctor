#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试智能搜索引擎选择功能
"""

import os
import sys
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

from agents.prompts import _smart_select_search_engine

def test_smart_search_engine():
    """测试智能搜索引擎选择"""
    
    print("=" * 60)
    print("测试智能搜索引擎选择功能")
    print("=" * 60)
    
    # 测试用例
    test_cases = [
        {
            'name': '纯中文关键词',
            'params': {'query': 'C罗'},
            'expected': 'baidu'
        },
        {
            'name': '纯英文关键词',
            'params': {'query': 'Cristiano Ronaldo'},
            'expected': 'google'
        },
        {
            'name': '技术文档查询',
            'params': {'query': 'Python asyncio tutorial'},
            'expected': 'google'
        },
        {
            'name': '中文技术查询',
            'params': {'query': 'Python 教程'},
            'expected': 'baidu'
        },
        {
            'name': '混合中英文',
            'params': {'query': 'Python 教程 tutorial'},
            'expected': 'baidu'  # 默认百度
        },
        {
            'name': '国际平台关键词',
            'params': {'query': 'github actions'},
            'expected': 'google'
        },
        {
            'name': '中国本土关键词',
            'params': {'query': '淘宝'},
            'expected': 'baidu'
        },
        {
            'name': '已指定引擎',
            'params': {'query': 'test', 'engine': 'bing'},
            'expected': 'bing'
        },
        {
            'name': '空查询',
            'params': {},
            'expected': 'baidu'  # 默认
        },
    ]
    
    passed = 0
    failed = 0
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n测试 {i}: {case['name']}")
        print(f"  输入: {case['params']}")
        
        result = _smart_select_search_engine(case['params'].copy())
        actual_engine = result.get('engine', 'unknown')
        
        print(f"  期望引擎: {case['expected']}")
        print(f"  实际引擎: {actual_engine}")
        
        if actual_engine == case['expected']:
            print("  ✅ 通过")
            passed += 1
        else:
            print("  ❌ 失败")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"测试结果: 通过 {passed}/{len(test_cases)}, 失败 {failed}/{len(test_cases)}")
    print("=" * 60)

if __name__ == '__main__':
    test_smart_search_engine()
