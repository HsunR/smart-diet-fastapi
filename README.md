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

## 测试服务器自动部署（GitHub Actions）

项目仅部署 API、PostgreSQL、Redis 和 MinIO。HTTPS、域名和反向代理由维护者自行配置，API 和 MinIO 端口仅绑定服务器本机。旧数据库数据由维护者手动清理，部署流程不执行清库。

后端仓库的 `main` 收到 push（含 PR 合并）后，`.github/workflows/deploy-test.yml` 通过 SSH 登录固定测试服务器，在服务器构建镜像并更新 Docker Compose 服务。实际部署逻辑统一放在 `scripts/deploy-test.sh`，可先在服务器直接运行，验证通过后再交给 Actions；workflow 只负责检出部署脚本、配置 SSH 和调用脚本。测试和依赖审计可按下文说明手动运行。

### 1. 首次准备服务器

服务器需安装 Git、Bash、`flock`（通常由 util-linux 提供）、Docker 和 **Docker Compose 2.20+**，并能访问 GitHub、容器镜像源和 Python 包源。部署用户应有目录写入权限及直接运行 Docker 的权限，非交互 SSH 会话也需能找到这些命令。

先以部署用户将后端仓库克隆到专用目录，例如 `/opt/smartdiet/backend`（该目录应由部署用户持有）：

```bash
git clone git@github.com:HsunR/smart-diet-fastapi.git /opt/smartdiet/backend
cd /opt/smartdiet/backend
cp .env.test.example .env
chmod 600 .env
```

上例使用 SSH 克隆，需给服务器配置只读 GitHub Deploy Key，并通过可信渠道核实、保存 GitHub 的 SSH 主机密钥；公开仓库也可改用 HTTPS 地址克隆。确认以部署用户执行 `git fetch origin main` 不需要交互输入密码或确认主机。该密钥与下文 Actions 登录服务器的密钥用途不同。

编辑服务器 `.env`：

- 分别设置 `POSTGRES_PASSWORD`、`REDIS_PASSWORD`、`JWT_SECRET`、`MINIO_ROOT_PASSWORD`，可运行 `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` 分别生成。数据库密码须使用 URL 安全字符，因为它会拼入数据库连接串。
- 显式设置 `MINIO_PUBLIC_URL` 为客户端实际可访问的 S3 API 根地址，例如 `https://images.hsunr.xyz`，不含路径前缀。此地址由你自行配置的代理提供，Compose 不再自动拼接图片域名。
- 配好代理后，将 `FORWARDED_ALLOW_IPS` 设为 API 容器实际看到的代理源 IP 或 CIDR，多个地址以逗号分隔；默认留空，不信任任何代理头。不要直接信任所有来源。
- `RATE_LIMIT_PREFIX=smartdiet:test:ratelimit:v1` 是 Redis 限流数据的命名空间，不是限流次数。测试和生产共用 Redis 时使用不同前缀，例如生产使用 `smartdiet:prod:ratelimit:v1`；同一环境的多个应用实例使用相同前缀，以共享计数。
- 按需填写模型接口和微信凭据，未配置微信时仍可使用网页账号登录。
- 可调整 `TEST_APP_PORT`、`TEST_MINIO_PORT` 和 `TEST_MINIO_CONSOLE_PORT`。
- 测试镜像构建默认使用清华 PyPI 镜像，下载超时 60 秒、连接重试 5 次；可通过 `.env` 的 `PIP_INDEX_URL`、`PIP_TIMEOUT`、`PIP_RETRIES` 调整。使用官方源时设置 `PIP_INDEX_URL=https://pypi.org/simple`。这些变量通过 Compose build args 传入 Docker 构建，不是应用运行时变量；依赖版本和 SHA256 哈希仍以 `requirements.txt` 为准。

测试配置独立使用 `docker-compose.test.yml`，不与开发 Compose 合并。应用无源码挂载、无热重载，启动时先执行数据库迁移。PostgreSQL、Redis 不发布宿主机端口；API、MinIO API 和控制台仅绑定 `127.0.0.1`。宿主机代理可分别连接 `http://127.0.0.1:8000` 和 `http://127.0.0.1:9002`；如修改了端口变量，使用对应端口。容器内代理不能通过自身的 `127.0.0.1` 访问这些服务，需自行配置其连接网络与端口绑定。

首次部署建议先在服务器手动完成一次，不依赖 GitHub Actions。确认 `.env` 和数据准备完成后，在后端仓库目录运行：

```bash
cd /opt/smartdiet/backend
bash scripts/deploy-test.sh --check
bash scripts/deploy-test.sh
curl --fail http://127.0.0.1:8000/health
```

默认部署当前检出代码，不自动拉取或切换 Git 分支。脚本自动选择对应的镜像标签，校验配置、构建镜像、更新服务并等待健康检查，通过后才记录成功版本。首次构建、基础镜像拉取和迁移可能较慢，先在服务器完成这一步，可直接看到错误，后续 Actions 会复用服务器的 Docker 构建缓存。

如需逐步排查，脚本的核心步骤对应下面这些手动命令。逐条执行，某一步失败就先排查，不要继续下一步：

```bash
cd /opt/smartdiet/backend
export DEPLOY_SHA="$(git rev-parse HEAD)"
docker compose --env-file .env -f docker-compose.test.yml config --quiet
docker compose --env-file .env -f docker-compose.test.yml build app
docker compose --env-file .env -f docker-compose.test.yml up -d --no-build --remove-orphans --wait --wait-timeout 120
curl --fail http://127.0.0.1:8000/health
```

| 命令 | 作用 | 成功表现 |
| --- | --- | --- |
| `config --quiet` | 读取 `.env`，检查 Compose 格式和必填变量，不启动容器 | 无输出，退出码为 0 |
| `build app` | 将当前后端代码和依赖构建为 `DEPLOY_SHA` 对应的镜像，不更新运行中的服务 | 镜像构建完成 |
| `up -d --no-build --remove-orphans --wait --wait-timeout 120` | 使用已构建镜像后台更新服务，移除同项目中已删除的旧服务容器，最多等待 120 秒确认就绪 | 命令成功结束，应用、数据库和 Redis 健康 |
| `curl --fail .../health` | 从服务器本机验证后端响应 | 返回下方 JSON |

```json
{"code":0,"message":"success","data":{"status":"ok"}}
```

`up` 会执行应用原有的 `alembic upgrade head`，不会删除数据卷。以上健康检查验证本机后端，不验证公网域名、证书、微信登录或模型接口；自管代理配置完成后，需另外从客户端访问 API 健康接口和图片签名地址。

若调整了 `TEST_APP_PORT`，对应修改 curl 地址。Compose 默认项目名固定为 `smartdiet-test`；数据保存在该项目的命名卷中。已有测试实例需先核对原项目名、卷名、数据库密码与迁移状态，再设置 `.env` 的 `COMPOSE_PROJECT_NAME` 沿用原项目。不要在现有实例旁启动另一套使用相同端口的项目。修改 `.env` 中的数据库密码不会修改已有数据库用户的密码。

从项目内置代理版本升级时，先在服务器 `.env` 补上 `MINIO_PUBLIC_URL`；旧的 `API_DOMAIN`、`IMAGES_DOMAIN`、`ACME_EMAIL`、`CADDY_PROXY_SUBNET` 和 `CADDY_PROXY_IP` 已不再使用，可删除。`--remove-orphans` 会停止并移除同一 Compose 项目中已从配置移除的旧服务容器，不删除数据卷；原有证书卷及服务器本地证书文件也不会自动删除。自管代理请独立部署，避免作为此 Compose 项目的额外服务被清理。

#### 1.1 部署脚本的运行方式

| 参数 | 行为 |
| --- | --- |
| 无参数 | 使用当前检出代码构建并启动服务，不执行 Git 拉取或切换 |
| `--check` | 仅检查 Compose 配置，不连接 Docker 引擎，不构建、不启动、不执行迁移，不获取部署锁 |
| `--build-only` | 仅构建当前代码的 API 镜像，不更新运行中的服务，也不更新成功部署记录 |
| `--no-build` | 使用当前检出代码对应的已有镜像启动服务；镜像不存在时明确报错 |
| `--sync` | 要求工作区干净，获取并切换到最新 `origin/main`，然后执行指定模式 |
| `--revision <完整 SHA>` | 与 `--sync` 一起使用；远端 `main` 已有更新提交时跳过本次部署，供 Actions 防止旧任务覆盖新版本 |
| `--deploy-dir <仓库根目录>` | 指定操作的后端仓库；本地文件执行默认定位到脚本所在仓库 |
| `--env-file <文件路径>` | 指定环境文件，默认 `.env`；相对路径从后端仓库根目录计算 |
| `--wait-timeout <秒数>` | 等待容器就绪的时间，默认 120 秒；不限制镜像构建耗时 |

`--check`、`--build-only`、`--no-build` 三者互斥；`--check` 不与 `--sync` 同用。可用 `bash scripts/deploy-test.sh --help` 查看帮助。

例如，先构建、排错，之后再启动相同版本：

```bash
bash scripts/deploy-test.sh --build-only
bash scripts/deploy-test.sh --no-build --wait-timeout 300
```

期间如修改了代码，应重新构建。需要手动部署服务器上最新的主分支时执行：

```bash
bash scripts/deploy-test.sh --sync
```

实际构建和部署需要 Linux 或 WSL 环境，并安装 Git、Bash、`flock`、Docker 和 Compose；运行前确认所用 Docker 引擎及 `.env` 指向预期环境。本机测试建议使用独立的 `COMPOSE_PROJECT_NAME` 和空的测试数据卷。Windows Git Bash 安装 Docker CLI 后可先进行不启动服务的检查：

```bash
bash scripts/deploy-test.sh --check
```

脚本默认不会覆盖未提交代码，可用当前工作区进行本地构建、启动测试；此时镜像和成功记录使用 `local-<当前提交前12位>`，日志注明包含未提交修改。没有未提交修改时使用完整提交 SHA。脚本忽略外部继承的 `DEPLOY_SHA`，避免意外部署旧标签。`--sync`（包含 Actions）仍严格拒绝未提交或未跟踪的非忽略文件。测试完成后应提交代码再启用自动部署。

手动运行和 Actions 共用 `.git/smartdiet-test-deploy.lock`，避免同时修改同一套服务；构建成功前不更新容器，失败不写入成功记录。不执行清库或删卷，也不自动配置、检测外部代理。

### 2. 配置 Actions 登录服务器

整个部署涉及两条独立的 SSH 连接：

| 连接方向 | 密钥用途 | 配置位置 |
| --- | --- | --- |
| GitHub Actions → 部署服务器 | Actions 以部署用户身份登录服务器 | GitHub 的 `TEST_SSH_PRIVATE_KEY`，服务器用户的 `~/.ssh/authorized_keys` |
| 部署服务器 → GitHub 仓库 | 服务器执行 `git fetch origin main` | 服务器上的仓库访问密钥、GitHub 仓库的只读 Deploy Key，以及服务器的 `~/.ssh/known_hosts` |

下列步骤配置第一条连接。第二条连接按首次准备服务器部分完成；若使用公开仓库的 HTTPS 地址，则拉取代码不需要 SSH Deploy Key。`TEST_SSH_KNOWN_HOSTS` 保存的是**部署服务器的主机公钥记录**，不是 GitHub 主机密钥，也不是登录用户的 `.pub` 公钥。

#### 2.1 在 Windows 生成部署专用密钥

在本机 PowerShell 执行。下面以服务器 `39.107.28.137`、SSH 端口 `22`、用户 `smart-diet` 为例，按实际情况替换；后续 PowerShell 命令在同一终端执行：

```powershell
$deployHost = '39.107.28.137'
$deployPort = 22
$deployUser = 'smart-diet'
$deployKey = "$env:USERPROFILE\.ssh\smartdiet_actions"

New-Item -ItemType Directory -Force "$env:USERPROFILE\.ssh" | Out-Null
ssh-keygen -t ed25519 -C 'github-actions-smartdiet' -f $deployKey
```

提示输入 `passphrase` 时直接回车两次，不设置口令。当前 workflow 使用 `BatchMode=yes`，没有配置交互式口令解锁。若已经有这个专用密钥文件，直接复用，不要覆盖。

生成的两个文件用途不同：

| 文件 | 用途 |
| --- | --- |
| `~/.ssh/smartdiet_actions` | 私钥，完整内容填入 GitHub `TEST_SSH_PRIVATE_KEY` |
| `~/.ssh/smartdiet_actions.pub` | 公钥，追加到服务器部署用户的 `authorized_keys` |

在 PowerShell 查看公钥：

```powershell
Get-Content "${deployKey}.pub"
```

复制以 `ssh-ed25519` 开头的完整一行。私钥不要放进仓库、`.env`、聊天或截图。

#### 2.2 在服务器授权部署用户

通过云厂商控制台远程终端或已经核实过身份的 SSH 连接登录服务器，切换到部署用户后执行。`whoami` 的结果必须与 `TEST_SERVER_USER` 一致；如果登录的是 root，不要把公钥误加到 root 的目录：

```bash
whoami
mkdir -p ~/.ssh
chmod 700 ~/.ssh
printf '\n' >> ~/.ssh/authorized_keys
cat >> ~/.ssh/authorized_keys <<'EOF'
这里替换成 Windows 上复制的完整公钥一行，以 ssh-ed25519 开头
EOF
chmod 600 ~/.ssh/authorized_keys
```

上面的占位行必须替换为实际公钥。这是追加操作，不覆盖已有密钥。部署用户还需要访问部署目录和运行 Docker 的权限。

#### 2.3 核对服务器身份并获取 known_hosts 记录

在**云厂商控制台的可信远程终端**中读取服务器已有主机公钥的指纹，无需重新生成主机密钥：

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256
```

在 Windows PowerShell 发起登录：

```powershell
ssh -o IdentitiesOnly=yes -o PreferredAuthentications=publickey -i $deployKey -p $deployPort "${deployUser}@${deployHost}"
```

首次连接可能出现：

```text
The authenticity of host '39.107.28.137 (...)' can't be established.
ED25519 key fingerprint is SHA256:...
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

将此处指纹与服务器控制台输出核对，完全一致后输入完整的 `yes`。未确认或取消时出现 `Host key verification failed`，表示连接在服务器身份校验阶段终止，不代表私钥错误。若显示主机密钥已变化，也应先核对是否重装或更换了服务器，再更新相应记录，不要关闭主机校验。

登录成功后执行 `exit` 返回 PowerShell，再验证无需密码和交互确认的登录是否可用：

```powershell
ssh -o BatchMode=yes -o IdentitiesOnly=yes -i $deployKey -p $deployPort "${deployUser}@${deployHost}" whoami
```

预期直接输出部署用户名。随后在服务器的可信控制台生成 GitHub Secret 所需的完整主机公钥记录：

```bash
awk -v server='39.107.28.137' '{print server, $1, $2}' /etc/ssh/ssh_host_ed25519_key.pub
```

输出形如：

```text
39.107.28.137 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA...
```

将完整输出一行填入 `TEST_SSH_KNOWN_HOSTS`，**不要只填 `SHA256:...` 指纹**。如果 `TEST_SERVER_HOST` 填域名，这里的 `server` 也使用相同域名；非标准端口须带方括号和端口，例如：

```bash
awk -v server='[39.107.28.137]:2222' '{print server, $1, $2}' /etc/ssh/ssh_host_ed25519_key.pub
```

也可用 `ssh-keyscan -p 22 服务器地址` 收集记录，但扫描本身不验证主机身份，必须再与可信控制台提供的指纹核对。Windows 本机的 `known_hosts` 和 GitHub Secret 独立，不能只在本机确认 `yes` 而忘记配置 GitHub。

#### 2.4 在 GitHub 创建 Secrets 和 Variables

打开后端仓库 **Settings → Secrets and variables → Actions**。在 **Secrets** 页点击 **New repository secret** 创建两个 Secret；已存在时使用编辑按钮更新。在 **Variables** 页点击 **New repository variable** 添加其余配置：

| 类型 | 名称 | 内容 |
| --- | --- | --- |
| Secret | `TEST_SSH_PRIVATE_KEY` | 完整 SSH 私钥，包含首尾标记与换行 |
| Secret | `TEST_SSH_KNOWN_HOSTS` | 核实过的服务器 `known_hosts` 记录 |
| Variable | `TEST_SERVER_HOST` | 服务器 IP 或域名，例如 `39.107.28.137`，不含用户名、端口或 URL 协议 |
| Variable | `TEST_SERVER_PORT` | SSH 端口，可省略，默认 `22` |
| Variable | `TEST_SERVER_USER` | SSH 部署用户，例如 `smart-diet`，与公钥所在用户一致 |
| Variable | `TEST_DEPLOY_PATH` | 仓库根目录的绝对路径，例如 `/opt/smartdiet/backend` |

复制私钥可在 PowerShell 执行：

```powershell
Get-Content -Raw $deployKey | Set-Clipboard
```

将剪贴板内容直接粘贴到 `TEST_SSH_PRIVATE_KEY` 的 Secret 值，保留完整首尾标记和实际换行，不额外加引号、不转换为 Base64：

```text
-----BEGIN OPENSSH PRIVATE KEY-----
实际私钥内容
-----END OPENSSH PRIVATE KEY-----
```

workflow 强制校验服务器身份，不自动接受未知主机。业务 `.env` 留在服务器，不上传 GitHub。不要把这两个 Secret 添加到 **Variables** 或其他仓库。

#### 2.5 更换服务器时同步更新

服务器 IP、SSH 端口或用户变化时，重新确认 `TEST_SERVER_HOST`、`TEST_SERVER_PORT`、`TEST_SERVER_USER` 和 `TEST_DEPLOY_PATH`。在新服务器给部署用户安装公钥，并重新取得、核实 `TEST_SSH_KNOWN_HOSTS`；只有更换了登录密钥，才需要同步更新 `TEST_SSH_PRIVATE_KEY`。同时准备新服务器的仓库拉取权限、Docker、`.env`、数据及自管代理配置。不要将旧服务器的主机公钥记录直接用于新服务器。

### 3. 触发与部署行为

将本次部署配置提交并推送到 `main` 后，在 Actions 中查看 **Deploy backend to test server**。也可选择该 workflow，点击 **Run workflow** 并选择 `main`；其他分支不会执行部署。

workflow 会先检出触发提交中的部署脚本，通过 SSH 将该脚本传给服务器，并调用以下同一套逻辑：

```bash
bash scripts/deploy-test.sh --deploy-dir /opt/smartdiet/backend --sync --revision "$DEPLOY_SHA"
```

这里的 `DEPLOY_SHA` 由 Actions 提供，为触发任务的完整提交值；正常手动部署直接使用 `--sync` 即可。传输脚本使首次启用不依赖服务器上已经有新版脚本。脚本主体先完整解析，再隔离标准输入执行，防止 Git/Docker 消耗 SSH 传入的后续代码而出现提前结束。

脚本会：

1. 校验配置、建立 SSH 连接，并在服务器取得部署锁。
2. 检查服务器工作区；存在未提交或未跟踪的非忽略文件时停止，保留本地修改。
3. 获取 `origin/main`，仅部署与当前远程主分支一致的本次提交 SHA，跳过过时任务。
4. 切换到该 SHA（detached HEAD），校验 `.env` 和 Compose 配置，构建以 SHA 为标签的应用镜像。
5. 构建成功后更新容器，并清理同项目中已移除的服务容器，最多等待 120 秒。应用健康检查从容器内请求 `/health`，同时校验 HTTP 成功、`code=0` 和 `data.status=ok`；Compose 也等待数据库、Redis 健康。部署不再依赖外部域名、HTTPS 或代理状态。
6. 成功后将 SHA 写入 `.git/smartdiet-test-deployed-sha`；失败时返回非零状态，并输出容器状态和近期日志。

同一时间只运行一个部署，不自动取消正在执行的任务；服务器文件锁也会串行处理尚未退出的 SSH 部署进程。单实例更新有短暂中断。构建失败时不更新现有容器；容器更新、迁移或健康检查失败时不会自动回滚。

`/health` 是应用存活检查，首次部署后还需验证注册/登录、数据查询和图片上传。数据库迁移成功后的代码回退不等于数据库回退。

确认部署成功应查看实际执行日志中的以下信息，而不只是日志开头打印的脚本文本：

```text
Successfully deployed <本次提交 SHA> to the test server.
```

还应确认该任务最终成功，且 `ps` 中运行的是本次 SHA 标签的应用镜像。仅出现 `Built API image ...; running services unchanged.` 表示手动预构建完成；`Skipping outdated deployment ...` 表示跳过旧提交，不代表已部署该提交。当前部署不自动验证公网代理，最终仍需由维护者进行公网访问验收。

### 4. 查看状态与恢复

以部署用户在仓库目录执行（自动部署后，先加载上次成功版本，避免 Compose 默认使用 `local` 镜像）：

```bash
cd /opt/smartdiet/backend
export DEPLOY_SHA="$(cat .git/smartdiet-test-deployed-sha)"
docker compose --env-file .env -f docker-compose.test.yml ps --all
docker compose --env-file .env -f docker-compose.test.yml logs --tail 100 app
cat .git/smartdiet-test-deployed-sha
```

该记录仅表示最近一次成功部署的镜像标签；Actions 部署为完整 SHA，手动部署含未提交修改的工作区时为 `local-<提交前12位>`。失败任务可能已经更新容器或迁移了数据库。首次部署失败时尚无该文件，可从本次日志取镜像标签设置 `DEPLOY_SHA` 后查看状态。修复配置或服务问题后，重新运行脚本或最新 `main` 的 workflow。排查迁移失败需先核对数据库状态；需要回退时，通过代码 revert 形成新的 `main` 提交，并确认其兼容当前数据库结构。

构建时报 `No matching distribution found` 时，先核对包的版本、Python 和系统架构，再检查服务器到所选索引的网络连通性及该索引是否包含锁定版本。可切换 `PIP_INDEX_URL` 后重新构建；镜像同步延迟也可能暂时缺少新版本。pip 的升级提示本身不是安装失败原因，不要直接删除版本约束或哈希校验。只修改 `.env` 中的下载源即可，不需要在服务器修改 Dockerfile 或 Compose 文件。

日常更新保留数据卷，不执行 `docker compose down --volumes`。服务器工作区供自动部署使用，代码修改应在开发机提交；服务器仅修改被 Git 忽略的 `.env`。

### 5. SSH 与部署常见问题

| 现象 | 检查和处理 |
| --- | --- |
| 本机首次连接提示 `The authenticity of host ... can't be established` | 在云厂商控制台核对服务器主机指纹，一致后输入 `yes`；这只保存本机信任记录 |
| Actions 报 `Host key verification failed` | 核对 `TEST_SSH_KNOWN_HOSTS` 的主机名、端口和主机公钥是否与当前服务器一致，不要填指纹或用户登录公钥 |
| `Permission denied (publickey)` | 核对部署用户名、私钥对应的公钥、该用户的 `authorized_keys` 和文件权限；用指定密钥执行无人值守登录测试 |
| `Load key ... invalid format` 或私钥校验失败 | 检查 Secret 是否包含完整私钥、真实换行和首尾标记，是否误填 `.pub`、额外引号或带口令的密钥 |
| `Connection refused` 或连接超时 | 检查 SSH IP、端口、服务状态、安全组和防火墙；尚未进入密钥认证阶段 |
| `git fetch` 报 GitHub 主机校验或权限错误 | 排查服务器到 GitHub 的第二条连接，检查服务器 `known_hosts` 和仓库 Deploy Key；不要把 GitHub 主机密钥填进 `TEST_SSH_KNOWN_HOSTS` |
| `Deployment stopped: the server checkout has local changes` | 执行 `git status --short` 核对本地修改，保存或提交需要保留的内容，再从开发机推送；不要盲目清空服务器工作区 |
| 缺少 `MINIO_PUBLIC_URL` | 在服务器 `.env` 显式填写实际图片访问根地址，再重新部署；不再从域名变量自动生成 |
| 内网健康检查成功，但域名 HTTPS 无法访问 | 单独检查自管代理、域名解析、证书和公网端口；若 HTTP 返回 `Non-compliance ICP Filing`，到云厂商核查域名备案及接入状态 |

参考：[GitHub Actions Secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)、[OpenSSH ssh-keygen](https://man.openbsd.org/ssh-keygen)、[OpenSSH ssh-keyscan](https://man.openbsd.org/ssh-keyscan)。

## 生产部署

1. **修改默认密码**
   - 修改 `JWT_SECRET`
   - 修改数据库密码
   - 修改 `POSTGRES_PASSWORD`

2. **使用反向代理**

   自行配置 HTTPS 反向代理，API 上游为本机 `8000` 端口，MinIO API 上游为本机 `9002` 端口（以实际端口变量为准）。API 保留原路径并支持 SSE 实时输出；单图和批量上传请求体上限分别为 11 MiB、61 MiB。MinIO 应使用独立域名根地址，保留 Host、路径和查询串，避免破坏签名 URL。证书管理、HTTP 跳转和公网入口验收由维护者负责。

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

测试使用独立 Redis，按随机命名空间隔离和清理，仅删除本次测试的键，不执行 `FLUSHDB`。未设置 `TEST_REDIS_URL` 时跳过 Redis 集成用例；手动执行完整测试前需配置可访问的测试 Redis。

```powershell
$env:TEST_REDIS_URL = "redis://localhost:6379/15"
python -m pytest -q
```

覆盖跨实例并发原子性、身份隔离、批量计数、状态过期、登录保护、可信 IP、普通/SSE 共享额度、故障关闭及开关行为。

## 依赖安全验证

`requirements.in` 维护直接依赖；`requirements.txt` 是针对 Python 3.12 生成的跨平台完整锁定文件，含安装包哈希。继续使用 `python -m pip install -r requirements.txt` 即可安装锁定版本。JWT 改用 PyJWT，移除了未使用的 `langchain`、`langchain-community` 及其额外依赖。

更新版本后使用 `uv pip compile requirements.in --universal --python-version 3.12 --generate-hashes --output-file requirements.txt` 重新生成锁定文件，再手动执行 `python -m pip check`、`python -m pip_audit --strict`（审计工具另行安装 `pip-audit==2.10.1`）。
