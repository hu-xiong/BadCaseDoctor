# agents/tools/login_state_tool.py
"""
登录状态管理工具
支持保存和加载浏览器登录状态（cookies + storage），避免重复登录
"""

import asyncio
import json
import os
import uuid
import hashlib
from typing import Dict, Any, Optional
from playwright.async_api import async_playwright
from ..tool_registry import BaseTool

# 登录状态存储目录
STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'tmp', 'login_states')
os.makedirs(STATE_DIR, exist_ok=True)


def get_state_path(domain: str) -> str:
    """根据域名生成状态文件路径"""
    domain_hash = hashlib.md5(domain.encode()).hexdigest()[:8]
    return os.path.join(STATE_DIR, f'{domain_hash}_{domain.replace(":", "_").replace("/", "_")}.json')


class LoginStateTool(BaseTool):
    """登录状态管理工具"""
    
    def __init__(self):
        super().__init__(
            name='login_state',
            description='管理浏览器登录状态：保存登录后的cookies，下次自动加载跳过登录'
        )
    
    async def execute(self, action: str, url: str = None, **kwargs) -> Dict[str, Any]:
        """
        执行登录状态管理
        
        Args:
            action: 'save' | 'load' | 'check' | 'manual_login'
            url: 目标URL（域名）
        """
        if action == 'manual_login':
            return await self._manual_login_and_save(url, **kwargs)
        elif action == 'save':
            return await self._save_state(url)
        elif action == 'load':
            return await self._load_state(url)
        elif action == 'check':
            return self._check_state(url)
        else:
            return {'success': False, 'error': f'未知操作: {action}'}
    
    def _check_state(self, url: str) -> Dict[str, Any]:
        """检查是否有保存的登录状态"""
        if not url:
            return {'success': False, 'error': '缺少URL参数'}
        
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        state_path = get_state_path(domain)
        
        exists = os.path.exists(state_path)
        return {
            'success': True,
            'has_saved_state': exists,
            'domain': domain,
            'state_path': state_path if exists else None
        }
    
    async def _manual_login_and_save(self, url: str, timeout: int = 120, **kwargs) -> Dict[str, Any]:
        """
        打开浏览器让用户手动登录，登录完成后保存状态
        
        流程：
        1. 打开可视化浏览器访问目标URL
        2. 用户手动完成登录
        3. 用户确认登录完成（关闭浏览器或超时）
        4. 保存cookies和storage state
        """
        if not url:
            return {'success': False, 'error': '缺少URL参数'}
        
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        state_path = get_state_path(domain)
        
        print(f"[LOGIN_STATE] 🔐 手动登录模式")
        print(f"[LOGIN_STATE]   目标: {url}")
        print(f"[LOGIN_STATE]   请在浏览器中完成登录，完成后关闭浏览器窗口")
        
        try:
            async with async_playwright() as p:
                # 使用有界面的浏览器让用户操作
                browser = await p.chromium.launch(
                    headless=False,  # 显示浏览器让用户操作
                    args=['--no-sandbox', '--disable-setuid-sandbox']
                )
                
                context = await browser.new_context()
                page = await context.new_page()
                
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                
                print(f"[LOGIN_STATE] ⏳ 等待用户完成登录（最长 {timeout} 秒）...")
                
                # 等待用户关闭浏览器或超时
                try:
                    await asyncio.wait_for(
                        page.wait_for_event('close'),
                        timeout=timeout
                    )
                except asyncio.TimeoutError:
                    print(f"[LOGIN_STATE] ⏰ 超时，自动保存当前状态")
                
                # 保存状态
                storage_state = await context.storage_state()
                
                with open(state_path, 'w', encoding='utf-8') as f:
                    json.dump(storage_state, f, ensure_ascii=False, indent=2)
                
                await context.close()
                await browser.close()
                
                cookies_count = len(storage_state.get('cookies', []))
                print(f"[LOGIN_STATE] ✅ 登录状态已保存（{cookies_count} 个cookies）")
                
                return {
                    'success': True,
                    'domain': domain,
                    'state_path': state_path,
                    'cookies_count': cookies_count,
                    'message': f'登录状态已保存，后续测试将自动加载'
                }
        
        except Exception as e:
            print(f"[LOGIN_STATE] ❌ 保存失败: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    async def _save_state(self, url: str) -> Dict[str, Any]:
        """从当前浏览器会话保存状态（需要浏览器已打开）"""
        return {'success': False, 'error': '请使用 manual_login 操作'}
    
    async def _load_state(self, url: str) -> Dict[str, Any]:
        """加载保存的登录状态"""
        if not url:
            return {'success': False, 'error': '缺少URL参数'}
        
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        state_path = get_state_path(domain)
        
        if not os.path.exists(state_path):
            return {
                'success': False,
                'error': f'未找到 {domain} 的登录状态，请先执行 manual_login'
            }
        
        return {
            'success': True,
            'domain': domain,
            'state_path': state_path,
            'message': '登录状态可用'
        }


def get_storage_state_for_url(url: str) -> Optional[str]:
    """
    获取URL对应的storage_state文件路径
    供其他工具调用，在启动浏览器时加载登录状态
    """
    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    state_path = get_state_path(domain)
    
    if os.path.exists(state_path):
        return state_path
    return None
