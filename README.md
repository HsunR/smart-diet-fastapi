# SmartDiet 后端启动文档

## 项目简介

SmartDiet 后端是一个基于 FastAPI 的异步 Web 服务，提供用户管理、饮食记录和食物识别等功能。使用 PostgreSQL 保存业务数据，使用 FastAPI-Limiter + PyrateLimiter + Redis 管理接口限流，支持 Docker 容器化部署。

用户上传的图片存储在 MinIO 对象存储中，而不是应用容器本地磁盘。对象存储使用私有桶。上传和查询接口向前端返回短时签名 URL；数据库只保存稳定对象引用，视觉模型通过后端读取并转换为 Base64 接收图片。

认证同时支持微信小程序登录和网页账号密码登录：网页端可调用 `POST /api/v1/users/web/register` 注册，随后调用 `POST /api/v1/users/web/login` 登录。账号为 3–32 位字母、数字、`_`、`.` 或 `-`；密码至少 8 位，后端仅保存 bcrypt 哈希值。

微信登录必须同时配置 `WECHAT_APPID` 和 `WECHAT_SECRET`；缺失时拒绝微信登录，不会自动退回模拟登录，网页账号密码登录仍可使用。只有显式设置 `ALLOW_MOCK_LOGIN=true` 且凭证为 `mock` 或以 `mock_` 开头时才允许模拟登录；生产环境必须关闭该开关。

上传入口在写入 MinIO 前校验照片：单张最多 **10 MiB**、最多 **4000 万像素**，实际格式仅允许 JPG、PNG、GIF 和 WebP，拒绝空文件、伪造文件头和损坏照片。对象扩展名和 MIME 类型根据实际内容生成，不信任客户端文件名及类型。批量接口最多 6 张，整批通过校验后才开始存储。

上传请求在 multipart 解析前按实际接收字节计数，单图请求体最多 **11 MiB**，批量最多 **61 MiB**（各预留 1 MiB 表单开销）；缺少或伪造 `Content-Length` 也不能绕过，超限返回 `413`。生产反向代理也应分别设置相同或更小的请求体上限，避免在代理端缓存过大的上传内容。

## 前置条件

### Docker 方式（推荐）
- Docker 20.10+
- Docker Compose 2.0+

### 手动方式
- Python 3.12+
- PostgreSQL 16+
- pip 或 poetry

## 快速启动

### 方式一：Docker Compose（推荐）

1. **进入后端目录**
   ```bash
   cd smartdiet-backend
   ```

2. **配置环境变量**

   复制环境变量模板：
   ```bash
   cp .env.example .env
   ```

   编辑 `.env` 文件，配置以下变量：
   ```env
   # 数据库连接（Docker 内部网络使用 db 作为主机名）
   DATABASE_URL=postgresql+asyncpg://smartdiet:smartdiet@db:5432/smartdiet

   # LLM API 配置
   LLM_BASE_URL=https://api.openai.com/v1
   LLM_MODEL=gpt-4o
   LLM_API_KEY=your-api-key-here

   # Redis 密码（必填，随机生成；Compose 内连接地址自动设为 redis:6379）
   REDIS_PASSWORD=replace-with-a-random-secret

   # JWT 密钥（生产环境请修改）
   JWT_SECRET=your-jwt-secret

   # MinIO（Docker Compose 默认已提供）
   MINIO_ENDPOINT=minio:9000
   MINIO_ACCESS_KEY=minioadmin
   MINIO_SECRET_KEY=minioadmin
   MINIO_BUCKET=smartdiet
   MINIO_SECURE=false
   # 必须是客户端可访问的 S3 API 根地址，不含额外路径
   MINIO_PUBLIC_URL=https://minio.example.com
   ```

3. **启动服务**

   使用 Python 生成随机密码：`python -c "import secrets; print(secrets.token_urlsafe(32))"`，填入 `.env` 的 `REDIS_PASSWORD`。Redis 仅在 Compose 内网访问，不发布宿主机端口。
   ```bash
   docker compose up -d --build
   ```

4. **验证服务**

   访问健康检查接口：
   ```bash
   curl http://localhost:8000/health
   ```

   预期响应：
   ```json
   {"code": 0, "message": "success", "data": {"status": "ok"}}
   ```

5. **查看日志**
   ```bash
   docker-compose logs -f app
   ```

### 方式二：手动启动

1. **安装 Python 依赖**
   ```bash
   cd smartdiet-backend
   pip install -r requirements.txt
   ```

2. **配置 PostgreSQL 数据库**

   确保 PostgreSQL 服务运行，并创建数据库：
   ```sql
   CREATE DATABASE smartdiet;
   CREATE USER smartdiet WITH PASSWORD 'smartdiet';
   GRANT ALL PRIVILEGES ON DATABASE smartdiet TO smartdiet;
   ```

3. **配置环境变量**

   复制并编辑环境变量文件：
   ```bash
   cp .env.example .env
   ```

   修改数据库连接（指向本地 PostgreSQL）：
   ```env
   DATABASE_URL=postgresql+asyncpg://smartdiet:smartdiet@localhost:5432/smartdiet
   ```

4. **运行数据库迁移**

   默认启用限流，本地运行也需要可访问的 Redis，并配置 `REDIS_URL` 与 `REDIS_PASSWORD`。Compose 中 Redis 仅内网可访问；宿主机 Python 请使用独立本地 Redis，或通过受控方式连接开发 Redis。仅本地离线调试可设置 `RATE_LIMIT_ENABLED=false`，此时应用不连接 Redis。
   ```bash
   alembic upgrade head
   ```

5. **启动应用**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

## 配置说明

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `REDIS_URL` | Redis 连接地址，不在 URL 中放密码 | `redis://localhost:6379/0` |
| `REDIS_PASSWORD` | Redis 密码；Compose 必填 | 无 |
| `DATABASE_URL` | 数据库连接字符串 | `postgresql+asyncpg://smartdiet:smartdiet@localhost:5432/smartdiet` |
| `JWT_SECRET` | JWT 签名密钥 | `change-me-in-production` |
| `JWT_ALGORITHM` | JWT 算法 | `HS256` |
| `JWT_EXPIRE_MINUTES` | JWT 过期时间（分钟） | `1440` (24小时) |
| `ALLOW_MOCK_LOGIN` | 允许 mock 开头的本地/H5 登录码，生产必须关闭 | `false` |
| `LLM_BASE_URL` | LLM API 基础 URL | `https://api.openai.com/v1` |
| `LLM_MODEL` | LLM 模型名称 | `gpt-4o` |
| `LLM_API_KEY` | LLM API 密钥 | - |
| `LLM_VISION_MODEL` | 视觉模型（可选） | 默认使用 `LLM_MODEL` |
| `MINIO_ENDPOINT` | 后端连接的 MinIO API 地址 | `localhost:9000` |
| `MINIO_PUBLIC_URL` | 用于签名地址的客户端可访问 S3 API 根地址 | `http://localhost:9000` |
| `MINIO_BUCKET` | 图片存储 Bucket 名称 | `smartdiet` |

### 数据库配置

Docker Compose 默认配置：
- 用户名：`smartdiet`
- 密码：`smartdiet`
- 数据库：`smartdiet`
- 端口：`5432`

MinIO 默认开放 S3 API `9000` 端口和管理控制台 `9001` 端口。服务启动时会自动创建 Bucket，并撤销旧版桶策略，禁止匿名读取。`MINIO_PUBLIC_URL` 必须是客户端可访问的 S3 API 根地址，不含路径前缀；生产环境使用 HTTPS。应用凭据需能创建桶及删除旧桶策略，策略管理权限后续可交给部署步骤。签名 URL 默认 15 分钟过期，可通过 `IMAGE_URL_EXPIRE_SECONDS` 调整为 60–3600 秒；它是临时访问凭证，持有人在到期前可以读取该图片。

## API 文档

启动服务后，访问以下地址查看 API 文档：

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 常用命令

### Docker 相关
```bash
# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 重建并启动
docker-compose up -d --build

# 查看日志
docker-compose logs -f app

# 进入容器
docker-compose exec app bash
```

### 数据库迁移
```bash
# 生成迁移文件
alembic revision --autogenerate -m "描述信息"

# 执行迁移
alembic upgrade head

# 回滚迁移
alembic downgrade -1
```

## 故障排除

### 1. 数据库连接失败
- 检查 PostgreSQL 服务是否运行
- 验证数据库用户名/密码是否正确
- 确认数据库端口是否开放

### 2. 端口被占用
```bash
# 查看端口占用
netstat -ano | findstr :8000

# 终止占用进程
taskkill /PID <进程ID> /F
```

### 3. 依赖安装失败
```bash
# 升级 pip
pip install --upgrade pip

# 使用国内镜像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 4. Alembic 迁移错误
```bash
# 查看当前迁移状态
alembic current

# 查看迁移历史
alembic history --verbose
```

## 开发建议

1. **使用虚拟环境**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Linux/Mac
   source venv/bin/activate
   ```

2. **代码热重载**

   使用 `--reload` 参数启动 uvicorn，代码修改后自动重启。

3. **调试模式**

   在 `.env` 中设置：
   ```env
   DEBUG=True
   ```

## 生产部署

1. **修改默认密码**
   - 修改 `JWT_SECRET`
   - 修改数据库密码
   - 修改 `POSTGRES_PASSWORD`

2. **使用反向代理**

   推荐使用 Nginx 反向代理，配置 HTTPS。

3. **数据库备份**
   ```bash
   docker-compose exec db pg_dump -U smartdiet smartdiet > backup.sql
   ```

## 相关文档

- [FastAPI 官方文档](https://fastapi.tiangolo.com/)
- [SQLAlchemy 异步文档](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Alembic 文档](https://alembic.sqlalchemy.org/)


## 全新数据库与图片权限

当前尚未发布正式版本，迁移历史已合并为 `0001_initial`，仅创建 `users`、`food_records`、`uploaded_images`。不提供旧库升级、旧图片归属回填、chat 表或数据库限流表。应用启动不再用 `create_all` 隐式建表，必须先执行 `alembic upgrade head`。

已有开发库必须重建后再运行新基线，不能直接升级或仅修改 Alembic 版本号。若确认丢弃当前 Compose 项目的全部开发数据（包含 PostgreSQL、MinIO 与 Redis），可执行：

```bash
docker compose down --volumes
docker compose up -d --build
```

网页账号的 `openid` 为空，不再生成假微信身份。记录接口只接收/返回 `imageUrls`；流式识别要求 1–6 张照片的 `imageUrls`，不接受旧的单图字段。独立单图识别接口 `/records/recognize` 仍使用 `imageUrl`。

新照片使用 `users/<用户 UUID>/<随机文件名>` 对象键，并登记所有者。保存、编辑、识别、头像更新与访问地址刷新都会校验所有者。数据库只保存稳定引用，响应生成短时签名。

`POST /api/v1/upload/access` 接收 `{"imageUrls": ["图片引用或过期签名 URL"]}`，返回同顺序的新签名 URL（最多 6 张），需要 Bearer 登录及归属校验。识别仅接收当前用户已上传的图片。闲聊 API、会话服务、模型及本地旧草稿迁移已移除。

## 接口限流

使用 **FastAPI-Limiter 0.2.0 + PyrateLimiter 4.5.1 + Redis**。FastAPI-Limiter 负责请求放行和超限回调，PyrateLimiter 的 `TokenBucket` / `StateBucket` / `RedisStateStore` 负责算法、Lua 原子更新及 TTL。项目仅配置策略、身份和 API 响应，不自行实现限流算法或 Lua 脚本。

默认启用；应用启动连接 Redis 并校验连通性，退出时关闭连接池。Compose 等待 Redis 健康后启动应用。Redis 保留密码认证、AOF 持久化和健康检查，不发布宿主机端口。

| 环境变量 | 默认值 | 规则 |
| --- | --- | --- |
| `RATE_LIMIT_ENABLED` | `true` | 总开关，关闭时不创建 Redis 连接 |
| `RATE_LIMIT_PREFIX` | `smartdiet:ratelimit:v1` | 环境命名空间，不同环境应隔离 |
| `RATE_LIMIT_IP_PER_MINUTE` | `300` | 所有 `/api/v1/` 请求按可信客户端 IP 共享 |
| `RATE_LIMIT_USER_PER_MINUTE` | `120` | 全部已认证接口按用户 ID 共享 |
| `RATE_LIMIT_LOGIN_PER_MINUTE` | `20` | 微信与网页登录按 IP 共享，包含失败及非法请求 |
| `RATE_LIMIT_ACCOUNT_PER_MINUTE` | `10` | 网页登录按小写规范化账号共享，跨 IP 生效，统计全部尝试 |
| `RATE_LIMIT_REGISTER_PER_HOUR` | `5` | 网页注册按 IP 计数，包含失败及非法请求 |
| `RATE_LIMIT_UPLOAD_IMAGES_PER_MINUTE` | `30` | 单张与批量上传按用户共享，按照片张数原子扣减，最小配置 6 |
| `RATE_LIMIT_AI_PER_MINUTE` | `6` | 普通与 SSE 识别按用户共享，每次请求扣 1 次 |

以上数量表示**令牌补充速度**，桶容量等于配置数量。例如 AI 桶最多累积 6 个令牌，以每 10 秒 1 个令牌的速度恢复；这不是“任意滚动一分钟最多 6 次”的严格窗口。批量上传额度不足时整批拒绝，不部分扣减。请求准入后即扣减，后续校验或业务失败不返还，避免通过失败请求绕过限制；不同策略依次执行，后续策略拒绝不会返还前面已消耗的令牌。

每个用户、IP、账号、策略使用独立 Redis 状态，身份通过 HMAC 摘要存储。所有实例须配置相同的前缀、JWT 密钥及阈值。修改环境变量后重启应用；阈值包含在状态键中，修改阈值会建立新桶，应协调多实例配置发布。空闲状态由框架 TTL 自动清理，不保留不断增长的 Python 用户桶缓存。

IP 及登录/注册限流在 JSON/multipart 解析和数据库操作之前执行。用户额度在通过鉴权后扣减；图片额度在验证图片内容和写入 MinIO 前扣减；AI 额度在启动识别及发送 SSE 响应头前扣减。`/health`、文档和 CORS `OPTIONS` 不参与限流。IP 只取 ASGI 客户端地址，应用不直接信任 `X-Forwarded-For`；反向代理部署须在 Uvicorn 配置 `--proxy-headers --forwarded-allow-ips=<可信代理IP>`，并限制外部直接访问后端。

超限返回 HTTP `429`、`Retry-After` 秒数和统一的 `{code, message, data}` 响应；前端普通请求、上传及 H5/小程序 SSE 均显示重试提示，不自动重放请求。CORS 允许浏览器读取 `Retry-After`。Redis 运行时不可用时，所有受保护 API 返回 `503`，不回退到进程内计数，不重试可能已经扣减的写操作；`/health` 仍作为存活检查响应。Redis 启动不可用会阻止应用启动。

已发布的 FastAPI-Limiter 0.2.0 会扫描路由位置，不能直接处理 FastAPI 0.162 的 `_IncludedRouter`；适配层为限流调用提供固定路由视图，并显式按策略确定共享关系，避免路由顺序影响计数。请勿直接套用其主分支文档中尚未发布的中间件/跳过参数示例。

本次提供频率控制，不包含 AI 活跃任务并发上限或持久化每日业务配额。图片上传的请求体大小、单张大小、张数、像素和格式校验、登录鉴权及图片归属校验继续生效。

### 限流验证

测试使用独立 Redis，按随机命名空间隔离和清理，仅删除本次测试的键，不执行 `FLUSHDB`。未设置 `TEST_REDIS_URL` 时跳过 Redis 集成用例，CI 使用 Redis 服务执行完整测试。

```powershell
$env:TEST_REDIS_URL = "redis://localhost:6379/15"
python -m pytest -q
```

覆盖跨实例并发原子性、身份隔离、批量计数、状态过期、登录保护、可信 IP、普通/SSE 共享额度、故障关闭及开关行为。

## 依赖安全验证

`requirements.in` 维护直接依赖；`requirements.txt` 是针对 Python 3.12 生成的跨平台完整锁定文件，含安装包哈希。继续使用 `python -m pip install -r requirements.txt` 即可安装锁定版本。JWT 改用 PyJWT，移除了未使用的 `langchain`、`langchain-community` 及其额外依赖。

更新版本后使用 `uv pip compile requirements.in --universal --python-version 3.12 --generate-hashes --output-file requirements.txt` 重新生成锁定文件，再执行 `python -m pip check`、`python -m pip_audit --strict`（审计工具另行安装 `pip-audit==2.10.1`）。仓库 push／PR 检查会运行依赖审计。
