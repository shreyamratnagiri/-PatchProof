FROM python:3.12.8-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY packages ./packages
COPY apps/api ./apps/api
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY README.md ./
RUN pip install --no-cache-dir . && \
    groupadd --system --gid 10001 patchproof && \
    useradd --system --uid 10001 --gid 10001 --no-create-home patchproof && \
    install -d -o 10001 -g 10001 -m 0700 /var/lib/patchproof
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn","apps.api.main:app","--host","0.0.0.0","--port","8000"]
