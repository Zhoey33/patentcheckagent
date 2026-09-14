# 香港服务器：通过 IP 访问

目标服务器：`47.76.238.160`，Alibaba Cloud Linux 3，x86_64。
应用目录：`/opt/patent_check_agent`。
访问入口：`https://47.76.238.160`。

本方案使用 `docker-compose.yml` 和 `docker-compose.ip.yml`。生产配置位于服务器的 `.env`，不提交到 Git。至少设置：

```dotenv
PUBLIC_IP=47.76.238.160
APP_ENV=production
FRONTEND_URL=https://47.76.238.160
NEXT_PUBLIC_API_BASE_URL=https://47.76.238.160
```

IP 部署覆盖文件使用 Debian、PyPI 和 npm 官方软件源，避免香港服务器无法连接内地镜像源导致构建失败。前端更新到 Next.js 15.5.25，包含此次上线前核实的安全修复。

模型 API 配置、数据库密码、应用签名密钥和三个种子账号密码也保存在服务器 `.env`。账号密码每次后端启动时都会按种子配置同步，因此修改初始账号密码时应同步修改该文件。

当前模型使用阿里云百炼 `qwen3.8-flash`，通过 Codex CLI 的 Responses 接口调用：

```dotenv
GPT_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
GPT_MODEL=qwen3.8-flash
CODEX_MODEL=qwen3.8-flash
CODEX_TIMEOUT_SECONDS=600
```

`GPT_API_KEY` 仅填写在服务器 `.env`，保持文件权限为 `600`。修改模型配置后执行以下命令，使后端和队列进程加载新配置：

```bash
sudo docker compose -f docker-compose.yml -f docker-compose.ip.yml up -d backend worker
sudo docker compose -f docker-compose.yml -f docker-compose.ip.yml exec -T nginx nginx -s reload
```

## 启动和检查

在服务器执行：

```bash
cd /opt/patent_check_agent
sudo docker compose -f docker-compose.yml -f docker-compose.ip.yml build backend frontend
sudo docker compose -f docker-compose.yml -f docker-compose.ip.yml up -d
sudo docker compose -f docker-compose.yml -f docker-compose.ip.yml ps
curl https://47.76.238.160/api/health
```

小内存服务器构建时可分别执行 `build backend` 和 `build frontend`。浏览器 API 地址在前端构建时写入，修改地址后需要重新构建前端。

公网提供 `80`（HTTPS 跳转和证书验证）和 `443`（应用入口）。`3000` 和 `8000` 仅绑定服务器本地，PostgreSQL 和 Redis 仅在 Docker 网络内通信。容器配置为随 Docker 恢复启动，日志按每个容器 3 个 10 MB 文件轮转。

## IP 证书

使用 Certbot 5.4 的 webroot 模式申请 Let's Encrypt IP 证书，证书目录为 `/etc/letsencrypt`，验证目录为 `/var/www/patent-check-certbot`。首次签发需要先用临时 HTTP 服务提供此验证目录，再启动包含 HTTPS 配置的 Nginx。

IP 证书有效期为 6 天，必须自动续期。服务器的 `patent-ip-certificate.timer` 每天检查两次续期，并通过 `deploy/renew_ip_certificate.sh` 重载 Nginx：

```bash
sudo systemctl status patent-ip-certificate.timer
sudo journalctl -u patent-ip-certificate.service -n 30 --no-pager
```

不要关闭公网 80 端口，否则后续证书验证会失败。

## 日志与备份

```bash
cd /opt/patent_check_agent
sudo docker compose -f docker-compose.yml -f docker-compose.ip.yml logs --tail=100 backend worker nginx
```

升级或迁移前备份 PostgreSQL 数据、上传文件卷、生产 `.env` 和证书目录。不要使用 `docker compose down -v`，它会删除应用数据卷。

## 2026-09-14 首次部署验证（原纯文本流程）

- 六个容器已启动，后端、PostgreSQL 和 Redis 健康检查通过。
- 公网 HTTPS 证书验证、HTTP 跳转、登录页面和引用的 JavaScript 文件访问通过。
- 通过 HTTPS API 验证登录、Secure Cookie、上传两份合成 Word 材料、队列执行、SSE 实时进度、用户隔离、管理员访问和登出。
- Certbot 模拟续期通过，systemd 续期服务执行成功。
- 已切换到阿里云百炼 `qwen3.8-flash`。Responses 接口与 Codex CLI 实际调用通过；两阶段审查执行成功，任务状态为 `succeeded`，进度为 100%，生成 11,530 字最终报告。
- 本次任务耗时约 6 分 25 秒（第一阶段 219.2 秒，第二阶段 165.5 秒）；完成后输入材料已清理，报告和进度事件可正常读取。
- 验收任务：`11de1405-daf2-488c-8772-115448cbb33f`，标题为“部署验收：合成温度提示装置”。管理员可在任务列表查看报告；验收使用合成材料，验证部署和流程，不代表对真实专利的审查质量评估。
- 浏览器自动化工具超时，因此本次页面检查使用 HTTP 响应和接口验证，未完成浏览器交互自动化检查。


## 原文件与 Skill 版本升级

升级先备份数据库，并确认没有运行中任务；更新后端和前端镜像后执行 `up -d`。后端自动运行 `20260914_0004` 迁移，创建 Skill 表和任务快照列，并初始化内置规则。不要手工删除旧表或历史任务。

Worker 所需 seccomp 文件 `deploy/codex-seccomp.json` 必须随 Compose 文件一起更新。它允许创建 Codex 沙箱所需的命名空间操作；任务自身仍采用仅访问当前工作目录、禁止文件工具联网的权限配置。Codex 超时时限提升至每阶段 600 秒。管理员登录后可在 `/skills` 修改规则；已有数据库规则不会被后续镜像更新覆盖。
