# BadCaseDoctor Go后端部署指南

## 前置要求

- Docker和Docker Compose已安装
- 至少2GB可用内存
- 5GB可用磁盘空间

## 快速启动

1. 克隆项目
```bash
git clone <repository-url>
cd BadCaseDoctor
```

2. 配置环境变量
编辑 `backend-go/.env` 文件，设置必要的环境变量：
```env
DATABASE_URL=badcasedoctor:password@tcp(mysql:3306)/badcasedoctor?charset=utf8mb4&parseTime=True&loc=Local
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=
JWT_SECRET=your-jwt-secret-key-here
ENVIRONMENT=production
PORT=8000
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
FROM_EMAIL=your-email@gmail.com
```

3. 启动服务
```bash
docker-compose up -d
```

4. 检查服务状态
```bash
docker-compose ps
```

5. 查看日志
```bash
docker-compose logs -f backend
```

## 服务说明

### MySQL数据库
- 端口：3306
- 数据库名：badcasedoctor
- 用户名：badcasedoctor
- 密码：password

### Redis缓存
- 端口：6379
- 无密码保护（生产环境请设置密码）

### Go后端服务
- 端口：8000
- 健康检查：http://localhost:8000/health

## 停止服务

```bash
docker-compose down
```

## 清理数据

```bash
docker-compose down -v
```

## 重新构建

```bash
docker-compose up -d --build
```

## 生产环境注意事项

1. 修改所有默认密码
2. 设置强JWT密钥
3. 配置HTTPS
4. 启用Redis密码
5. 配置防火墙规则
6. 定期备份数据库
7. 监控日志和性能

## 故障排查

### 数据库连接失败
- 检查MySQL容器是否正常运行
- 验证数据库连接字符串
- 查看MySQL日志：`docker-compose logs mysql`

### Redis连接失败
- 检查Redis容器是否正常运行
- 验证Redis配置
- 查看Redis日志：`docker-compose logs redis`

### 服务无法启动
- 查看服务日志：`docker-compose logs backend`
- 检查端口占用
- 验证环境变量配置