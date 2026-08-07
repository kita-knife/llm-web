# Web Test1

基于 Flask 的多用户 AI 对话 Web 应用，支持多种 LLM Provider 和数据库后端。

## 特性

- **多 Provider 兼容**：通过 OpenAI 兼容协议接入任意 LLM（MiniMax、DeepSeek、Qwen、Moonshot、OpenAI、Ollama 等），通过 `.env` 切换
- **多数据库支持**：同时支持 MySQL 和 PostgreSQL，通过 `DB_TYPE` 切换
- **流式响应**：基于 SSE 的实时输出，含工具调用状态展示
- **会话管理**：历史会话持久化，支持置顶、重命名、删除
- **思考过程展示**：折叠式的 `<think>` 块展示推理过程
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
| 部署 | Gunicorn |
| 包管理 | uv |

## 快速开始

### 1. 环境要求

- Python ≥ 3.12
- uv（推荐）或 pip
- MySQL ≥ 5.7 或 PostgreSQL ≥ 13

### 2. 安装依赖

```bash
uv sync
# 或
pip install -r requirements.txt
```

### 3. 配置环境变量

复制示例配置：

```bash
cp .env_example .env
```

编辑 `.env`，至少配置以下三项：

```env
# LLM Provider（OpenAI 兼容端点）
LLM_API_BASE=https://api.minimax.chat/v1
LLM_API_KEY=your-api-key
LLM_MODEL=MiniMax-M3

# 数据库
DB_TYPE=mysql            # 或 postgres
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=appuser
DB_PASSWORD=your-password
DB_NAME=web_test1
```

### 4. 启动

开发模式：

```bash
python wsgi.py
# 或
uv run python wsgi.py
```

生产模式：

```bash
gunicorn -w 4 -b 0.0.0.0:8000 'wsgi:app'
```

首次启动会自动建表（`users`、`chat_sessions`、`login_sessions`）。

### 5. 访问

打开 http://127.0.0.1:5000 ，注册账号并登录。

## LLM Provider 配置示例

`.env` 中改以下三项即可切换 Provider（兼容所有 OpenAI 兼容端点）：

| Provider | `LLM_API_BASE` | `LLM_MODEL` 示例 |
|----------|----------------|------------------|
| MiniMax | `https://api.minimax.chat/v1` | `MiniMax-M3` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 阿里百炼 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| Ollama | `http://localhost:11434/v1` | `llama3.2` |

## 目录结构

```
.
├── app/
│   ├── __init__.py          # Flask 工厂 + 自动建表
│   ├── config.py            # 环境变量配置
│   ├── csrf.py              # CSRF 校验
│   ├── session.py           # 服务端会话
│   ├── extensions.py        # flask-limiter 实例
│   ├── db/                  # 数据库抽象层
│   │   ├── base.py          # DatabaseEngine 抽象基类
│   │   ├── mysql.py         # MySQL 实现
│   │   ├── postgres.py      # PostgreSQL 实现
│   │   └── __init__.py      # 引擎注册
│   ├── blueprints/
│   │   ├── pages.py         # 页面路由（登录/注册/用户管理）
│   │   ├── auth.py          # 注册/登录/登出 API
│   │   ├── users.py         # 用户管理 API
│   │   ├── chat.py          # AI 对话（含 SSE 流式）
│   │   ├── chat_tools.py    # Agent 工具函数
│   │   └── db_check.py      # DB 健康检查
│   └── templates/           # Jinja2 模板
├── app.py                   # 开发入口
├── main.py                  # 脚手架入口
├── pyproject.toml
├── uv.lock
├── .env_example
└── TOOLS_AND_DEPLOY.md      # 详细部署文档
```

## 数据库

通过 `DB_TYPE` 切换：

```env
DB_TYPE=mysql      # 默认
DB_TYPE=postgres
```

表结构会在首次启动时自动创建（`ensure_auth_schema()` in `app/__init__.py`）。若使用已有数据库，可手动执行建表 SQL 或允许应用自动建表。

### 关键表

| 表 | 说明 |
|----|------|
| `users` | 用户账号（`role` 字段控制权限） |
| `chat_sessions` | 对话会话（含 `messages` JSON、`model` 字段） |
| `login_sessions` | 服务端会话（用于 Cookie 验证） |

## 角色权限

| 角色 | 权限 |
|------|------|
| `root` | 所有权限 |
| `admin` | 用户管理、AI 对话 |
| `user` | AI 对话 |

初始用户需手动创建：

```sql
INSERT INTO users (name, password_hash, role)
VALUES ('admin', '<werkzeug 哈希>', 'admin');
```

或通过 `/register` 注册（默认 `user` 角色），再手动升级。

## 部署

### Railway（一键部署）

1. **推送代码到 GitHub**（需 Personal Access Token，见上方提示）
2. **Railway 控制台**：https://railway.app → New Project → Deploy from GitHub repo
3. **添加 PostgreSQL**：New → Database → PostgreSQL（Railway 自动注入 `DATABASE_URL`）
4. **配置环境变量**：
   | 变量 | 值 |
   |------|----|
   | `SECRET_KEY` | `python -c "import secrets;print(secrets.token_urlsafe(32))"` 生成 |
   | `LLM_API_BASE` | 如 `https://api.minimax.chat/v1` |
   | `LLM_API_KEY` | 你的 API Key |
   | `LLM_MODEL` | 如 `MiniMax-M3` |
5. **自动获得域名**：Railway 分配 `xxx.up.railway.app`，自动 HTTPS

数据库迁移：首次启动时 `ensure_auth_schema()` 自动建表。

### 自托管（VPS + Docker）

详见 [TOOLS_AND_DEPLOY.md](./TOOLS_AND_DEPLOY.md)。

## 开发

```bash
# 安装依赖
uv sync

# 开发模式（自动重载）
FLASK_DEBUG=1 python wsgi.py

# 生产模式
gunicorn -w 4 -b 0.0.0.0:8000 'wsgi:app'
```

## 许可

MIT