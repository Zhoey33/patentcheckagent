# 这个文件用于说明专利审查系统在阿里云 ECS 上的部署流程。

# 阿里云 ECS 部署说明

## 1. 准备服务器

1. 购买或准备阿里云 ECS。
2. 安全组开放 `80`、`443`、必要的 SSH 端口。
3. 安装 Docker 与 Docker Compose。
4. 确认域名已备案并可解析到 ECS 公网 IP。

## 2. 拉取代码

```bash
git clone git@github.com:Zhoey33/patentcheckagent.git
cd patentcheckagent
```

如果服务器尚未配置 GitHub SSH key，需要先把服务器公钥添加到 GitHub。

## 3. 写入生产配置

```bash
cp .env.example .env
```

必须修改：

- `APP_SECRET_KEY`：生产随机长密钥。
- `GPT_API_KEY`：公司提供的模型 API key。
- `POSTGRES_PASSWORD`：生产数据库密码。
- `FRONTEND_URL`：正式域名，例如 `https://your-domain.example`。
- `NEXT_PUBLIC_API_BASE_URL`：正式 API 访问地址，例如 `https://your-domain.example`。

不要把 `.env` 提交到 Git。

## 4. 启动服务

```bash
docker compose up -d --build
docker compose ps
```

首次启动会通过 `backend` 服务执行种子脚本，创建 1 个管理员账号和 2 个普通账号。账号和密码来自 `.env` 中的 `SEED_*` 变量。

## 5. 配置 HTTPS

推荐在 ECS 上使用 Certbot 或阿里云证书服务签发证书，再将 `deploy/nginx/default.conf` 扩展为 `443 ssl` 监听。HTTPS 配置完成后，将 HTTP 重定向到 HTTPS。

## 6. 验证

1. 打开正式域名。
2. 使用种子账号登录。
3. 上传可复制文本型 PDF。
4. 检查任务进入 `审查中`。
5. Worker 完成后报告可展示、复制、下载。
6. 历史记录只能看到当前用户自己的任务。

## 7. 升级

```bash
git pull
docker compose up -d --build
```

升级前建议备份 PostgreSQL 数据卷或执行数据库备份。
