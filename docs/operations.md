# 这个文件用于记录系统日常运维、排障和安全检查方法。

# 运维手册

## 常用命令

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f frontend
docker compose logs -f nginx
```

## 健康检查

```bash
curl http://localhost:8000/api/health
```

返回 `{"status":"ok"}` 表示后端进程可访问。

## 账号维护

第一版不提供管理员页面，账号可以通过种子脚本或管理员 API 维护。修改 `.env` 中的 `SEED_*` 变量后运行：

```bash
docker compose run --rm backend python -m app.scripts.seed_users
```

管理员 API：

```text
GET  /api/admin/users
POST /api/admin/users
PATCH /api/admin/users/{user_id}
POST /api/admin/users/{user_id}/reset-password
GET  /api/admin/patent-checks
```

这些接口需要管理员账号登录态。普通用户访问会返回 `403`。

## 模型调用失败

排查顺序：

1. 确认 `.env` 中 `GPT_API_KEY` 已配置。
2. 确认 ECS 可以访问 `GPT_BASE_URL`。
3. 查看 `worker` 日志。
4. 查看任务详情中的失败原因。

日志中不得打印完整 API key 或完整专利文本。

## Docker Hub 拉取超时

如果 `docker compose up --build` 在拉取 `node:22-alpine`、`python:3.12-slim` 等基础镜像时出现 `i/o timeout`，先确认 Docker Desktop 已启动，然后在 `.env` 中临时改用可访问的镜像前缀，例如：

```bash
PYTHON_BASE_IMAGE=docker.m.daocloud.io/library/python:3.12-slim
NODE_BASE_IMAGE=docker.m.daocloud.io/library/node:22-alpine
POSTGRES_IMAGE=docker.m.daocloud.io/library/postgres:16-alpine
REDIS_IMAGE=docker.m.daocloud.io/library/redis:7-alpine
NGINX_IMAGE=docker.m.daocloud.io/library/nginx:1.27-alpine
```

后端 Python 依赖安装已在 Dockerfile 中配置清华 PyPI 源。前端 Docker 构建已配置 npm 镜像源，避免构建阶段再次卡在 npm 下载。

## 上传与清理

Worker 在任务成功或失败后清理上传原始文件和过程文本，仅保留文件元数据、状态、错误、阶段结果和最终报告。如果任务一直停留在 `pending`，优先检查 Redis 和 Worker 是否正常。

## 上线前安全清单

- `.env` 未提交 Git。
- `llm_api.md` 未提交 Git。
- 生产 `APP_SECRET_KEY` 不使用默认值。
- PostgreSQL 密码已更换。
- 生产域名启用 HTTPS。
- 普通用户无法访问他人任务详情。
