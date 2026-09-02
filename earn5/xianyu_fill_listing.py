# -*- coding: utf-8 -*-
"""Fill Xianyu publish form for AI agent service listing."""
from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
COVER = ROOT / "earn5" / "xianyu_agent_cover.png"
SHOT = ROOT / "earn5" / "xianyu_filled.png"

TITLE = "AI智能体定制开发 扣子Coze/Dify/私有Agent 客服知识库工作流"

DESC = """【接做 AI 智能体 · 不是卖模板】

帮你把「重复咨询 / 查资料 / 自动流程」做成能用的智能体。
能做扣子(Coze)、Dify，也能做可私有部署、能接工具的 Agent。

可做方向（常见）：
✓ 店铺/售后智能客服（FAQ + 议价话术 + 转人工）
✓ 企业知识库问答（文档/表格喂进去能问）
✓ 内容助手（文案、选题、多平台口吻）
✓ 工作流自动化（表单收集→整理→通知）
✓ 挂机助手类（规则回复 + 人设 + 底价保护）
✓ 需要调 API / 浏览器 / 脚本的进阶 Agent

技术栈（按你需求选，不硬推）：
· 扣子 Coze —— 快、零代码、适合先上线
· Dify —— 知识库/工作流更强，可私有化
· Python Agent（LangGraph 等）—— 要接真实工具、本地跑、深度定制

合作流程：
1. 你说要解决什么问题（有例子最好）
2. 我给方案 + 报价 + 工期
3. 定金开工 → 演示/修改 → 交付链接或源码
4. 约定范围内免费小改

购买说明：
· 本页 ¥35 仅为沟通/评估占位，正式项目另报
· 模型 API、服务器、第三方会员费买家自理
· 违法违规（刷单、作弊外挂等）不做
· 虚拟服务，沟通确认后开工，不支持无理由退

怎么开始：
直接拍下或私聊发：「场景 + 有没有现成文档/网站 + 预算大概」
有支付宝，可扫码定金后开工。

#AI智能体 #扣子 #Coze #Dify #Agent #智能客服 #工作流"""

# goofish description often wants title + body; keep under 1500
FULL = (TITLE + "\n\n" + DESC).strip()
if len(FULL) > 1490:
    FULL = FULL[:1490]

PRICE = "35"


def main() -> None:
    if not COVER.exists():
        raise SystemExit(f"cover missing: {COVER}")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9333")
        ctx = browser.contexts[0]
        page = None
        for pg in ctx.pages:
            if "publish" in pg.url:
                page = pg
                break
        if page is None:
            page = ctx.pages[-1]
            page.goto("https://www.goofish.com/publish", wait_until="domcontentloaded")
            time.sleep(2)

        page.bring_to_front()

        # Upload cover image
        file_inputs = page.locator('input[type="file"]')
        print("file inputs:", file_inputs.count())
        if file_inputs.count() == 0:
            # click add image area to reveal input
            for sel in ['text=添加首图', 'text=宝贝图片', '[class*="upload"]']:
                loc = page.locator(sel).first
                try:
                    if loc.count():
                        loc.click(timeout=2000)
                        time.sleep(0.5)
                except Exception:
                    pass
        file_inputs = page.locator('input[type="file"]')
        print("file inputs after click:", file_inputs.count())
        if file_inputs.count():
            file_inputs.first.set_input_files(str(COVER))
            print("uploaded cover")
            time.sleep(2)
        else:
            print("WARN: no file input found")

        # Description textarea
        area = page.locator("textarea").first
        if area.count():
            area.click()
            area.fill(FULL)
            print("filled description len=", len(FULL))
        else:
            # contenteditable fallback
            edit = page.locator('[contenteditable="true"]').first
            if edit.count():
                edit.click()
                page.keyboard.press("Control+A")
                page.keyboard.type(FULL, delay=5)
                print("filled contenteditable")
            else:
                print("WARN: no description field")

        # Price - first money input near 价格
        # try placeholder / spinbutton / input near label
        price_filled = False
        for sel in [
            'input[placeholder*="价格"]',
            'input[type="number"]',
            'input[inputmode="decimal"]',
            'input[inputmode="numeric"]',
        ]:
            locs = page.locator(sel)
            n = locs.count()
            print("price candidates", sel, n)
            if n:
                try:
                    locs.first.click()
                    locs.first.fill(PRICE)
                    price_filled = True
                    print("filled price via", sel)
                    break
                except Exception as e:
                    print("price fail", sel, e)

        if not price_filled:
            # click 价格 label then type
            try:
                page.get_by_text("价格", exact=True).first.click()
                page.keyboard.type(PRICE)
                print("typed price after label click")
            except Exception as e:
                print("price label fail", e)

        # Shipping: 无需邮寄
        for sel in ['text=无需邮寄', 'label:has-text("无需邮寄")']:
            loc = page.locator(sel).first
            try:
                if loc.count() and loc.is_visible():
                    loc.click(timeout=2000)
                    print("clicked 无需邮寄")
                    break
            except Exception as e:
                print("ship fail", e)

        time.sleep(1)
        page.screenshot(path=str(SHOT), full_page=True)
        print("SHOT", SHOT)
        print("DONE_FILL_NO_PUBLISH")  # wait for user confirm before clicking 发布


if __name__ == "__main__":
    main()
