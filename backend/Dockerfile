# 这个文件用于构建 FastAPI API 与 RQ Worker 共用的后端镜像。

ARG PYTHON_BASE_IMAGE=python:3.12-slim
FROM ${PYTHON_BASE_IMAGE}

ARG CODEX_NPM_REGISTRY=https://registry.npmmirror.com
ARG DEBIAN_MIRROR=https://mirrors.tuna.tsinghua.edu.cn
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i \
        -e "s|http://deb.debian.org|${DEBIAN_MIRROR}|g" \
        /etc/apt/sources.list.d/debian.sources; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates nodejs npm unzip \
    && rm -rf /var/lib/apt/lists/*

RUN pip config set global.index-url "${PIP_INDEX_URL}"
RUN npm install --global --registry=${CODEX_NPM_REGISTRY} @openai/codex@0.154.0 \
    && codex --version

COPY backend/pyproject.toml /app/pyproject.toml
COPY backend/app /app/app
COPY skills /app/skills
COPY backend/alembic.ini /app/alembic.ini
COPY backend/alembic /app/alembic

RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
