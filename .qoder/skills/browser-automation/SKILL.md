---
name: browser-automation
description: OpenClaw 风格 CDP 浏览器闭环。snapshot→act→失败看图再决策；stale ref 重拍；screenshot 返回视觉描述。
---

# Browser Automation（CDP / OpenClaw 对齐）

主路径：**无障碍树 refs**，不是坐标乱点。视觉截图是兜底。

## 标准闭环

1. `cdp action=session`（create + url）→ 需要登录则 `login`
2. `snapshot` 拿到 `@e1…` → 再 `click` / `fill` / `assert`
3. **UI 变化后必须重新 snapshot**，禁止复用旧 ref
4. 失败时：
   - 读 observation 的 `vision_description`、`agent_hint`
   - `stale_ref`：用 `new_snapshot_id` / `focus_hints` 换新 `@eN`，**只重试一次**
   - 状态不明：`screenshot`（会自动返回视觉描述文本）→ 再决策
5. 登录/验证码/滑块：走 `login`；验证码等用户，勿猜测

## 探测性测试

- 用户说「测试下 + URL」：session 后系统可自动 explore
- explore 内另有视觉纠错兜底（`CDP_VISION_RECOVER`），不替代你在对话里的闭环决策

## 禁止

- 空口说「已完成」而未读工具结果
- 失败后不看 `vision_description` 就换无关策略
- 沿用已声明 stale 的旧 ref
