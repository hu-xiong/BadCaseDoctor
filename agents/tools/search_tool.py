# agents/tools/search_tool.py
"""
网络搜索工具
使用浏览器访问搜索引擎（百度、Google等）获取搜索结果
"""

import asyncio
import json
from typing import Dict, Any, List
from ..tool_registry import BaseTool


class SearchTool(BaseTool):
    """网络搜索工具"""
    
    def __init__(self, llm=None):
        """
        初始化搜索工具
            
        Args:
            llm: 语言模型实例（可选）
        """
        super().__init__(
            name='search',
            description='使用搜索引擎（百度/Google/Bing）搜索信息'
        )
        self.llm = llm
    
    async def execute(
        self,
        query: str = None,
        engine: str = 'baidu',
        limit: int = 10,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行搜索
            
        Args:
            query: 搜索关键词
            engine: 搜索引擎 (baidu/google/bing)
            limit: 返回结果数量
            **kwargs: 其他参数
                
        Returns:
            搜索结果
        """
        # 兼容各种参数名
        if not query:
            query = kwargs.get('keyword') or kwargs.get('keywords') or kwargs.get('search_query') or kwargs.get('q')
                    
        if not query:
            return {'error': '缺少搜索关键词', 'success': False}
                
        # 将 engine 转换为小写，兼容大小写
        engine = engine.lower() if engine else 'baidu'
                    
        print(f"[SEARCH] 🔍 搜索关键词: {query} (引擎: {engine})")
                    
        if engine == 'baidu':
            return await self._search_baidu(query, limit)
        elif engine == 'google':
            return await self._search_google(query, limit)
        elif engine == 'bing':
            return await self._search_bing(query, limit)
        else:
            return await self._search_baidu(query, limit)  # 默认百度
    
    async def _search_baidu(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """
        使用百度搜索 - 真实浏览器访问
        """
        print(f"[SEARCH] 🔎 百度搜索: {query}")
        
        try:
            from playwright.async_api import async_playwright
            import base64
            import os
            import tempfile
            import uuid
            
            # 设置临时目录为项目下的 tmp 文件夹
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            tmp_dir = os.path.join(project_root, 'tmp')
            os.makedirs(tmp_dir, exist_ok=True)
            
            # 强制设置环境变量
            os.environ['TMPDIR'] = tmp_dir
            os.environ['TEMP'] = tmp_dir
            os.environ['TMP'] = tmp_dir
            # 使用系统默认的 Playwright 浏览器路径
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '0'
            
            # 为每次启动生成唯一的 user-data-dir
            unique_profile = os.path.join(tmp_dir, f'chrome_profile_{uuid.uuid4().hex[:8]}')
            os.makedirs(unique_profile, exist_ok=True)
            
            async with async_playwright() as p:
                context = await p.chromium.launch_persistent_context(
                    unique_profile,
                    headless=True,
                    timeout=60000,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage'
                    ]
                )
                page = await context.new_page()
                
                # 访问百度
                search_url = f"https://www.baidu.com/s?wd={query}"
                print(f"[SEARCH] 📡 访问: {search_url}")
                await page.goto(search_url, wait_until='domcontentloaded', timeout=60000)
                
                # 等待搜索结果加载（增加等待时间）
                await page.wait_for_selector('.result', timeout=10000)
                await page.wait_for_timeout(2000)  # 额外等待2秒确保动态内容加载
                
                # 提取搜索结果
                results = await page.evaluate('''
                    () => {
                        // 排除AI回答卡片，只提取真实搜索结果
                        const items = Array.from(document.querySelectorAll('.result, .c-container')).filter(item => {
                            // 排除百度AI回答（通常在顶部且没有真实URL）
                            const link = item.querySelector('h3 a') || item.querySelector('a[data-title]');
                            if (!link || !link.href || link.href.includes('javascript:')) return false;
                            
                            // 排除空白内容
                            const title = link.innerText || '';
                            if (!title.trim()) return false;
                            
                            return true;
                        });
                        
                        console.log('找到有效搜索结果数量:', items.length);
                        return items.slice(0, 10).map((item, index) => {
                            const titleEl = item.querySelector('h3 a') || item.querySelector('a[data-title]');
                            const snippetEl = item.querySelector('.c-abstract') || item.querySelector('.c-span18');
                            return {
                                title: titleEl ? titleEl.innerText : '',
                                url: titleEl ? titleEl.href : '',
                                snippet: snippetEl ? snippetEl.innerText : '',
                                rank: index + 1
                            };
                        });
                    }
                ''')
                
                # 截图
                screenshot = await page.screenshot(full_page=False)
                screenshot_base64 = base64.b64encode(screenshot).decode()
                
                await context.close()
                
                print(f"[SEARCH] ✅ 提取到 {len(results)} 条结果")
                
                return {
                    'query': query,
                    'engine': 'baidu',
                    'total_results': len(results),
                    'results': results,
                    'screenshot': screenshot_base64,
                    'success': True
                }
        
        except Exception as e:
            print(f"[SEARCH] ❌ 搜索失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                'error': str(e),
                'success': False
            }
    
    async def _search_google(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """
        使用 Google 搜索 - 真实浏览器访问
        """
        print(f"[SEARCH] 🔎 Google搜索: {query}")
        
        try:
            from playwright.async_api import async_playwright
            import base64
            import os
            import tempfile
            import uuid
            
            # 设置临时目录为项目下的 tmp 文件夹
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            tmp_dir = os.path.join(project_root, 'tmp')
            os.makedirs(tmp_dir, exist_ok=True)
            
            # 强制设置环境变量
            os.environ['TMPDIR'] = tmp_dir
            os.environ['TEMP'] = tmp_dir
            os.environ['TMP'] = tmp_dir
            # 使用系统默认的 Playwright 浏览器路径
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '0'
            
            # 为每次启动生成唯一的 user-data-dir
            unique_profile = os.path.join(tmp_dir, f'chrome_profile_{uuid.uuid4().hex[:8]}')
            os.makedirs(unique_profile, exist_ok=True)
            
            async with async_playwright() as p:
                context = await p.chromium.launch_persistent_context(
                    unique_profile,
                    headless=True,
                    timeout=60000,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage'
                    ]
                )
                page = await context.new_page()
                
                # 访问 Google
                search_url = f"https://www.google.com/search?q={query}"
                print(f"[SEARCH] 📡 访问: {search_url}")
                await page.goto(search_url, wait_until='domcontentloaded', timeout=60000)
                
                # 等待搜索结果加载
                await page.wait_for_selector('.g', timeout=5000)
                
                # 提取搜索结果
                results = await page.evaluate('''
                    () => {
                        const items = Array.from(document.querySelectorAll('.g'));
                        return items.slice(0, 10).map((item, index) => {
                            const titleEl = item.querySelector('h3');
                            const linkEl = item.querySelector('a');
                            const snippetEl = item.querySelector('.VwiC3b');
                            return {
                                title: titleEl ? titleEl.innerText : '',
                                url: linkEl ? linkEl.href : '',
                                snippet: snippetEl ? snippetEl.innerText : '',
                                rank: index + 1
                            };
                        });
                    }
                ''')
                
                # 截图
                screenshot = await page.screenshot(full_page=False)
                screenshot_base64 = base64.b64encode(screenshot).decode()
                
                await context.close()
                
                print(f"[SEARCH] ✅ 提取到 {len(results)} 条结果")
                
                return {
                    'query': query,
                    'engine': 'google',
                    'total_results': len(results),
                    'results': results,
                    'screenshot': screenshot_base64,
                    'success': True
                }
        
        except Exception as e:
            print(f"[SEARCH] ❌ 搜索失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                'error': str(e),
                'success': False
            }
    
    async def _search_bing(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """
        使用 Bing 搜索 - 真实浏览器访问
        """
        print(f"[SEARCH] 🔎 Bing搜索: {query}")
        
        try:
            from playwright.async_api import async_playwright
            import base64
            import os
            import tempfile
            import uuid
            
            # 设置临时目录为项目下的 tmp 文件夹
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            tmp_dir = os.path.join(project_root, 'tmp')
            os.makedirs(tmp_dir, exist_ok=True)
            
            # 强制设置环境变量
            os.environ['TMPDIR'] = tmp_dir
            os.environ['TEMP'] = tmp_dir
            os.environ['TMP'] = tmp_dir
            # 使用系统默认的 Playwright 浏览器路径
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '0'
            
            # 为每次启动生成唯一的 user-data-dir
            unique_profile = os.path.join(tmp_dir, f'chrome_profile_{uuid.uuid4().hex[:8]}')
            os.makedirs(unique_profile, exist_ok=True)
            
            async with async_playwright() as p:
                context = await p.chromium.launch_persistent_context(
                    unique_profile,
                    headless=True,
                    timeout=60000,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage'
                    ]
                )
                page = await context.new_page()
                
                # 访问 Bing
                search_url = f"https://www.bing.com/search?q={query}"
                print(f"[SEARCH] 📡 访问: {search_url}")
                await page.goto(search_url, wait_until='domcontentloaded', timeout=60000)
                
                # 等待搜索结果加载
                await page.wait_for_selector('.b_algo', timeout=5000)
                
                # 提取搜索结果
                results = await page.evaluate('''
                    () => {
                        const items = Array.from(document.querySelectorAll('.b_algo'));
                        return items.slice(0, 10).map((item, index) => {
                            const titleEl = item.querySelector('h2 a');
                            const snippetEl = item.querySelector('.b_caption p');
                            return {
                                title: titleEl ? titleEl.innerText : '',
                                url: titleEl ? titleEl.href : '',
                                snippet: snippetEl ? snippetEl.innerText : '',
                                rank: index + 1
                            };
                        });
                    }
                ''')
                
                # 截图
                screenshot = await page.screenshot(full_page=False)
                screenshot_base64 = base64.b64encode(screenshot).decode()
                
                await context.close()
                
                print(f"[SEARCH] ✅ 提取到 {len(results)} 条结果")
                
                return {
                    'query': query,
                    'engine': 'bing',
                    'total_results': len(results),
                    'results': results,
                    'screenshot': screenshot_base64,
                    'success': True
                }
        
        except Exception as e:
            print(f"[SEARCH] ❌ 搜索失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                'error': str(e),
                'success': False
            }
    
    async def _simulate_baidu_search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        模拟百度搜索结果
        """
        # 模拟延迟
        await asyncio.sleep(1)
        
        # 根据关键词返回相关结果
        if 'c罗' in query.lower() or 'cristiano' in query.lower():
            return [
                {
                    'title': '克里斯蒂亚诺·罗纳尔多（C罗） - 百度百科',
                    'url': 'https://baike.baidu.com/item/克里斯蒂亚诺·罗纳尔多',
                    'snippet': 'C罗（克里斯蒂亚诺·罗纳尔多）是葡萄牙足球运动员，被誉为世界足坛第一人。生于1985年2月5日，身高187cm，体重83kg。',
                    'rank': 1
                },
                {
                    'title': 'C罗个人资料 - 球迷论坛',
                    'url': 'https://forum.baidu.com/c-luo-personal',
                    'snippet': 'C罗职业生涯统计：出场次数超过1000场，进球数超过800个。现效力沙特阿拉伯足球超级联赛球队。',
                    'rank': 2
                },
                {
                    'title': 'C罗转会新闻最新消息',
                    'url': 'https://news.baidu.com/c-luo-transfer',
                    'snippet': '最新转会新闻：C罗于2023年加盟沙特阿拉伯Al Nassr足球俱乐部，成为历史最高薪球员。',
                    'rank': 3
                },
                {
                    'title': 'C罗vs梅西：谁是足坛第一人',
                    'url': 'https://sports.baidu.com/c-luo-vs-messi',
                    'snippet': '球迷热议：C罗和梅西都是足坛传奇，两人各有千秋。C罗以强大的身体素质和头球能力见长，梅西以技术和盘带见长。',
                    'rank': 4
                },
                {
                    'title': 'C罗职业生涯荣誉汇总',
                    'url': 'https://baike.baidu.com/c-luo-honors',
                    'snippet': '职业荣誉：5次欧冠冠军、7次金球奖得主、多次被评为世界足球先生。带领球队赢得多个国际大赛冠军。',
                    'rank': 5
                },
                {
                    'title': 'C罗与皇马的传奇故事',
                    'url': 'https://sports.baidu.com/c-luo-real-madrid',
                    'snippet': '在皇马效力期间，C罗打进超过500球，创造多项历史纪录。与皇马期间荣获4次欧冠和2次西甲冠军。',
                    'rank': 6
                }
            ]
        elif '足球' in query or 'football' in query.lower():
            return [
                {
                    'title': '足球运动介绍 - 百度百科',
                    'url': 'https://baike.baidu.com/item/足球',
                    'snippet': '足球是一项以脚踢球为主，但也可以用头顶球的球类运动。两队各11人，在长方形球场上对抗。',
                    'rank': 1
                },
                {
                    'title': '国际足球联合会（FIFA）官方网站',
                    'url': 'https://www.fifa.com',
                    'snippet': 'FIFA是国际足球联合会，负责管理全球足球事务，组织世界杯等重大赛事。',
                    'rank': 2
                }
            ]
        else:
            # 通用搜索结果
            return [
                {
                    'title': f'{query} - 搜索结果1',
                    'url': f'https://baidu.com/s?wd={query}&result=1',
                    'snippet': f'关于"{query}"的搜索结果1，包含相关信息和介绍。',
                    'rank': 1
                },
                {
                    'title': f'{query} - 搜索结果2',
                    'url': f'https://baidu.com/s?wd={query}&result=2',
                    'snippet': f'关于"{query}"的搜索结果2，提供更多详细信息。',
                    'rank': 2
                }
            ]
    
    async def _simulate_google_search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        模拟 Google 搜索结果
        """
        await asyncio.sleep(1)
        
        if 'c罗' in query.lower() or 'cristiano' in query.lower():
            return [
                {
                    'title': 'Cristiano Ronaldo - Wikipedia',
                    'url': 'https://en.wikipedia.org/wiki/Cristiano_Ronaldo',
                    'snippet': 'Cristiano Ronaldo is a Portuguese professional footballer who plays as a forward. He is considered one of the greatest footballers of all time.',
                    'rank': 1
                },
                {
                    'title': 'Cristiano Ronaldo Official Site',
                    'url': 'https://www.cristiano.com',
                    'snippet': 'Official website of Cristiano Ronaldo with latest news, statistics, and personal information.',
                    'rank': 2
                }
            ]
        else:
            return [
                {
                    'title': f'{query} - Google Search Result 1',
                    'url': f'https://google.com/search?q={query}&result=1',
                    'snippet': f'Information about "{query}" from Google search result 1.',
                    'rank': 1
                }
            ]
    
    async def _simulate_bing_search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        模拟 Bing 搜索结果
        """
        await asyncio.sleep(1)
        
        return [
            {
                'title': f'{query} - Bing Search',
                'url': f'https://bing.com/search?q={query}',
                'snippet': f'Bing search results for "{query}".',
                'rank': 1
            }
        ]
