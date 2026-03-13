# 邮件配置说明

## 问题
验证码发送功能失败，需要配置邮件服务器。

## 解决方案

### 1. 创建 .env 文件
在项目根目录创建 `.env` 文件，内容如下：

```env
# 数据库配置
DATABASE_URL=mysql+pymysql://root:hx123456@117.72.33.38:33106/bad_case

# 邮件配置
MAIL_SERVER=smtp.qq.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-email@qq.com
MAIL_PASSWORD=your-email-password
MAIL_DEFAULT_SENDER=your-email@qq.com

# 应用密钥
SECRET_KEY=your-secret-key-here
```

### 2. 邮件服务器配置

#### QQ邮箱配置
- MAIL_SERVER: smtp.qq.com
- MAIL_PORT: 587
- MAIL_USE_TLS: true
- MAIL_USERNAME: 你的QQ邮箱地址
- MAIL_PASSWORD: QQ邮箱的授权码（不是登录密码）
- MAIL_DEFAULT_SENDER: 你的QQ邮箱地址

#### Gmail配置
- MAIL_SERVER: smtp.gmail.com
- MAIL_PORT: 587
- MAIL_USE_TLS: true
- MAIL_USERNAME: 你的Gmail地址
- MAIL_PASSWORD: Gmail的应用专用密码
- MAIL_DEFAULT_SENDER: 你的Gmail地址

#### 163邮箱配置
- MAIL_SERVER: smtp.163.com
- MAIL_PORT: 587
- MAIL_USE_TLS: true
- MAIL_USERNAME: 你的163邮箱地址
- MAIL_PASSWORD: 163邮箱的授权码
- MAIL_DEFAULT_SENDER: 你的163邮箱地址

### 3. 获取授权码

#### QQ邮箱授权码获取步骤：
1. 登录QQ邮箱
2. 点击"设置" -> "账户"
3. 找到"POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务"
4. 开启"POP3/SMTP服务"
5. 按照提示获取授权码

#### Gmail应用专用密码获取步骤：
1. 开启两步验证
2. 生成应用专用密码
3. 使用应用专用密码而不是登录密码

### 4. 测试邮件发送
配置完成后，重启应用即可正常使用验证码发送功能。

### 注意事项
- 不要将真实的邮箱密码提交到代码仓库
- 使用授权码而不是登录密码
- 确保邮箱开启了SMTP服务 