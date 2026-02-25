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

1. **浏览器已保存的凭证** - 从浏览器自动填充中获取
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

2. **执行登录**
   ```
   - 定位用户名输入框 (input[type="text"], input[name="username"], #username)
   - 定位密码输入框 (input[type="password"], input[name="password"], #password)
   - 填入凭证
   - 点击登录按钮 (button[type="submit"], .login-btn, #login-btn)
   ```

3. **验证登录成功**
   - 等待页面跳转
   - 确认URL不再是登录页面
   - 如果仍在登录页，检查是否有错误提示

4. **登录失败处理**
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
