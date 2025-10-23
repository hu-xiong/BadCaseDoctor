# BadCase Doctor

基于Flask的BadCase管理系统，支持用户管理、项目管理、BadCase工作流和AI对话功能。

## 主要功能

### 用户管理
- **邮箱验证注册**：用户注册时需要邮箱验证码验证
- **密码加密存储**：使用passlib进行密码加密
- **忘记密码功能**：通过邮箱验证码重置密码
- **用户角色管理**：支持项目管理员和项目协作者两种角色

### 项目管理
- **项目创建**：用户可以创建自己的项目
- **权限管理**：项目管理员可以邀请成员、分配权限
- **项目状态**：支持发布/未发布状态管理

### BadCase管理
- **状态流转**：
  - 新建 → 待处理 → 已处理 → 已解决
  - 支持hold、重新打开等状态
- **优先级管理**：P1（高）、P2（中）、P3（低）
- **人员指派**：支持指派多个处理人员
- **评论系统**：富文本评论，支持图片和附件
- **数据导入**：支持Excel和数据库导入

### AI对话功能
- **智能对话**：基于Qwen3-Code模型的对话系统
- **工具调用**：
  - 三方对话工具
  - 提示词获取工具
  - 文档召回工具
  - BadCase原因分析
- **动态工具调度**：支持动态调用MCP工具

## 技术栈

- **后端**：Flask + SQLAlchemy + Flask-Login
- **数据库**：MySQL
- **前端**：Bootstrap 5 + jQuery
- **邮件**：Flask-Mail
- **数据处理**：pandas + openpyxl

## 安装和运行

### 1. 环境准备
```bash
# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或 .venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量
创建 `.env` 文件：
```env
SECRET_KEY=your-secret-key-here
DATABASE_URL=mysql+pymysql://username:password@host:port/database
MAIL_SERVER=smtp.qq.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-email@qq.com
MAIL_PASSWORD=your-email-password
```

### 3. 数据库初始化
```bash
python app.py
```
程序会自动创建数据库表结构。

### 4. 运行应用
```bash
python app.py
```
访问 http://localhost:5000

## 使用说明

### 用户注册和登录
1. 访问注册页面，输入邮箱
2. 点击"发送验证码"获取邮箱验证码
3. 输入验证码完成注册
4. 使用邮箱和密码登录

### 项目管理
1. 登录后创建新项目
2. 作为项目管理员，可以邀请其他用户
3. 分配协作者或管理员权限

### BadCase工作流
1. 创建BadCase，设置优先级
2. 发布BadCase进入待处理状态
3. 指派处理人员
4. 处理完成后标记为已处理
5. 添加评论后标记为已解决

### AI对话
1. 点击导航栏"AI对话"
2. 与AI助手进行对话
3. 使用工具按钮调用特定功能
4. 分析BadCase原因和解决方案

## 数据库结构

### 主要表
- `user`：用户信息
- `project`：项目信息
- `project_permission`：项目权限
- `badcase`：BadCase信息
- `comment`：评论信息
- `prompt_template`：提示词模板

### BadCase状态

- `pending`：待处理
- `resolved`：已处理
- `hold`：hold
- `reopen`：重新打开
- `close`：已解决

## 开发说明

### 权限控制
- 使用 `has_project_permission()` 函数检查用户权限
- 项目管理员拥有所有权限
- 协作者可以操作BadCase但不能管理项目成员

### 邮件配置
- 默认使用QQ邮箱SMTP
- 支持自定义邮件服务器配置
- 验证码有效期10分钟

### 扩展功能
- 支持添加更多AI工具
- 可以集成真实的Qwen3-Code模型
- 支持更复杂的权限控制

## 许可证

MIT License 