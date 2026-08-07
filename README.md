# LLM Chat

基于 Flask 的多用户 AI 对话 Web 应用，支持多种 LLM Provider 和数据库后端，可一键部署到 Railway。

## 特性

- **多 Provider 兼容**：通过 OpenAI 兼容协议接入任意 LLM（MiniMax、DeepSeek、Qwen、Moonshot、OpenAI、Ollama 等），通过环境变量切换
- **多数据库支持**：同时支持 MySQL 和 PostgreSQL，通过 `DB_TYPE` 或 `DATABASE_URL` 切换
- **流式响应**：基于 SSE 的实时输出，含工具调用状态展示
- **会话管理**：历史会话持久化，支持置顶、重命名、删除
- **思考过程展示**：折叠式的 `<think>` 块展示推理过程
- **每会话模型记录**：切换全局模型后，老会话仍按创建时的模型回复
- **用户认证**：基于 Cookie 的服务端会话（`login_sessions` 表）
- **角色权限**：内置 `root` / `admin` / `user` 三级角色
- **CSRF / 限流**：内置 Flask-Limiter 与 CSRF 保护
- **深色模式**：跟随系统设置

## 技术栈

| 类别 | 选型 |
|------|------|
| Web 框架 | Flask 3.1 |
| Agent / LLM | agno 2.8+ |
| 数据库 | MySQL（PyMySQL）/ PostgreSQL（psycopg2） |
| 部署 | Gunicorn + Railway / Docker |
| 包管理 | uv |

## 快速开始（本地开发）

### 1. 环境要求

- Python ≥ 3.12
- [uv](https://docs.astral.sh/uv/)（推荐）或 pip
- MySQL ≥ 5.7 或 PostgreSQL ≥ 13

### 2. 安装依赖

```bash
uv sync
```

### 3. 配置环境变量

```bash
cp .env_example .env
```

最少需要配置：

```env
# LLM Provider
LLM_API_BASE=https://api.minimax.chat/v1
LLM_API_KEY=your-api-key
LLM_MODEL=MiniMax-M3

# 数据库（任选其一）
# 方式 A：分别指定
DB_TYPE=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=appuser
DB_PASSWORD=your-password
DB_NAME=llm_chat

# 方式 B：使用连接字符串（覆盖上面所有 DB_* 配置）
# DATABASE_URL=postgresql://user:pwd@host:5432/dbname
```

### 4. 启动

```bash
# 开发模式（自动重载）
uv run python wsgi.py

# 生产模式（带 preload 避免多 worker 并发建表）
gunicorn --preload -w 4 -b 0.0.0.0:8000 wsgi:app
```

首次启动会自动建表（`users`、`chat_sessions`、`login_sessions`）。

打开 http://127.0.0.1:5000 注册账号登录。

## LLM Provider 配置

改 `LLM_API_BASE` / `LLM_MODEL` 即可切换（兼容所有 OpenAI 兼容端点）：

| Provider | `LLM_API_BASE` | `LLM_MODEL` 示例 |
|----------|----------------|------------------|
| MiniMax | `https://api.minimax.chat/v1` | `MiniMax-M3` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 阿里百炼 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| Ollama | `http://localhost:11434/v1` | `llama3.2` |

## Railway 一键部署（推荐）

1. 把代码推到 GitHub
2. https://railway.app → **New Project** → **Deploy from GitHub repo**
3. 同项目内 **+ New** → **Database** → **PostgreSQL**
4. web service → **Variables** 添加：
   | 变量 | 值 |
   |------|----|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
   | `SECRET_KEY` | `python -c "import secrets;print(secrets.token_urlsafe(32))"` |
   | `LLM_API_BASE` | 如 `https://api.minimax.chat/v1` |
   | `LLM_API_KEY` | 你的 API Key |
   | `LLM_MODEL` | 模型名 |
   | `APP_ENV` | `prod` |
5. Settings → Networking → **Generate Domain**，自动 HTTPS

后续 `git push` 会**自动触发 redeploy**。

## 创建 root 账号

注册接口只能创建 `user` 角色。首个 root 通过 SQL 升级：

1. 通过 `/register` 注册一个普通账号（如 `admin`）
2. Railway Postgres → Data → Query：
   ```sql
   UPDATE users SET role = 'root' WHERE name = 'admin';
   ```
3. 重新登录 → 即可进入用户管理页

## 目录结构

```
.
├── app/
│   ├── __init__.py          # Flask 工厂 + 自动建表 + 并发锁
│   ├── config.py            # 环境变量（含 DATABASE_URL 解析）
│   ├── csrf.py              # CSRF 校验
│   ├── session.py           # 服务端会话
│   ├── extensions.py        # flask-limiter 实例
│   ├── db/                  # 数据库抽象层
│   │   ├── base.py          # DatabaseEngine 抽象基类
│   │   ├── mysql.py         # MySQL 实现
│   │   ├── postgres.py      # PostgreSQL 实现（含 BOOLEAN 取反）
│   │   └── __init__.py      # 引擎注册
│   ├── blueprints/
│   │   ├── pages.py         # 页面路由（登录/注册/用户管理）
│   │   ├── auth.py          # 注册/登录/登出 API
│   │   ├── users.py         # 用户管理 API
│   │   ├── chat.py          # AI 对话（含 SSE 流式）
│   │   ├── chat_tools.py    # Agent 工具函数
│   │   └── db_check.py      # DB 健康检查
│   └── templates/           # Jinja2 模板
├── wsgi.py                  # 生产入口（gunicorn wsgi:app）
├── main.py                  # 脚手架入口
├── Procfile                 # Railway 启动命令
├── pyproject.toml
├── uv.lock
├── .env_example
└── TOOLS_AND_DEPLOY.md      # 详细部署文档
```

## 数据库

通过环境变量切换：

```env
DB_TYPE=mysql            # 默认
DB_TYPE=postgres
# 或直接用 DATABASE_URL 覆盖（自动识别为 postgres）
DATABASE_URL=postgresql://user:pwd@host:5432/dbname
```

### 关键表

| 表 | 说明 |
|----|------|
| `users` | 用户账号（`role` 字段控制权限） |
| `chat_sessions` | 对话会话（`messages` JSON + `model` 字段） |
| `login_sessions` | 服务端会话（用于 Cookie 验证） |

### 关键特性

- **自动建表**：首次启动时 `ensure_auth_schema()` 幂等创建
- **advisory lock**：`pg_advisory_lock` / MySQL `GET_LOCK` 防止多 worker 并发
- **`model` 字段迁移**：启动时检查并自动 `ALTER TABLE ADD COLUMN`

## 角色权限

| 角色 | 权限 |
|------|------|
| `root` | 所有权限（含管理其他 root / admin） |
| `admin` | 用户管理 + AI 对话（不能创建/降级 root） |
| `user` | 仅 AI 对话 |

权限边界实现见 `app/blueprints/pages.py:_can_manage` 等函数。

## 安全

- ✅ `werkzeug.security` 哈希密码（pbkdf2:sha256）
- ✅ 服务端会话存 DB，Cookie 只存 sid
- ✅ CSRF token 校验所有写操作
- ✅ 注册限流 5/小时，登录限流 10/分钟
- ⚠️ 生产环境限流用 Redis（当前 memory:// 单进程内有效）

## 许可

MIT