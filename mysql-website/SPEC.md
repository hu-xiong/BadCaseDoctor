# MySQL 官网项目规范

## 1. 项目概述

### 项目名称
MySQL Website Clone

### 项目类型
企业级官方网站（响应式 + 桌面端入口）

### 核心功能
完整仿 MySQL 官网，包含首页、下载、文档、社区等核心模块。BadCaseDoctor 桌面端挂载下载链接作为入口。

### 技术栈
- **前端**: Vue 3 + TypeScript + Vite
- **后端**: Go (Gin 框架)
- **数据库**: MySQL (独立实例)
- **UI**: Element Plus

### 项目路径
`c:\Users\h2629\PycharmProjects\PythonProject\BadCaseDoctor\mysql-website`

---

## 2. 页面结构

| 页面 | 路由 | 说明 |
|------|------|------|
| 首页 | `/` | 主页面，含导航、Hero、特性展示 |
| 下载 | `/downloads` | MySQL 各版本下载 |
| 文档 | `/docs` | 文档中心 |
| 社区 | `/community` | 论坛/帖子 |
| 新闻 | `/news` | 新闻动态 |
| 登录 | `/login` | 用户登录 |
| 注册 | `/register` | 用户注册 |

---

## 3. 后端 API

### 3.1 认证接口
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/register` | 用户注册 |
| POST | `/api/v1/auth/login` | 用户登录 |
| POST | `/api/v1/auth/logout` | 登出 |
| GET | `/api/v1/auth/me` | 获取当前用户 |

### 3.2 下载接口
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/downloads` | 下载列表 |
| GET | `/api/v1/downloads/:id` | 下载详情 |
| POST | `/api/v1/downloads/:id/record` | 记录下载 |

### 3.3 文档接口
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/docs/categories` | 文档分类 |
| GET | `/api/v1/docs/pages` | 文档列表 |
| GET | `/api/v1/docs/pages/:id` | 文档详情 |

### 3.4 社区接口
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/community/posts` | 帖子列表 |
| POST | `/api/v1/community/posts` | 创建帖子 |
| GET | `/api/v1/community/posts/:id` | 帖子详情 |
| POST | `/api/v1/community/posts/:id/comments` | 发表评论 |

### 3.5 新闻接口
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/news` | 新闻列表 |
| GET | `/api/v1/news/:id` | 新闻详情 |

---

## 4. 数据库表

### users
```sql
CREATE TABLE users (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    username VARCHAR(100) NOT NULL,
    avatar VARCHAR(500),
    status TINYINT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### downloads
```sql
CREATE TABLE downloads (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    version VARCHAR(50) NOT NULL,
    edition VARCHAR(50) NOT NULL,
    os VARCHAR(50) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_size BIGINT,
    sha256 VARCHAR(64),
    description TEXT,
    download_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### download_history
```sql
CREATE TABLE download_history (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT,
    download_id BIGINT,
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (download_id) REFERENCES downloads(id)
);
```

### doc_categories
```sql
CREATE TABLE doc_categories (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    parent_id BIGINT,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### docs
```sql
CREATE TABLE docs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    category_id BIGINT,
    title VARCHAR(255) NOT NULL,
    content TEXT,
    slug VARCHAR(255) UNIQUE,
    status TINYINT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### posts
```sql
CREATE TABLE posts (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT,
    title VARCHAR(255) NOT NULL,
    content TEXT,
    category VARCHAR(50),
    view_count INT DEFAULT 0,
    like_count INT DEFAULT 0,
    status TINYINT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### comments
```sql
CREATE TABLE comments (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    post_id BIGINT,
    user_id BIGINT,
    content TEXT NOT NULL,
    parent_id BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES posts(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### news
```sql
CREATE TABLE news (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    content TEXT,
    summary VARCHAR(500),
    image_url VARCHAR(500),
    status TINYINT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 5. 项目结构

```
mysql-website/
├── backend/                 # Go 后端
│   ├── main.go
│   ├── go.mod
│   ├── config/
│   │   └── config.go
│   ├── handlers/
│   │   ├── auth.go
│   │   ├── downloads.go
│   │   ├── docs.go
│   │   ├── community.go
│   │   └── news.go
│   ├── models/
│   │   └── models.go
│   ├── middleware/
│   │   └── auth.go
│   ├── routes/
│   │   └── routes.go
│   ├── migrations/
│   │   └── init.sql
│   └── config.yaml
│
└── frontend/                # Vue3 前端
    ├── src/
    │   ├── views/
    │   │   ├── Home.vue
    │   │   ├── Downloads.vue
    │   │   ├── Docs.vue
    │   │   ├── Community.vue
    │   │   ├── News.vue
    │   │   ├── Login.vue
    │   │   └── Register.vue
    │   ├── components/
    │   │   ├── Navbar.vue
    │   │   ├── Footer.vue
    │   │   ├── Hero.vue
    │   │   └── ...
    │   ├── router/
    │   │   └── index.ts
    │   ├── stores/
    │   │   └── user.ts
    │   ├── api/
    │   │   └── index.ts
    │   ├── App.vue
    │   └── main.ts
    ├── index.html
    ├── vite.config.ts
    ├── tsconfig.json
    └── package.json
```

---

## 6. 启动方式

### 后端
```bash
cd backend
go mod tidy
go run main.go
# 服务运行在 http://localhost:8080
```

### 前端
```bash
cd frontend
npm install
npm run dev
# 服务运行在 http://localhost:5173
```

---

## 7. 设计规范

### 颜色主题（MySQL 风格）
- 主色: `#00758F` (MySQL Blue)
- 次色: `#00667F`
- 强调色: `#F29111` (MySQL Orange)
- 背景色: `#FFFFFF`
- 文字色: `#333333`
- 辅助色: `#F5F5F5`

### 字体
- 主字体: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto
- 标题: 600-700 weight
- 正文: 400-500 weight

---

## 8. 验收标准

- [ ] 首页完整，包含所有区块
- [ ] 下载页可选择版本和操作系统
- [ ] 文档页左侧导航正常
- [ ] 社区帖列表和详情页正常
- [ ] 用户注册/登录功能正常
- [ ] API 响应正常
- [ ] 响应式布局正常
- [ ] BadCaseDoctor 可挂载访问
