# SmartDiet 后端启动文档

## 项目简介

SmartDiet 后端是一个基于 FastAPI 的异步 Web 服务，提供用户管理、食物识别、智能聊天等功能。使用 PostgreSQL 数据库，支持 Docker 容器化部署。

用户上传的图片存储在 MinIO 对象存储中，而不是应用容器本地磁盘。上传接口返回的对象 URL 会直接供前端展示和视觉模型识别使用。

认证同时支持微信小程序登录和网页账号密码登录：网页端可调用 `POST /api/v1/users/web/register` 注册，随后调用 `POST /api/v1/users/web/login` 登录。账号为 3–32 位字母、数字、`_`、`.` 或 `-`；密码至少 8 位，后端仅保存 bcrypt 哈希值。

## 前置条件

### Docker 方式（推荐）
- Docker 20.10+
- Docker Compose 2.0+

### 手动方式
- Python 3.10+
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
   
   # JWT 密钥（生产环境请修改）
   JWT_SECRET=your-jwt-secret

   # MinIO（Docker Compose 默认已提供）
   MINIO_ENDPOINT=minio:9000
   MINIO_ACCESS_KEY=minioadmin
   MINIO_SECRET_KEY=minioadmin
   MINIO_BUCKET=smartdiet
   MINIO_SECURE=false
   # 必须是客户端与视觉模型均可访问的对象存储公网地址
   MINIO_PUBLIC_URL=https://minio.example.com
   ```

3. **启动服务**
   ```bash
   docker-compose up -d
   ```

4. **验证服务**
   
   访问健康检查接口：
   ```bash
   curl http://localhost:8000/health
   ```
   
   预期响应：
   ```json
   {"status": "ok"}
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
| `MINIO_PUBLIC_URL` | 返回给前端和视觉模型的对象访问根地址 | `http://localhost:9000` |
| `MINIO_BUCKET` | 图片存储 Bucket 名称 | `smartdiet` |

### 数据库配置

Docker Compose 默认配置：
- 用户名：`smartdiet`
- 密码：`smartdiet`
- 数据库：`smartdiet`
- 端口：`5432`

MinIO 默认开放 S3 API `9000` 端口和管理控制台 `9001` 端口。服务启动时会自动创建 Bucket 并配置对象匿名只读，以保持原 `/uploads` 静态资源的公开读取行为；生产环境请通过 HTTPS 域名设置 `MINIO_PUBLIC_URL`。

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
