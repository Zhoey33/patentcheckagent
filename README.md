# 这个文件用于说明专利文件智能审查系统的开发、运行和部署方式。

# 专利文件智能审查系统

仓库代号：`patentcheckagent`

面向实验室内部使用的专利申请文件智能审查系统。系统支持固定账号登录、PDF/Word 原文件上传、管理员 Skill 管理、异步调用 Codex 执行专利审查 skill、实时执行过程展示、Markdown 报告展示与历史记录查询。

## 技术栈

- 前端：Next.js、React、TypeScript、Tailwind CSS
- 后端：FastAPI、SQLAlchemy、Alembic、Pydantic
- 异步任务：Redis、RQ
- 数据库：PostgreSQL
- 模型执行：Codex CLI + `skills/check-patent/SKILL.md`
- 部署：Docker Compose、Nginx

## 安全说明

- Codex 认证信息只允许保存在本地或服务器运行环境中。
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
- 执行事件：`GET /api/patent-checks/{task_id}/events`、`GET /api/patent-checks/{task_id}/events/stream`
- Skills：`GET /api/skills`、`GET/POST /api/admin/skills`、`GET/PUT/DELETE /api/admin/skills/{id}`、`POST /api/admin/skills/{id}/default`
- 管理员：`GET /api/admin/users`、`POST /api/admin/users`、`PATCH /api/admin/users/{user_id}`、`POST /api/admin/users/{user_id}/reset-password`、`GET /api/admin/patent-checks`

## 上传规则

- 权利要求书文件、说明书文件为必填。
- 附图说明文件、摘要文件为可选。
- 支持 PDF（含扫描件）和 Word（`.docx`），每个文件最多 20 MB。上传阶段只保存原文件，不抽取文字、不转换页面。
- Codex 根据 Skill 自行调用文件工具；扫描页按需渲染并查看，无法辨读或未完成的部分须在报告中说明。
- 成功或取消后清理原文件；失败时保留原文件供重试。历史报告及所用 Skill 快照保留。

## Skill 管理

管理员登录后打开 `/skills`，可新建、编辑、导入 Markdown、启停、删除和设置默认 Skill。支持 `SKILL.md` 和 `references/` 下的 Markdown 规则，上传任务时可选择启用的 Skill。

每个任务保存提交时的完整规则快照。Worker 将其放入任务目录的 `.agents/skills/<name>/`，显式调用 `$<name>`，仅把原文件路径和阶段指令交给 Codex。第二阶段读取完整第一阶段报告，保持技术特征编号。

首次启动从 `skills/check-patent/` 初始化默认规则，之后由管理员维护；重启不会覆盖已有修改。旧报告仍可查看；原文件已经清理的旧失败任务需要重新上传。

Docker Worker 使用 `deploy/codex-seccomp.json`，在 Moby 默认规则上允许 `clone`、`unshare`、`setns`、`mount`、`umount2`、`pivot_root`，供 Codex 的用户命名空间沙箱运行，无需特权容器。Codex 固定为已验证的 0.154.0；每次调用仅允许读写自己的任务目录及读取必要系统工具，禁止工具联网，并移除应用数据库等环境凭据。自定义权限配置优先于通用 `CODEX_SANDBOX_MODE`。

seccomp 基础规则来自 [Moby profiles](https://github.com/moby/profiles/blob/main/seccomp/default.json)，2026-09-14 获取，许可证见 `deploy/moby-profiles-LICENSE`。

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

无域名 HTTPS 部署见 [docs/deployment-ip.md](docs/deployment-ip.md)。Skill 参考分析与改动见 [docs/skill-review.md](docs/skill-review.md)。
