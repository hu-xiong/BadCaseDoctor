# MySQL Website Backend

Go 后端服务，使用 Gin 框架和 GORM ORM。

## 技术栈

- Go 1.21+
- Gin Web 框架
- GORM (MySQL)
- JWT 认证
- YAML 配置

## 项目结构

```
backend/
├── config/          # 配置模块
│   ├── config.go    # 配置加载
│   └── config.yaml  # 配置文件
├── handlers/       # HTTP 处理器
│   ├── auth.go     # 认证
│   ├── download.go # 下载管理
│   ├── docs.go     # 文档系统
│   ├── community.go # 社区系统
│   └── news.go     # 新闻系统
├── middleware/     # 中间件
│   └── auth.go     # JWT 认证
├── models/         # 数据模型
│   ├── models.go   # 实体定义
│   └── database.go # 数据库连接
├── routes/         # 路由配置
│   └── routes.go   # 路由设置
├── migrations/     # 数据库迁移
│   └── 001_init_schema.sql
├── main.go         # 应用入口
└── go.mod          # Go 模块
```

## 快速开始

### 1. 初始化数据库

```bash
mysql -u root -p < migrations/001_init_schema.sql
```

### 2. 修改配置

编辑 `config/config.yaml`，修改数据库连接信息：

```yaml
database:
  dsn: "root:password@tcp(localhost:3306)/mysql_website?charset=utf8mb4&parseTime=True&loc=Local"
```

### 3. 安装依赖

```bash
cd backend
go mod download
```

### 4. 运行服务

```bash
go run main.go
```

服务将在 `http://localhost:8080` 启动。

## API 接口

### 认证接口

| 方法   | 路径                    | 描述           | 认证 |
|--------|------------------------|----------------|------|
| POST   | /api/v1/auth/register  | 用户注册       | 否   |
| POST   | /api/v1/auth/login     | 用户登录       | 否   |
| POST   | /api/v1/auth/logout    | 用户登出       | 否   |
| GET    | /api/v1/auth/me        | 获取当前用户   | 是   |

### 下载接口

| 方法   | 路径                        | 描述           | 认证 |
|--------|----------------------------|----------------|------|
| GET    | /api/v1/downloads          | 下载列表       | 否   |
| GET    | /api/v1/downloads/:id      | 下载详情       | 否   |
| POST   | /api/v1/downloads/:id/record | 记录下载     | 是   |

### 文档接口

| 方法   | 路径                        | 描述           | 认证 |
|--------|----------------------------|----------------|------|
| GET    | /api/v1/docs/categories    | 文档分类       | 否   |
| GET    | /api/v1/docs/pages          | 文档列表       | 否   |
| GET    | /api/v1/docs/pages/:id      | 文档详情       | 否   |
| GET    | /api/v1/docs/search        | 搜索文档       | 否   |

### 社区接口

| 方法   | 路径                          | 描述           | 认证 |
|--------|------------------------------|----------------|------|
| GET    | /api/v1/community/posts      | 帖子列表       | 否   |
| POST   | /api/v1/community/posts      | 创建帖子       | 是   |
| GET    | /api/v1/community/posts/:id  | 帖子详情       | 否   |
| GET    | /api/v1/community/posts/:id/comments | 评论列表 | 否   |
| POST   | /api/v1/community/posts/:id/comments | 创建评论 | 是   |

### 新闻接口

| 方法   | 路径                | 描述       | 认证 |
|--------|--------------------|------------|------|
| GET    | /api/v1/news       | 新闻列表   | 否   |
| GET    | /api/v1/news/latest | 最新新闻   | 否   |
| GET    | /api/v1/news/:id   | 新闻详情   | 否   |

## API 使用示例

### 注册用户

```bash
curl -X POST http://localhost:8080/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password123","username":"testuser"}'
```

### 登录

```bash
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password123"}'
```

### 获取下载列表

```bash
curl http://localhost:8080/api/v1/downloads
```

### 获取文档分类

```bash
curl http://localhost:8080/api/v1/docs/categories
```

## 配置说明

### config.yaml

```yaml
server:
  port: 8080        # 服务端口
  mode: debug       # Gin 模式: debug, release, test

database:
  dsn: "root:password@tcp(localhost:3306)/mysql_website?charset=utf8mb4&parseTime=True&loc=Local"
  max_idle_conns: 10
  max_open_conns: 100
  conn_max_lifetime: 3600

jwt:
  secret: "your-secret-key"
  expire_hours: 24

app:
  name: "MySQL Official Website"
  version: "1.0.0"
```

## 开发说明

### 运行测试

```bash
go test ./...
```

### 构建

```bash
go build -o mysql-website-backend main.go
```

### 目录结构说明

- `config/` - 配置管理
- `models/` - 数据模型和数据库操作
- `handlers/` - HTTP 请求处理
- `middleware/` - HTTP 中间件（认证、日志等）
- `routes/` - 路由定义
- `migrations/` - SQL 迁移脚本
