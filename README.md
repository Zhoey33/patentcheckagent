# 这个文件用于说明专利文件智能审查系统的开发、运行和部署方式。

# 专利文件智能审查系统

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

## 文档

- 产品需求：[docs/PRD.md](docs/PRD.md)
- 技术设计：`docs/superpowers/specs/`
- 实施计划：`docs/superpowers/plans/`
