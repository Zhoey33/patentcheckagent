# 这个文件用于说明专利审查系统在阿里云 ECS 和 asqmsl.cn 域名上的部署流程。

# asqmsl.cn 阿里云 ECS 部署说明

推荐访问地址：`https://check.asqmsl.cn`

根域名 `https://asqmsl.cn/login` 当前已经是一个正在运行的专利解析系统。为了不覆盖现有系统，本项目默认部署到独立子域名，例如 `check.asqmsl.cn`。

当前外部探测结果：

- `asqmsl.cn` 已解析到 `81.70.201.9`。
- `www.asqmsl.cn` 已解析到 `81.70.201.9`。
- 当前 HTTPS 证书包含 `asqmsl.cn` 和 `www.asqmsl.cn`。
- `http://asqmsl.cn` 已返回 `301` 到 HTTPS。
- `https://asqmsl.cn` 已有宿主机 Nginx 返回 `200`。
- `https://asqmsl.cn/login` 当前已有业务系统，不建议直接覆盖根域名。
- `https://asqmsl.cn/api/health` 当前返回 `404`，说明根域名线上不是本系统。
- SSH `22` 端口可连。

因此当前推荐使用“新增子域名 + 宿主机已有 Nginx 反向代理 + Docker 只运行应用容器”的部署方式，避免 Docker Nginx 抢占 `80/443` 或覆盖根域名已有系统。

当前实际阻塞点：

- 阿里云控制台页面仍停在登录页，无法读取控制台内的 ECS 或域名资产信息。
- 本机执行 `ssh root@81.70.201.9` 仍返回 `Permission denied (publickey,password)`，无法登录服务器执行部署。

恢复部署所需的最短路径：

1. 在阿里云控制台确认 `81.70.201.9` 是要部署本系统的 ECS。
2. 给当前本机配置可用 SSH 登录方式，直到以下命令可以成功：

```bash
ssh root@81.70.201.9
```

3. 在 DNS 中新增子域名解析，例如 `check.asqmsl.cn -> 81.70.201.9`。
4. 回到本仓库执行自动初始化和部署：

```bash
./deploy/deploy_asqmsl_cn.sh --domain check.asqmsl.cn --no-www --bootstrap-ecs
```

如果服务器包源网络不稳定：

```bash
./deploy/deploy_asqmsl_cn.sh --domain check.asqmsl.cn --no-www --bootstrap-ecs --bootstrap-use-tsinghua-mirror
```

## 1. 上线前确认项

需要先准备：

- 一台阿里云 ECS，建议 2 核 4 GB 或以上。
- ECS 公网 IP。
- 可以 SSH 登录 ECS 的账号和密钥或密码。
- 阿里云安全组开放 `80`、`443` 和必要的 SSH 端口。
- 域名 `asqmsl.cn` 已完成备案，或确认当前服务器所在地域和接入方式满足备案要求。
- 公司模型网关配置：`GPT_BASE_URL`、`GPT_API_KEY`、`GPT_MODEL`。

## 2. 域名解析

在阿里云控制台进入 `asqmsl.cn` 的云解析 DNS，当前根域名和 `www` 已经指向旧系统所在服务器：

```text
记录类型：A
主机记录：@
记录值：81.70.201.9
TTL：默认
```

```text
记录类型：A
主机记录：www
记录值：81.70.201.9
TTL：默认
```

本项目当前推荐 HTTPS 入口是独立子域名 `check.asqmsl.cn`。

如果不想覆盖现有系统，不要修改上面两条记录。新增一条子域名记录即可：

```text
记录类型：A
主机记录：check
记录值：81.70.201.9
TTL：默认
```

这样：

- `https://asqmsl.cn/login` 继续访问旧系统。
- `https://check.asqmsl.cn` 访问本项目。

DNS 生效后，在本地或服务器上检查：

```bash
dig +short asqmsl.cn
dig +short www.asqmsl.cn
dig +short check.asqmsl.cn
```

输出应包含目标 ECS 公网 IP。证书可用以下命令确认：

```bash
printf '' | openssl s_client -servername check.asqmsl.cn -connect check.asqmsl.cn:443 2>/dev/null | openssl x509 -noout -subject -ext subjectAltName
```

## 3. 准备 ECS

登录服务器：

```bash
ssh root@<ECS 公网 IP>
```

安装基础工具、Docker、Compose 插件、Nginx、Certbot 和 rsync。服务器能 SSH 登录后，推荐直接从本机运行：

```bash
./deploy/deploy_asqmsl_cn.sh --domain check.asqmsl.cn --no-www --bootstrap-ecs
```

这个命令会先把 [deploy/bootstrap_ecs.sh](/Users/zhoey/project/patent_check_agent/deploy/bootstrap_ecs.sh) 传到服务器执行，再继续部署应用。如果服务器安装依赖时出现包源网络问题，按要求使用清华源重试：

```bash
./deploy/deploy_asqmsl_cn.sh --domain check.asqmsl.cn --no-www --bootstrap-ecs --bootstrap-use-tsinghua-mirror
```

也可以 SSH 到服务器后只运行初始化脚本：

```bash
bash deploy/bootstrap_ecs.sh
```

Alibaba Cloud Linux、CentOS、Ubuntu 的包管理命令略有差异，如果服务器已安装 Docker，可跳过安装部分。

Ubuntu 示例：

```bash
apt-get update
apt-get install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
```

如果 Docker 官方源网络不稳定，先按阿里云 ECS 系统镜像对应文档安装 Docker，不要绕过依赖问题。

## 4. 拉取代码

```bash
git clone git@github.com:Zhoey33/patentcheckagent.git
cd patentcheckagent
```

如果服务器尚未配置 GitHub SSH key，需要先生成并添加公钥到 GitHub。也可以使用 HTTPS 方式 clone，但不要把访问 token 写入仓库文件。

## 5. 写入生产配置

复制域名专用模板：

```bash
cp deploy/asqmsl.cn.env.example .env
```

必须修改：

- `APP_SECRET_KEY`：生产随机长密钥。
- `POSTGRES_PASSWORD`：生产数据库强密码。
- `GPT_BASE_URL`：公司提供的 OpenAI-compatible 模型 API 地址，例如 `https://helloapi.cc`。
- `GPT_API_KEY`：公司提供的模型 API key。
- `GPT_MODEL`：公司提供的模型名称。
- `SEED_ADMIN_PASSWORD`、`SEED_USER1_PASSWORD`、`SEED_USER2_PASSWORD`：初始账号强密码。

保持：

```env
APP_ENV=production
FRONTEND_URL=https://asqmsl.cn
NEXT_PUBLIC_API_BASE_URL=https://asqmsl.cn
CODEX_SANDBOX_MODE=danger-full-access
```

如果部署到 `check.asqmsl.cn`，自动部署脚本会把 `FRONTEND_URL` 和 `NEXT_PUBLIC_API_BASE_URL` 更新为：

```env
FRONTEND_URL=https://check.asqmsl.cn
NEXT_PUBLIC_API_BASE_URL=https://check.asqmsl.cn
```

不要把 `.env`、`llm_api.md` 或任何密钥提交到 Git。

## 6. 推荐方案：复用宿主机 Nginx

如果 `81.70.201.9` 是目标服务器，并且根域名已有系统不能覆盖，推荐使用本节部署到 `check.asqmsl.cn`。

### 6.1 自动部署脚本

本仓库提供了自动部署脚本，会执行代码同步、Docker 服务启动、宿主机 Nginx 配置安装和健康检查：

```bash
./deploy/deploy_asqmsl_cn.sh --domain check.asqmsl.cn --no-www
```

如果服务器还没有 Docker、Compose、Nginx、Certbot 或 rsync：

```bash
./deploy/deploy_asqmsl_cn.sh --domain check.asqmsl.cn --no-www --bootstrap-ecs
```

如果安装依赖遇到包源网络问题：

```bash
./deploy/deploy_asqmsl_cn.sh --domain check.asqmsl.cn --no-www --bootstrap-ecs --bootstrap-use-tsinghua-mirror
```

脚本默认连接：

```text
root@81.70.201.9
```

首次运行时，如果服务器没有 `.env`，脚本会在 `/opt/patent_check_agent/.env` 创建模板并停止。填入真实生产密钥后再次运行。

脚本默认拒绝直接部署到根域名 `asqmsl.cn`，防止覆盖现有系统。如果服务器已有其他 Nginx 配置匹配目标子域名，脚本会停止并打印冲突文件。确认本系统要接管该目标域名后，可以显式运行：

```bash
./deploy/deploy_asqmsl_cn.sh --domain check.asqmsl.cn --no-www --disable-conflicting-nginx
```

只同步和启动容器、不安装 Nginx 配置时：

```bash
./deploy/deploy_asqmsl_cn.sh --domain check.asqmsl.cn --no-www --no-nginx
```

如果 SSH 用户或服务器 IP 不同：

```bash
./deploy/deploy_asqmsl_cn.sh --domain check.asqmsl.cn --no-www --remote root@<ECS 公网 IP>
```

### 6.2 手动启动应用容器

应用容器只绑定到本机端口，公网不能直接访问 `3000/8000`：

```bash
docker compose -f docker-compose.yml -f docker-compose.host-nginx.yml up -d --build postgres redis backend worker frontend
docker compose -f docker-compose.yml -f docker-compose.host-nginx.yml ps
```

检查本机后端：

```bash
curl http://127.0.0.1:8000/api/health
```

预期返回：

```json
{"status":"ok"}
```

### 6.3 手动配置宿主机 Nginx

先备份当前站点配置：

```bash
mkdir -p /root/nginx-backup
cp -a /etc/nginx/sites-enabled /root/nginx-backup/sites-enabled.$(date +%Y%m%d%H%M%S) 2>/dev/null || true
cp -a /etc/nginx/conf.d /root/nginx-backup/conf.d.$(date +%Y%m%d%H%M%S) 2>/dev/null || true
```

复制本项目提供的模板并替换为子域名配置：

```bash
sed \
  -e "s#__SERVER_NAMES__#check.asqmsl.cn#g" \
  -e "s#__CERT_DOMAIN__#check.asqmsl.cn#g" \
  deploy/nginx/host.conf.template >/etc/nginx/conf.d/check.asqmsl.cn.conf
nginx -t
systemctl reload nginx
```

不要删除或修改当前承载 `asqmsl.cn` 的 server block；子域名应使用独立的 `server_name check.asqmsl.cn`。

### 6.4 验证

```bash
./deploy/check_asqmsl_cn.sh
```

浏览器打开：

```text
https://check.asqmsl.cn
```

用 `.env` 中的种子账号登录，上传一个 Word 或 PDF 文件，确认报告可以生成。

## 7. 备选方案：由 Docker Nginx 接管 80/443

只有在确认宿主机当前 Nginx 可以停止或移除时，才使用本节。

### 7.1 签发 HTTPS 证书

生产 `.env` 使用 `APP_ENV=production` 和 `https://check.asqmsl.cn`。因此不要先用 HTTP 登录验证，否则浏览器不会按生产规则发送 Secure Cookie。推荐先签发证书，再一次性启动 HTTPS 服务。

在 ECS 上安装 Certbot：

Ubuntu 示例：

```bash
apt-get update
apt-get install -y certbot
```

不要停止当前承载根域名的 Nginx。为子域名创建 webroot 校验目录后，用 webroot 模式完成 HTTP 校验：

```bash
mkdir -p /var/www/certbot
certbot certonly --webroot -w /var/www/certbot -d check.asqmsl.cn
```

证书成功后，路径应存在：

```bash
ls /etc/letsencrypt/live/check.asqmsl.cn/fullchain.pem
ls /etc/letsencrypt/live/check.asqmsl.cn/privkey.pem
```

### 7.2 启动 HTTPS 服务

证书存在后，用 HTTPS override 启动全套服务：

```bash
docker compose -f docker-compose.yml -f docker-compose.https.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.https.yml ps
```

验证：

```bash
curl -I https://check.asqmsl.cn
curl https://check.asqmsl.cn/api/health
```

HTTP 应自动跳转 HTTPS：

```bash
curl -I http://check.asqmsl.cn
```

## 8. 证书续期

如果使用 Docker Nginx 接管 `80/443`，Certbot standalone 续期需要临时释放 `80` 端口：

```bash
docker compose stop nginx
certbot renew
docker compose -f docker-compose.yml -f docker-compose.https.yml up -d nginx
```

如果复用宿主机 Nginx，优先沿用当前服务器已有的证书续期方式；若当前证书也是 Certbot 管理，可检查：

```bash
certbot certificates
systemctl list-timers | grep certbot
```

可后续改成 webroot 或 DNS 验证来减少停机时间。

## 9. 上线验证

逐项验证：

1. 打开 `https://check.asqmsl.cn`。
2. 使用种子账号登录。
3. 上传可复制文本型 PDF 或 Word（`.docx`）。
4. 检查任务进入 `审查中`，并显示用户可读的审查执行过程。
5. Worker 完成后报告可展示、复制、下载。
6. 历史记录只能看到当前用户自己的任务。
7. 管理员账号可以访问管理员接口。

常用命令：

```bash
docker compose -f docker-compose.yml -f docker-compose.host-nginx.yml logs -f backend
docker compose -f docker-compose.yml -f docker-compose.host-nginx.yml logs -f worker
docker compose -f docker-compose.yml -f docker-compose.https.yml logs -f backend
docker compose -f docker-compose.yml -f docker-compose.https.yml logs -f worker
docker compose -f docker-compose.yml -f docker-compose.https.yml logs -f nginx
```

## 10. 升级

```bash
git pull
docker compose -f docker-compose.yml -f docker-compose.host-nginx.yml up -d --build postgres redis backend worker frontend
docker compose -f docker-compose.yml -f docker-compose.https.yml up -d --build
```

升级前建议备份 PostgreSQL 数据卷或执行数据库备份。服务启动时会自动执行 Alembic 迁移；如果需要手动迁移，可执行：

```bash
docker compose -f docker-compose.yml -f docker-compose.host-nginx.yml run --rm backend alembic upgrade head
```

## 11. 服务器备份建议

至少备份：

- PostgreSQL Docker volume：`postgres_data`
- Redis Docker volume：`redis_data`
- 上传过程数据 Docker volume：`uploads_data`
- 生产 `.env`

查看 volume 名称：

```bash
docker volume ls | grep patent
```
