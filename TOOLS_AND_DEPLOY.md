# 命令行工具与部署指南

> 项目：`web_test1`（Flask + MySQL + uv）
> 适用环境：WSL2 / Ubuntu 24.04 / Python 3.12 / MySQL 8.0

本文档分四章：

1. **curl** 常用命令速查
2. **httpie** 常用命令速查
3. 本项目 6 个接口的 curl / httpie 实战对照
4. 部署指南（本地开发 + gunicorn + systemd 生产方案）

---

## 第一章 curl 常用命令

### 1.1 基础语法

```bash
curl [选项] URL [URL...]
```

支持多个 URL；URL 中可用 `{}` 与 `[]` 做批量展开：

```bash
curl http://x.com/users/{1,2,3}.json      # → 1.json, 2.json, 3.json
curl http://x.com/users[1-5].json        # → 1.json ~ 5.json
```

> ⚠️ **zsh 坑**：URL 含 `?` 必须用单引号包，否则 `?` 被当通配符：
> `curl 'http://127.0.0.1:5000/api/user?id=2'`
>
> zsh 下 `[]` 也会被吃，需要 `setopt -s nomatch` 或加引号。

### 1.2 请求方法 `-X`

```bash
curl -X GET    URL
curl -X POST   URL
curl -X PUT    URL
curl -X PATCH  URL
curl -X DELETE URL
curl -X HEAD   URL    # 只看响应头
```

`GET` / `HEAD` 可省略 `-X`；`POST` / `PUT` / `PATCH` / `DELETE` 必须显式指定，或通过 `-d` / `-F` 隐式触发。

### 1.3 请求头与认证

```bash
# 自定义请求头
curl -H "Content-Type: application/json" URL
curl -H "Authorization: Bearer eyJhbGciOi..." URL
curl -H "X-Request-Id: 123" URL              # 多个 -H 可叠加

# User-Agent
curl -A "MyApp/1.0" URL

# Cookie
curl -b "session=abc" URL                    # 直接传字符串
curl -b cookies.txt URL                      # 从文件读

# Basic Auth / Digest
curl -u user:pass URL                        # Basic
curl --digest -u user:pass URL               # Digest

# OAuth2 Bearer
curl --oauth2-bearer "ey..." URL
```

### 1.4 请求体

```bash
# application/x-www-form-urlencoded（默认）
curl -d "name=小刚&age=22" URL

# JSON（需手动指定 Content-Type）
curl -X POST URL -H "Content-Type: application/json" -d '{"name":"小刚","age":22}'

# JSON（curl 7.82+，自动加 Content-Type）
curl --json '{"name":"小刚","age":22}' URL

# 从文件读 body
curl -d @body.json URL
curl --data-binary @body.json URL            # 原样发，不处理 @ 前缀

# URL 编码字段
curl --data-urlencode "q=hello world" URL

# multipart/form-data（文件上传）
curl -F "file=@a.png" URL
curl -F "file=@a.txt;type=text/plain" URL    # 指定 MIME
curl -F "img=@a.png" -F "name=小刚" URL      # 多个字段叠加

# PUT 上传整个文件
curl -T upload.tar.gz URL
```

### 1.5 响应输出控制

```bash
# 保存到文件
curl -o response.json URL
curl -O URL                                  # 文件名取 URL 末尾

# 静默（无进度条、错误信息）
curl -s URL

# 显示响应头 + body
curl -i URL

# 只看响应头（等价 -X HEAD，但支持 GET 路径）
curl -I URL

# 详细调试（看请求 / 响应全过程，含 TLS 握手）
curl -v URL

# 自定义输出格式
curl -w "HTTP %{http_code}\n耗时 %{time_total}s\n" URL
```

`curl -w` 常用占位符：

| 占位符 | 含义 |
|---|---|
| `%{http_code}` | HTTP 状态码 |
| `%{time_total}` | 总耗时（秒） |
| `%{time_namelookup}` | DNS 解析耗时 |
| `%{time_connect}` | TCP 建连耗时 |
| `%{size_download}` | 下载字节数 |
| `%{speed_download}` | 下载速度（bytes/s） |
| `%{url_effective}` | 最终请求 URL（重定后） |
| `%{ssl_verify_result}` | 0 = TLS 校验通过 |

### 1.6 错误处理与重试

```bash
# HTTP 错误时返回非零退出码（脚本里必加）
curl -f URL
curl -fsSL URL          # 经典四连：fail + silent + show-error + follow

# 静默模式下仍显示错误
curl -sS URL

# 失败重试
curl --retry 3 --retry-delay 2 URL

# 跟随重定向
curl -L URL
curl --max-redirs 5 -L URL
```

### 1.7 调试与抓包

```bash
# 详细：看请求行 + 响应行 + 头 + TLS
curl -v URL

# 全量十六进制抓包，存到 dump.txt
curl --trace-ascii dump.txt URL

# 自动 Accept-Encoding: gzip，响应自动解压
curl --compressed URL
```

---

## 第二章 httpie 常用命令

### 2.1 安装

```bash
sudo apt install -y httpie
```

装完命令名是 `http`（不是 `httpie`）。

### 2.2 语法核心

| 语法 | 用途 |
|---|---|
| `key==value` | **查询参数**（URL Query String，两个等号） |
| `key=value` | **请求体字段**（JSON body 或 form 字段） |
| `header:value` | 自定义请求头 |

```bash
http GET  http://x.com/users page==2 sort==name
http POST http://x.com/users name=小刚 age=22 city=广州
http GET  http://x.com/items Authorization:'Bearer ey...'
```

### 2.3 请求方法 / 体 / 头

```bash
# 方法可省略：http 默认按是否有 body 自动选 GET / POST
http URL                           # GET
http URL key==value                # GET 带查询参数
http URL key=value                  # POST（自动 JSON）
http POST URL key=value             # 显式 POST
http PUT URL key=value
http PATCH URL key=value
http DELETE URL

# 切换表单模式（multipart/form-data）
http --form POST URL name=小刚 avatar=@photo.png

# 指定 Content-Type
http POST URL Content-Type:application/x-www-form-urlencoded name=小刚

# 文件上传
http POST URL file@/path/to/a.txt
http POST URL file@~/data.json
```

### 2.4 非交互环境：`--ignore-stdin`

当 stdin **不是 tty**（如 CI、容器、某些 IDE 终端），httpie 会尝试从 stdin 读取请求体，
与命令行 `key=value` 冲突：

```
error: Request body (from stdin, --raw or a file) and request data (key=value)
cannot be mixed. Pass --ignore-stdin to let key/value take priority.
```

修法：

```bash
http --ignore-stdin POST URL name=小刚
http --ignore-stdin GET URL id==2
```

### 2.5 调试与响应输出

```bash
# 详细：打印请求 / 响应头 + body
http -v URL

# 自定义打印哪些段（H=请求头 h=响应头 B=响应 body b=请求 body）
http --print=hHb URL                # 响应头 + 请求头
http --print=bBb URL                # 响应 body + 请求 body（分隔清楚）

# 输出到文件
http -o response.json URL
http --download -o file.zip URL     # 文件下载模式

# 只看状态码
http --check-status URL             # 4xx/5xx 时非零退出
```

### 2.6 httpie vs curl 速查对照

| 需求 | curl | httpie |
|---|---|---|
| 简单 GET | `curl -s URL` | `http URL` |
| 带查询参数 | `curl -s 'URL?k=v'` | `http URL k==v` |
| POST JSON | `curl -X POST -H "Content-Type: application/json" -d '{...}'` | `http POST k=v k2=v2` |
| 上传文件 | `curl -F file=@a.png` | `http --form file@/path` |
| 看响应头 | `curl -i URL` | `http --print=h URL` |
| 看全过程 | `curl -v URL` | `http -v URL` |
| 自定义输出 | `curl -w "..."` | `http --print=...` |
| 中文显示 | 默认 `\u` 转义 | **直接中文** ✅ |
| 预装 | 几乎所有系统 | 需 apt 装 |

---

## 第三章 本项目 6 个接口的 curl / httpie 对照

> 服务器默认跑在 `http://127.0.0.1:5000`
> zsh 下 URL 含 `?` 务必加单引号

| # | 路由 | 方法 | 用途 |
|---|---|---|---|
| 1 | `/` | `GET` | 健康问候 |
| 2 | `/api/user` | `GET` | 查单个用户（`?id=N`，默认 1）|
| 3 | `/api/db-check` | `GET` | MySQL 连通性 + 版本 |
| 4 | `/api/users` | `GET` | 查全部用户 |
| 5 | `/api/users` | `POST` | 创建用户 |
| 6 | `/api/users/<id>` | `PUT` | 更新指定用户 |
| 7 | `/api/users/<id>` | `DELETE` | 删除指定用户 |

### 1. `GET /`

```bash
# curl
curl -s http://127.0.0.1:5000/
# → 你好，世界！我现在是个后端服务器了！

# httpie
http http://127.0.0.1:5000/
```

### 2. `GET /api/user`（查单个）

```bash
# curl
curl -s http://127.0.0.1:5000/api/user              # 默认 id=1
curl -s 'http://127.0.0.1:5000/api/user?id=2'       # 指定 id=2
curl -s -w "\nHTTP %{http_code}\n" 'http://127.0.0.1:5000/api/user?id=999'  # 不存在 → 404

# httpie
http http://127.0.0.1:5000/api/user                 # 默认 id=1
http http://127.0.0.1:5000/api/user id==2           # 指定 id=2
http --ignore-stdin http://127.0.0.1:5000/api/user id==999
```

### 3. `GET /api/db-check`

```bash
# curl
curl -s http://127.0.0.1:5000/api/db-check
# → {"ok":true,"mysql_version":"8.0.46-...","server_time":"..."}

# httpie（看详细 -v 会打印响应头）
http -v http://127.0.0.1:5000/api/db-check
```

### 4. `GET /api/users`

```bash
# curl
curl -s http://127.0.0.1:5000/api/users

# httpie
http http://127.0.0.1:5000/api/users
```

### 5. `POST /api/users`（创建）

**请求体字段**：`name`（必填，str）、`age`（必填，int）、`city`（必填，str）

```bash
# curl
curl -s -X POST http://127.0.0.1:5000/api/users \
  -H "Content-Type: application/json" \
  -d '{"name":"小刚","age":22,"city":"广州"}'
# → 201 {"id":3,"name":"小刚","age":22,"city":"广州"}

# 缺字段
curl -s -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:5000/api/users \
  -H "Content-Type: application/json" \
  -d '{"name":"缺字段"}'
# → 400 {"error":"required fields: name (str), age (int), city (str)"}

# httpie
http --ignore-stdin POST http://127.0.0.1:5000/api/users name=小刚 age=22 city=广州
http --ignore-stdin POST http://127.0.0.1:5000/api/users name=缺字段
```

### 6. `PUT /api/users/<id>`（更新）

请求体可只传**部分字段**（未提供的不动）；不存在 → 404

```bash
# curl：只改 city
curl -s -X PUT http://127.0.0.1:5000/api/users/3 \
  -H "Content-Type: application/json" \
  -d '{"city":"深圳"}'

# curl：同时改 age + name
curl -s -X PUT http://127.0.0.1:5000/api/users/3 \
  -H "Content-Type: application/json" \
  -d '{"name":"小强","age":25}'

# curl：id 不存在
curl -s -w "\nHTTP %{http_code}\n" -X PUT http://127.0.0.1:5000/api/users/999 \
  -H "Content-Type: application/json" -d '{"city":"不存在"}'
# → 404 {"error":"user not found","id":999}

# httpie
http --ignore-stdin PUT http://127.0.0.1:5000/api/users/3 city=深圳
http --ignore-stdin PUT http://127.0.0.1:5000/api/users/3 name=小强 age=25
```

### 7. `DELETE /api/users/<id>`（删除）

成功 → **204 No Content**（空 body）；不存在 → 404

```bash
# curl
curl -s -X DELETE http://127.0.0.1:5000/api/users/3
curl -s -X DELETE -w "HTTP %{http_code}\n" http://127.0.0.1:5000/api/users/3
curl -s -X DELETE http://127.0.0.1:5000/api/users/999  # → 404

# httpie
http --ignore-stdin DELETE http://127.0.0.1:5000/api/users/3
```

### 完整 CRUD 一气呵成（httpie 版）

```bash
# 1. 查全部
http GET http://127.0.0.1:5000/api/users

# 2. 创建
http --ignore-stdin POST http://127.0.0.1:5000/api/users name=小刚 age=22 city=广州

# 3. 查刚创建的（id 是上面返回的，假设是 3）
http GET http://127.0.0.1:5000/api/user id==3

# 4. 改 city
http --ignore-stdin PUT http://127.0.0.1:5000/api/users/3 city=深圳

# 5. 删除
http --ignore-stdin DELETE http://127.0.0.1:5000/api/users/3

# 6. 验证
http GET http://127.0.0.1:5000/api/users
```

---

## 第四章 部署

### 4.1 当前环境速览

| 组件 | 版本 / 状态 |
|---|---|
| WSL | WSL2 + systemd 已启用 |
| OS | Ubuntu 24.04.3 LTS |
| Python | 3.12.3（`.venv`） |
| MySQL | 8.0.46-0ubuntu0.24.04.3 |
| Flask | 3.1.3 |
| PyMySQL | 1.2.0 |
| python-dotenv | 1.2.2 |
| 包管理 | uv（`uv.lock` 锁定） |
| 工作目录 | `/mnt/d/projects/self/plg/web_pg/web_test1` |

### 4.2 本地开发启动

```bash
# 1. MySQL：确保服务在跑（WSL 重启后会停，需手动起）
sudo systemctl start mysql
sudo systemctl enable mysql   # 开机自启（systemd 已启用时生效）
sudo systemctl status mysql

# 2. 同步 Python 依赖
cd /mnt/d/projects/self/plg/web_pg/web_test1
uv sync

# 3. 确认 .env 存在且数据库已建
cat .env                       # DB_HOST/DB_USER/DB_PASSWORD/DB_NAME
mysql -uappuser -h127.0.0.1 -p'App@123456' web_test1 -e "SELECT * FROM users;"

# 4. 启动 Flask（debug 模式自动重载）
.venv/bin/python app.py
# → * Running on http://127.0.0.1:5000

# 5. 另开终端测一下
curl -s http://127.0.0.1:5000/api/db-check
```

#### 用 nohup 后台跑（不被父终端关闭影响）

```bash
# 必须 < /dev/null 切断 stdin，否则 Flask debug 重启会抢走 stdin
nohup .venv/bin/python app.py > /tmp/flask.log 2>&1 < /dev/null &
tail -f /tmp/flask.log
```

### 4.3 生产部署：gunicorn + systemd

> Flask 自带 `app.run()` 仅供开发用，**生产必须用 WSGI 服务器**。
> 这里选 gunicorn（最稳的 Python WSGI 服务器之一）。

#### a. 安装 gunicorn

```bash
cd /mnt/d/projects/self/plg/web_pg/web_test1
uv add gunicorn
```

装完二进制路径在 `.venv/bin/gunicorn`。

#### b. 试启动确认可用

```bash
# 先停 debug 版的 Flask（如在跑）
pkill -f "app.py"   # 或 kill PID

# 用 gunicorn 启，4 worker，监听 8000
.venv/bin/gunicorn -w 4 -b 0.0.0.0:8000 app:app
# 测一下
curl -s http://127.0.0.1:8000/api/db-check
```

#### c. 写 systemd service 文件

```bash
sudo tee /etc/systemd/system/webtest1.service <<'EOF'
[Unit]
Description=web_test1 Flask + Gunicorn
After=network.target mysql.service
Requires=mysql.service

[Service]
Type=simple
User=chenl
Group=chenl
WorkingDirectory=/mnt/d/projects/self/plg/web_pg/web_test1
EnvironmentFile=/mnt/d/projects/self/plg/web_pg/web_test1/.env
ExecStart=/mnt/d/projects/self/plg/web_pg/web_test1/.venv/bin/gunicorn \
    --workers 4 \
    --bind 127.0.0.1:8000 \
    --access-logfile - \
    --error-logfile - \
    app:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

#### d. 启用 + 启动

```bash
sudo systemctl daemon-reload
sudo systemctl enable webtest1.service     # 开机自启
sudo systemctl start webtest1.service
sudo systemctl status webtest1.service        # 应为 active (running)

# 看日志
sudo journalctl -u webtest1 -f

# 测
curl -s http://127.0.0.1:8000/api/db-check
```

#### e. （可选）nginx 反向代理

如果想用 80/443 端口、或者要 TLS 终结、加访问控制，加 nginx：

```nginx
# /etc/nginx/sites-available/webtest1
server {
    listen 80;
    server_name webtest1.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/webtest1 /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

> 注：WSL2 里 nginx 监听 `0.0.0.0:80` 能从 Windows 主机访问，但要外网访问还得做端口转发。

#### f. gunicorn 常用参数

```bash
.venv/bin/gunicorn \
    -w 4 \                        # worker 数，建议 2~4 × CPU 核数
    -b 0.0.0.0:8000 \             # 监听地址
    -k sync \                     # worker class（默认 sync，IO 密集可换 gevent）
    --timeout 30 \                 # 单请求超时（秒）
    --max-requests 1000 \          # 每个 worker 处理 N 请求后重启，防内存泄漏
    --max-requests-jitter 100 \    # 上面那个数加随机抖动，避免同时重启
    --access-logfile - \           # 访问日志 stdout
    --error-logfile - \            # 错误日志 stdout
    app:app                       # 模块:Flask 实例
```

### 4.4 环境变量管理

#### 本项目 `.env`（开发用）

```
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=appuser
DB_PASSWORD=App@123456
DB_NAME=web_test1
FLASK_DEBUG=1
```

#### 生产用 `EnvironmentFile`

上面 systemd unit 里已经写了 `EnvironmentFile=.../.env`，gunicorn 启动时会自动加载。

> ⚠️ `.env` 已加入 `.gitignore`，不会进版本库。
> 生产服务器上需要手动复制 `.env` 过去（或用 Ansible / 密钥管理）。

#### 多环境策略

| 做法 | 适用 |
|---|---|
| 同一 `.env` 通过 `Environment=` 覆盖 | 单机多服务 |
| `.env.development` / `.env.production` 两份 | 简单区分 |
| 用 Vault / AWS Secrets Manager / Doppler | 团队 / 合规 |

### 4.5 MySQL 生产注意事项

#### a. 不要用 root 跑应用

✅ 已建独立账号 `appuser@localhost`，只对 `web_test1` 库有权限。

如需远程访问，再建一个限定来源的账号：

```sql
CREATE USER 'appuser'@'10.0.0.%' IDENTIFIED BY '...';
GRANT ALL ON web_test1.* TO 'appuser'@'10.0.0.%';
FLUSH PRIVILEGES;
```

#### b. 字符集

建库已用 `CHARACTER SET utf8mb4`，表也是 `utf8mb4`。
`utf8mb4` 才能完整支持 emoji 和部分生僻字，**生产默认用它**。

#### c. 备份与还原

```bash
# 备份单个库
mysqldump -uappuser -h127.0.0.1 -p'App@123456' web_test1 > backup_$(date +%F).sql

# 备份全部库
mysqldump -uroot -p'Root@123456' --all-databases > full_backup_$(date +%F).sql

# 加 binlog 位置（用于 point-in-time 恢复）
mysqldump -uappuser -p'...' --single-transaction --master-data=2 web_test1 > backup.sql

# 还原
mysql -uappuser -h127.0.0.1 -p'App@123456' web_test1 < backup_2026-08-05.sql
```

#### d. 远程访问（仅内网）

```bash
sudo sed -i 's/^bind-address.*/bind-address = 0.0.0.0/' /etc/mysql/mysql.conf.d/mysqld.cnf
sudo systemctl restart mysql
```

> ⚠️ 公网开放前必须做：防火墙、SSL 强制、复杂密码、限定 IP。

### 4.6 常见故障排查

#### A. WSL 重启后 MySQL 没起

```bash
sudo systemctl status mysql          # 看是不是 inactive
sudo systemctl start mysql           # 手动起
sudo systemctl enable mysql          # 设自启
```

WSL2 关闭时 systemd 也会停，下次开 WSL 需手动 `start`。
如要 WSL 真正"开机自启"，在 Windows 端写一个计划任务，开机时 `wsl -u root systemctl start mysql`。

#### B. `python3` alternative 指错版本

症状：`apt update` 报 `ModuleNotFoundError: No module named 'apt_pkg'`。

根因：`/usr/bin/python3` 指向了 3.14，但 `python3-apt` 只对 3.12 编译了 `apt_pkg`。
修法：

```bash
sudo update-alternatives --set python3 /usr/bin/python3.12
python3 --version                     # 应回到 3.12.x
sudo apt update                       # 不再报错
```

#### C. MySQL `caching_sha2_password` 鉴权失败

症状：客户端报 `Access denied for user 'root'@'localhost' (using password: NO)`，
即使密码为空也不行。

根因：MySQL 8.0 默认用 `caching_sha2_password`，它要求密码交换，空密码握手失败。

修法 A：用 Debian 维护账号连接后改插件：

```bash
sudo head -20 /etc/mysql/debian.cnf       # 看密码
sudo mysql --defaults-file=/etc/mysql/debian.cnf mysql <<'SQL'
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '新密码';
SQL
```

修法 B：停 MySQL → `--skip-grant-tables` 启动 → 改 plugin → 正常重启。

#### D. 端口 5000 被占

```bash
ss -tlnp | grep :5000          # 看谁占了
lsof -i :5000                  # 另一种查法
```

常见原因：
- 之前的 Flask 没退：`pkill -f "app.py"`
- macOS AirPlay 占了 5000（Linux 没这问题）
- Windows 端 Hyper-V 保留端口（少见）

#### E. Flask debug 卡住 / 不重载

- 改了代码但没生效 → 看是否启了 `debug=True`
- 看日志：`tail -f /tmp/flask.log`
- 强制重启：Ctrl+C + 重新 `python app.py`
- reload 进程死了：用 `nohup ... < /dev/null &` 后台跑，避免 stdin 冲突

#### F. `.env` 没生效

```bash
# 检查文件存在
ls -la .env

# 检查内容
cat .env

# 检查 python-dotenv 加载
.venv/bin/python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('DB_HOST'))"
```

常见错误：路径不对（要在项目根目录跑）、文件名写错（`.env` 不是 `env`）、
`.env` 被 `.gitignore` 后没复制到目标机器。

---

## 附录：项目目录结构

```
web_test1/
├── .env                # 数据库连接等环境变量（不入 git）
├── .gitignore          # git 忽略规则
├── .python-version     # 锁定 Python 版本（3.12）
├── .venv/              # uv 创建的虚拟环境
├── app.py              # Flask 主程序（6 个路由）
├── main.py             # 默认入口（未使用）
├── pyproject.toml      # 项目元数据 + 依赖清单
├── README.md           # （空）
├── TOOLS_AND_DEPLOY.md # 本文档
└── uv.lock             # 依赖版本锁定文件
```

---

## 附录：常用速记

```bash
# 启动
sudo systemctl start mysql && \
  nohup .venv/bin/python app.py > /tmp/flask.log 2>&1 < /dev/null &

# 停止
pkill -f "python app.py"
sudo systemctl stop webtest1    # 生产用

# 健康检查
curl -fsS http://127.0.0.1:5000/api/db-check | grep -q '"ok":true' && echo "OK" || echo "FAIL"

# 看 Flask 日志
tail -f /tmp/flask.log
sudo journalctl -u webtest1 -f

# 进入数据库
mysql -uappuser -h127.0.0.1 -p'App@123456' web_test1

# 备份
mysqldump -uappuser -p'App@123456' web_test1 > "backup_$(date +%F_%H%M%S).sql"
```