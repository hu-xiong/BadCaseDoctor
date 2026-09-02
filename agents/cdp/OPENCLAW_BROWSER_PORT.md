# -*- coding: utf-8 -*-
"""
OpenClaw Browser 能力对齐说明（MIT 合法移植，非绑定 Gateway）。

来源：https://github.com/openclaw/openclaw （MIT License）
Copyright (c) 2026 OpenClaw Foundation

实现策略：
- OpenClaw Browser = **Playwright 驱动 + CDP/无障碍树 refs**（不是 browser-use）。
- BadCaseDoctor 在自有 Python ``agents/cdp`` 中按同一动作集补齐，
  不依赖 OpenClaw Gateway / Node 插件。

已对齐动作（经 cdp 工具 action）：
session/tabs/open/focus/navigate/snapshot/click/click_coords/type/press/
hover/scroll/drag/select/fill/wait/get_text/screenshot/pdf/evaluate/
extract/resize/console/login/assert/explore/batch

Agent 闭环（对齐 OpenClaw screenshot vision + browser-automation skill）：
- screenshot 成功后自动视觉理解 → observation.vision_description 回传主模型
- click/fill 失败同样截图+视觉描述 + agent_hint
- stale ref：自动轻量 snapshot + focus_hints，提示换新 @eN 重试
- 主路径仍是无障碍树 refs；视觉为兜底（CDP_SCREENSHOT_VISION / CDP_VISION_RECOVER）
"""
