# SmartDiet 后端启动文档

## 项目简介

SmartDiet 后端是一个基于 FastAPI 的异步 Web 服务，提供用户管理、饮食记录和食物识别等功能。使用 PostgreSQL 保存业务数据，保留 Redis 基础服务供后续扩展，支持 Docker 容器化部署。

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

   当前应用不依赖 Redis，本地 Python 运行无需启动 Redis。
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

## Redis 基础服务

Compose 保留 Redis 服务及密码认证、AOF 持久化和健康检查，不发布宿主机端口。当前业务未使用 Redis，应用启动不连接或依赖 Redis。

接口频率限制、账号尝试限制、图片数量配额和 AI 并发租约均已移除，待后续重新设计。图片上传的请求体大小、单张大小、张数、像素和格式校验仍然有效，登录鉴权及图片归属校验也保留。

## 依赖安全验证

`requirements.in` 维护直接依赖；`requirements.txt` 是针对 Python 3.12 生成的跨平台完整锁定文件，含安装包哈希。继续使用 `python -m pip install -r requirements.txt` 即可安装锁定版本。JWT 改用 PyJWT，移除了未使用的 `langchain`、`langchain-community` 及其额外依赖。

更新版本后使用 `uv pip compile requirements.in --universal --python-version 3.12 --generate-hashes --output-file requirements.txt` 重新生成锁定文件，再执行 `python -m pip check`、`python -m pip_audit --strict`（审计工具另行安装 `pip-audit==2.10.1`）。仓库 push／PR 检查会运行依赖审计。
