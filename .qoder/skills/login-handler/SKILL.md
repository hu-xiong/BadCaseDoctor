---
name: login-handler
description: 处理browser-use测试时的登录问题。当浏览器访问页面被重定向到登录界面时自动处理登录流程。使用用户名密码登录，支持登录状态持久化。
---

# Login Handler

处理测试过程中的登录问题。

## 触发场景

- 浏览器访问目标页面但被重定向到登录页
- 页面URL包含 `/login`、`#/login` 或 `signin`
- 页面出现登录表单

## 登录凭证获取优先级

1. **项目网站登录配置** - `project.login_configs`（url/username/password）
2. **本地凭证文件** - 读取 `tmp/login_states/credentials.json`
3. **用户手动输入** - 提示用户填写后保存到凭证文件

凭证文件格式 (`tmp/login_states/credentials.json`):
```json
{
  "username": "用户名",
  "password": "密码"
}
```

## 处理流程

1. **检测登录页面**
   - 检查URL是否包含登录路径
   - 检查页面是否存在登录表单元素

2. **执行登录（CDP `action=login`）**
   ```
   - cdp session create + url
   - cdp action=login（自动读项目 login_configs 填账号密码）
   - 若返回 await_verification_code=true：暂停，请用户在对话发送验证码
   - 用户回复验证码后：cdp action=login + verification_code（同一 session_id）
   - 登录成功后继续 snapshot/click 等测试步骤
   ```

3. **验证码 / 图形码 / 滑块**
   - 短信/邮箱验证码：**必须**等用户发码，不可猜测
   - 可先自动点击「发送验证码」
   - 返回 `await_verification_code=true` 后暂停；pending 会写入 `tmp/login_states/pending/` 与浏览器 session
   - 用户下一条消息发纯数字验证码 → 自动 `cdp login+verification_code` 续登（无需 LLM 猜）
   - 图形验证码/滑块：提示用户手动完成或发码后继续

4. **验证登录成功**
   - 等待页面跳转
   - 确认URL不再是登录页面
   - 如果仍在登录页，检查是否有错误提示

5. **断言失败 → 自动落库预览（D4）**
   - `cdp assert` 失败后系统自动 `create(target=bug, confirm=false)` 预览
   - 复现步骤/实际结果来自 `cdp_test_evidence`
   - 用户在侧栏确认后落库；勿重复调用 create

6. **登录失败处理**
   - 记录错误信息
   - 提示用户手动登录
   - 等待用户确认后继续

## 登录状态持久化

使用 `tmp/login_states/` 目录保存登录状态：
- Cookie存储路径: `tmp/login_states/cookies.json`
- LocalStorage存储路径: `tmp/login_states/storage.json`

## 常见登录元素选择器

| 元素 | 选择器优先级 |
|------|-------------|
| 用户名输入框 | `#username`, `input[name="username"]`, `input[type="text"]` |
| 密码输入框 | `#password`, `input[name="password"]`, `input[type="password"]` |
| 登录按钮 | `#login-btn`, `.login-btn`, `button[type="submit"]` |
| 错误提示 | `.error`, `.alert-danger`, `.login-error` |

## 注意事项

- 优先使用用户名密码登录
- 避免明文记录密码到日志
- 登录成功后保存状态以便后续测试复用

## 已集成工具

`browser_test_tool.py` 已集成登录处理逻辑：

1. **凭证加载优先级**：参数传入 > 凭证文件 > 无凭证
2. **登录页检测**：自动检测URL是否包含 `/login`、`#/login` 等
3. **自动登录**：在 Browser Agent 任务中注入登录指南
4. **状态复用**：自动加载已保存的 storage_state
