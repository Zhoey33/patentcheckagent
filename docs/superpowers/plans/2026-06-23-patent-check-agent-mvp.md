# 专利审查系统 MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 PRD 构建一个本地 Docker Compose 可运行、可部署到阿里云 ECS 的专利文件智能审查 MVP。

**Architecture:** Next.js 前端调用 FastAPI 后端；后端保存任务、抽取 PDF 文本并投递 Redis/RQ；Worker 调用 GPT-5.5 API 生成两阶段 Markdown 报告并写回 PostgreSQL。

**Tech Stack:** Next.js、React、TypeScript、Tailwind CSS、FastAPI、SQLAlchemy、Alembic、Pydantic、PostgreSQL、Redis、RQ、Docker Compose、Nginx。

---

### Task 1: 项目治理与文档

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`
- Create: `docs/superpowers/specs/2026-06-23-patent-check-agent-design.md`

- [x] **Step 1: 排除密钥和运行产物**

将 `.env`、`.env.*`、`llm_api.md`、`node_modules/`、`.next/`、`.venv/`、`uploads/`、`logs/` 写入 `.gitignore`。

- [x] **Step 2: 提供环境变量示例**

创建 `.env.example`，包含数据库、Redis、GPT、上传限制和种子账号变量，不包含真实密钥。

- [x] **Step 3: 写设计文档**

将技术架构、边界、安全策略、测试策略和部署策略写入设计说明。

### Task 2: 后端骨架与配置

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/main.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/security.py`
- Create: `backend/app/db/session.py`
- Create: `backend/app/db/base.py`

- [ ] **Step 1: 写配置测试**

创建 `backend/tests/test_config.py`，验证默认限制值、GPT 配置和上传目录可被环境变量覆盖。

- [ ] **Step 2: 实现配置与应用入口**

实现 Pydantic Settings、FastAPI 应用、CORS、健康检查。

- [ ] **Step 3: 运行后端基础测试**

Run: `cd backend && pytest`

### Task 3: 数据模型、迁移与种子账号

**Files:**
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/patent_check_task.py`
- Create: `backend/app/models/patent_check_file.py`
- Create: `backend/app/models/model_call_log.py`
- Create: `backend/app/scripts/seed_users.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`

- [ ] **Step 1: 写密码和用户模型测试**

验证密码哈希不等于明文、停用用户不可登录、普通用户角色为 `user`。

- [ ] **Step 2: 实现 SQLAlchemy 模型**

按 PRD 字段建立 users、patent_check_tasks、patent_check_files、model_call_logs。

- [ ] **Step 3: 实现种子脚本**

从环境变量预置 1 个 admin 和 2 个普通用户，重复执行保持幂等。

### Task 4: 认证接口

**Files:**
- Create: `backend/app/api/auth.py`
- Create: `backend/app/deps.py`
- Create: `backend/tests/test_auth.py`

- [ ] **Step 1: 写登录接口测试**

覆盖登录成功、密码错误、停用账号失败、`/api/auth/me` 返回当前用户。

- [ ] **Step 2: 实现 JWT HttpOnly Cookie 登录**

实现 `POST /api/auth/login`、`POST /api/auth/logout`、`GET /api/auth/me`。

### Task 5: PDF 抽取和任务接口

**Files:**
- Create: `backend/app/services/pdf_extractor.py`
- Create: `backend/app/services/patent_check_service.py`
- Create: `backend/app/api/patent_checks.py`
- Create: `backend/tests/test_patent_checks.py`

- [ ] **Step 1: 写文件校验测试**

覆盖非 PDF 拒绝、超 20MB 拒绝、必填文件缺失拒绝、空文本 PDF 返回扫描件提示。

- [ ] **Step 2: 实现 PDF 文本抽取**

使用 `pypdf` 提取可复制文本，返回文本和长度。

- [ ] **Step 3: 实现任务接口**

实现 `POST /api/patent-checks`、`GET /api/patent-checks`、`GET /api/patent-checks/{task_id}`、`GET /api/patent-checks/{task_id}/report`、`POST /api/patent-checks/{task_id}/retry`。

### Task 6: Worker 和模型调用

**Files:**
- Create: `backend/app/services/model_client.py`
- Create: `backend/app/services/prompt_loader.py`
- Create: `backend/app/worker.py`
- Create: `backend/prompts/check_patent.md`
- Create: `backend/tests/test_worker.py`

- [ ] **Step 1: 复制审查模板**

将 `skills/check-patent.md` 复制为 `backend/prompts/check_patent.md`，由后端固定读取。

- [ ] **Step 2: 写模型客户端测试**

覆盖缺少 API key、超时、非 2xx 响应、正常返回 Markdown。

- [ ] **Step 3: 实现两阶段 Worker**

Worker 将任务置为 running，调用第一阶段和第二阶段，保存 `stage_one_result` 与 `final_report`，失败时写 `failed` 和用户可读错误，最后清理临时输入。

### Task 7: 前端应用

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/src/app/login/page.tsx`
- Create: `frontend/src/app/workspace/page.tsx`
- Create: `frontend/src/app/tasks/page.tsx`
- Create: `frontend/src/app/tasks/[id]/page.tsx`
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/components/`

- [ ] **Step 1: 建立 Next.js 与 Tailwind 骨架**

配置 TypeScript、Tailwind、App Router 和 API 代理地址。

- [ ] **Step 2: 实现登录与业务页面**

实现登录页、工作台、历史列表、任务详情和报告展示。

- [ ] **Step 3: 实现复制和下载**

任务详情页支持复制完整 Markdown 和下载 `.md` 文件。

### Task 8: Docker、Nginx 与部署文档

**Files:**
- Create: `docker-compose.yml`
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `deploy/nginx/default.conf`
- Create: `docs/deployment.md`
- Create: `docs/operations.md`

- [ ] **Step 1: 编排本地服务**

Compose 启动 postgres、redis、backend、worker、frontend、nginx。

- [ ] **Step 2: 写部署文档**

覆盖 ECS、DNS、HTTPS、环境变量、启动、升级和回滚。

### Task 9: 验证与提交

**Files:**
- Modify: all touched files

- [ ] **Step 1: 运行后端测试**

Run: `cd backend && pytest`

- [ ] **Step 2: 运行前端检查**

Run: `cd frontend && npm run lint && npm run typecheck`

- [ ] **Step 3: 运行 Docker 验证**

Run: `docker compose config`

- [ ] **Step 4: 中文提交**

Run: `git add . && git commit -m "初始化专利审查系统 MVP"`

- [ ] **Step 5: 配置 GitHub 远端**

Run: `git remote add origin git@github.com:Zhoey33/patentcheckagent.git`

如果本机没有 GitHub SSH 权限，则保留命令和文档，不伪造推送完成。

## Plan Self-Review

- PRD 功能覆盖：登录、固定账号、PDF 上传、文本抽取、异步任务、GPT 调用、报告展示、历史记录、部署配置均有任务。
- 非目标遵守：不做公开注册、在线编辑、法律意见、管理员页面、OCR、PDF 导出。
- 安全覆盖：API key 不提交、`.env` 排除、HttpOnly Cookie、密码哈希、权限隔离。
- 外部依赖边界：GitHub 推送、阿里云上线、HTTPS 证书配置需要用户凭据或服务器状态，计划中明确为可执行步骤。
