# 这个文件用于构建 FastAPI API 与 RQ Worker 共用的后端镜像。

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

COPY backend/pyproject.toml /app/pyproject.toml
COPY backend/app /app/app
COPY backend/prompts /app/prompts
COPY backend/alembic.ini /app/alembic.ini
COPY backend/alembic /app/alembic

RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
