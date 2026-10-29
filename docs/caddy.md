# Caddy HTTPS 部署

服务器使用独立的 `docker-compose.test.yml`，本地开发继续使用 `docker-compose.yml`。配置位于 `caddy/Caddyfile`，整个 `caddy/` 目录只读挂载，确保 Git 更新文件后 reload 可读取新内容。Caddy 固定为 `2.11.7-alpine`，统一提供两个 HTTPS 入口：

| 入口 | Compose 内上游 | 用途 |
| --- | --- | --- |
| `https://<API_DOMAIN>` | `app:8000` | API、SSE、上传、健康检查和接口文档 |
| `https://<IMAGES_DOMAIN>` | `minio:9000` | 私有图片的短时签名访问 |

两个域名必须不同，均填写普通 DNS 主机名，不带协议、端口和路径。默认使用 `api.hsunr.xyz`、`images.hsunr.xyz`，请确认你控制这些域名并完成解析。Caddy 自动申请和续期公开受信证书，并将 HTTP 跳转至 HTTPS。

## 首次部署与切换

1. 在服务器准备 README 中要求的 Docker、Compose 和部署目录。将两个域名的 A 记录指向服务器公网 IPv4；如存在 AAAA 记录，IPv6 也必须可达，否则修正或移除错误记录。首次验证建议使用直接解析，避免 CDN 影响证书验证、客户端 IP 和访问检查。
2. 安全组与防火墙开放 TCP `80/443`；UDP `443` 用于 HTTP/3，可选。保留 SSH 管理入口。API `8000`、MinIO API `9002`、控制台 `9001` 均仅绑定 `127.0.0.1`，不需要对公网开放；PostgreSQL、Redis 不发布端口。
3. 检查现有 `80/443` 监听者。如果已运行宿主机 Caddy、Nginx 或其他 HTTPS 服务，先记录其配置与恢复方式；在配置校验和镜像构建完成后，再于切换窗口停止占用端口的旧入口。新 Caddy 与旧入口不能同时占用这些端口。若旧入口同时承载其他站点，应先将其路由纳入切换方案。
4. 新服务器复制 `.env.test.example` 为 `.env` 并填写密钥；已有服务器将新增变量合并到原 `.env`，不要覆盖已有密钥。设置 `API_DOMAIN`、`IMAGES_DOMAIN`、真实的 `ACME_EMAIL`。`MINIO_PUBLIC_URL` 由 Compose 自动设为 `https://<IMAGES_DOMAIN>`，原 `.env` 中同名旧值不再用于此服务器配置。
5. 默认可信代理子网为 `172.30.88.0/24`，仅 Caddy 和应用加入；若与服务器已有 Docker、局域网或 VPN 网段冲突，调整 `CADDY_PROXY_SUBNET`。容器 IP 由 Docker 动态分配，不再设置固定 IP。旧 `.env` 中的 `CADDY_PROXY_IP` 可以删除，保留也不会生效。
6. 旧数据库数据由你手动清理。此改动不执行清库、删卷或旧图片地址回填。当前迁移基线要求空库或已兼容的数据库；切换图片域名后，旧域名的数据库图片引用不会自动转换。MinIO 旧对象是否删除也由你决定。

在后端目录执行（先完成上述配置和数据准备）：

```bash
docker compose --env-file .env -f docker-compose.test.yml config --quiet
docker compose --env-file .env -f docker-compose.test.yml build app
docker compose --env-file .env -f docker-compose.test.yml run --rm --no-deps app python scripts/check_deployment.py
docker compose --env-file .env -f docker-compose.test.yml run --rm --no-deps caddy-validate
# 此时再释放旧入口占用的 80/443，然后启动：
docker compose --env-file .env -f docker-compose.test.yml up -d --no-build --wait --wait-timeout 120
docker compose --env-file .env -f docker-compose.test.yml exec -T app python scripts/check_deployment.py --https
```

两项部署前校验不启动依赖，也不执行迁移。`caddy-validate` 使用无网络的独立工具容器，不加入运行中的服务网络。`up` 会启动应用并执行原有的 `alembic upgrade head`。

HTTPS 检查默认等待最多 180 秒，为首次证书申请预留时间；校验证书链和主机名、API `/health` 的业务响应、MinIO `/minio/health/live`，以及两个域名的 HTTP 跳转。检查使用公网域名，不通过容器服务名访问；服务器必须能访问这两个域名的公网入口。证书签发失败时查看 Caddy 日志，检查 DNS、80/443 可达性、CAA 限制及服务器访问 ACME 服务的网络。

## 代理与访问限制

Caddy 和应用加入独立的 `proxy` 网络；Caddy 与 MinIO 通过另一个 `storage_proxy` 网络通信，MinIO 不加入可信代理网络。应用、MinIO、数据库和 Redis 保留原服务网络连接。Uvicorn 开启代理头解析，且仅信任 `CADDY_PROXY_SUBNET`，不信任来自原服务网络或公网的代理头。Caddy 作为公网第一层入口默认丢弃外部提交的伪造 `X-Forwarded-For`，生成真实客户端地址，从而支持现有 IP 限流。

所有容器使用动态地址，避免先启动的 MinIO 等服务占用 Caddy 的固定 IP 而导致 `Address already in use`。从旧配置升级时直接使用正常部署流程，Compose 会更新 Caddy、应用和 MinIO 的网络连接；不需要删除网络或数据卷。

如果以后在 Caddy 前增加 CDN、负载均衡或其他反向代理，需要按其可信出口地址另外配置 Caddy 的可信代理；当前配置不直接信任任意来源的转发头。

API 保持原始路径。单图上传 `/api/v1/upload` 请求体最多 11 MiB，批量 `/api/v1/upload/images` 最多 61 MiB，包含尾斜杠形式；应用继续校验单图 10 MiB、格式、像素和归属。Caddy 对 API 关闭响应延迟刷新，支持 SSE 逐步输出。

MinIO 代理不重写 Host、路径和查询串，不新增 URL 前缀、不开放匿名桶策略。签名 URL 本身是临时凭证，请勿加入公开访问日志或聊天截图。此配置默认不启用 Caddy 访问日志；运行错误仍写入容器日志。

## 沿用已有证书（可选）

默认无需手动管理证书。如果必须沿用现有公开证书，将证书和私钥放到服务器的 `caddy/tls` 下，并创建以下片段。例如 API 入口：

```text
caddy/tls/api/certificate.caddy
caddy/tls/api/fullchain.pem
caddy/tls/api/privkey.pem
```

`certificate.caddy` 内容：

```caddyfile
tls /etc/caddy/tls/api/fullchain.pem /etc/caddy/tls/api/privkey.pem
```

图片域名同理使用 `caddy/tls/images/`，证书须包含相应域名。该目录只读挂载进 Caddy，片段、证书与私钥被 Git 和应用镜像忽略，限制其服务器文件权限。手动加载的证书由原签发方续期，更新后重新校验并 reload；Caddy 不会自动续期这些手动证书。不要同时运行其他占用 `80/443` 的证书工具服务。未配置证书片段时，校验可能提示通配导入未匹配文件，这是正常提示。

## 前端与微信

前端生产、测试环境当前已经使用 `https://api.hsunr.xyz`。如果更换 API 域名，同时修改对应构建环境的 `VITE_SERVER_BASEURL` 和 `VITE_SERVER_BASEURL__WEIXIN_*`，并重新构建。真机开发可复制 `unibest/env/.env.https.example` 为对应 `.local` 文件。

微信后台的 request、uploadFile 合法域名应包含 API 域名；downloadFile 及图片相关域名应包含图片域名。H5 验证图片预览、登录、上传和 SSE；本次不将前端静态站点托管纳入 Caddy，也不修改现有 CORS 策略。

## 自动部署与日常维护

GitHub Actions 在原有镜像构建后增加域名配置和 Caddyfile 校验；容器健康后 reload Caddy 并验证公网 HTTPS，全部成功才记录部署 SHA。首次启用前必须先更新服务器 `.env`、DNS，并处理现有端口占用。失败日志包含 Caddy；不自动回滚迁移或清理数据。

自动部署后运行下列命令时，先按 README 从 `.git/smartdiet-test-deployed-sha` 加载 `DEPLOY_SHA`。首次部署失败则使用 Actions 日志中的本次 SHA。

```bash
docker compose --env-file .env -f docker-compose.test.yml ps --all
docker compose --env-file .env -f docker-compose.test.yml logs --tail 100 caddy app
docker compose --env-file .env -f docker-compose.test.yml run --rm --no-deps caddy-validate
docker compose --env-file .env -f docker-compose.test.yml exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

证书保存在 `caddy_data` 命名卷，运行配置在 `caddy_config`，普通重建容器不会丢失。备份和恢复时保留这些卷；不要通过删除卷解决配置问题。仅修改 `.env` 后需重新创建容器使环境变量生效，单纯 reload 不会重新读取宿主机 `.env`。切换失败时可停止新的 Caddy，恢复此前入口配置；应用及数据库的回退需单独评估。

## 验收与本地测试

1. 两个域名的 HTTP 自动跳转，HTTPS 证书链及域名有效。
2. 注册、登录、单图/批量上传、签名图片预览和签名刷新正常，无签名的图片请求被拒绝。
3. SSE 在识别过程中持续返回，超限上传返回 413，限流返回 429，伪造转发头不能绕过 IP 限流。
4. 公网无法直连 8000、9002、9001；普通重启后证书仍在。

真实 Caddy 代理测试不依赖 Docker 或业务数据库；安装与部署一致版本的 Caddy 后运行：

```powershell
$env:CADDY_BIN = 'C:\tools\caddy.exe'
python -m pytest tests/test_caddy.py -q
```

测试使用临时高端口和回环上游，不申请公开证书，不修改现有服务；覆盖请求体边界、图片签名的 Host/路径/参数透传、伪造 IP、可信代理与 SSE 首个事件即时返回。未设置 `CADDY_BIN` 且 PATH 无 Caddy 时仅跳过真实代理测试。
