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

## Codex 执行失败

排查顺序：

1. 确认后端和 Worker 容器内可以执行 `CODEX_COMMAND`。
2. 确认 `.env` 中 `CODEX_SKILL_PATH` 指向存在的 skill 文件。
3. 确认 Codex 认证、模型和网络配置在容器运行环境中可用。
4. 查看 `worker` 日志和任务详情中的 Codex 执行过程。

按任务 ID 查看 Worker 日志：

```bash
docker compose logs worker | grep '<task_id>'
```

查看 Codex 阶段审计记录：

```bash
docker compose exec -T postgres psql -U patent_user -d patent_check_agent \
  -c "select stage,status,error_message,latency_ms,created_at from model_call_logs where task_id='<task_id>' order by created_at;"
```

查看 Codex 执行事件：

```bash
docker compose exec -T postgres psql -U patent_user -d patent_check_agent \
  -c "select id,stage,event_type,message,created_at from patent_check_events where task_id='<task_id>' order by id;"
```

日志事件说明：

- `patent_task_started`：Worker 开始处理任务。
- `codex_stage_started`：开始某个 Codex 审查阶段。
- `codex_stage_failed`：某个阶段最终失败，并已写入审计表。
- `patent_task_timeout`：任务超过 Worker 作业超时。
- `patent_task_succeeded`：任务生成最终报告。

日志中不得打印完整认证信息或完整专利文本。默认 Worker 作业超时由 `WORKER_JOB_TIMEOUT_SECONDS` 控制，应大于两阶段 Codex 执行的最坏耗时。

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

Worker 在任务成功后清理上传原始文件和过程文本，仅保留文件元数据、状态、错误、阶段结果和最终报告。任务失败时会清理上传原始文件，但保留可重试所需的过程文本；用户点击重试并成功完成后，过程文本会被清理。如果任务一直停留在 `pending`，优先检查 Redis 和 Worker 是否正常。

## 上线前安全清单

- `.env` 未提交 Git。
- `llm_api.md` 未提交 Git。
- 生产 `APP_SECRET_KEY` 不使用默认值。
- PostgreSQL 密码已更换。
- 生产域名启用 HTTPS。
- 普通用户无法访问他人任务详情。
