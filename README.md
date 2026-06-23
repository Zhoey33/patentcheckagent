# 这个文件用于说明专利文件智能审查系统的开发、运行和部署方式。

# 专利文件智能审查系统

仓库代号：`patentcheckagent`

面向实验室内部使用的专利申请文件智能审查系统。系统支持固定账号登录、PDF 文件上传、文本抽取、异步调用 GPT-5.5 审查模板、Markdown 报告展示与历史记录查询。

## 技术栈

- 前端：Next.js、React、TypeScript、Tailwind CSS
- 后端：FastAPI、SQLAlchemy、Alembic、Pydantic
- 异步任务：Redis、RQ
- 数据库：PostgreSQL
- 部署：Docker Compose、Nginx

## 安全说明

- 真实 API key 只允许写入本地或服务器 `.env`。
- `.env` 与 `llm_api.md` 已被 `.gitignore` 排除，不得提交到 GitHub。
- 密码使用哈希存储，前端和接口响应不得暴露密钥、堆栈和服务器路径。

## 本地启动

开发完成后使用：

```bash
cp .env.example .env
docker compose up --build
```

默认访问：

- 前端：http://localhost:3000
- 后端：http://localhost:8000/docs

## 已实现接口

- 认证：`POST /api/auth/login`、`POST /api/auth/logout`、`GET /api/auth/me`
- 审查任务：`POST /api/patent-checks`、`GET /api/patent-checks`、`GET /api/patent-checks/{task_id}`、`GET /api/patent-checks/{task_id}/report`、`POST /api/patent-checks/{task_id}/retry`
- 管理员：`GET /api/admin/users`、`POST /api/admin/users`、`PATCH /api/admin/users/{user_id}`、`POST /api/admin/users/{user_id}/reset-password`、`GET /api/admin/patent-checks`

## 本地验证

```bash
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python -m ruff check backend/app backend/tests backend/alembic
cd frontend && npm run build
docker compose config
```

## 文档

- 产品需求：[docs/PRD.md](docs/PRD.md)
- 技术设计：`docs/superpowers/specs/`
- 实施计划：`docs/superpowers/plans/`
