# One image for the API, the Celery worker and Celery beat (different commands; see infra/deploy/compose.prod.yml).
# Build: docker build -t abos-backend backend   (EXTRAS=s3,monitoring adds boto3 / sentry-sdk)
FROM python:3.12-slim AS build
ARG EXTRAS=s3
WORKDIR /src
COPY pyproject.toml ./
COPY abos ./abos
RUN pip wheel --no-cache-dir --wheel-dir /wheels ".[${EXTRAS}]"

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ABOS_ENV=production \
    # Only these proxies may set X-Forwarded-For (client IPs feed rate limits and the audit log). Set it to the
    # reverse proxy / web container address(es) in your deployment.
    FORWARDED_ALLOW_IPS=127.0.0.1
RUN useradd --create-home --uid 10001 abos
WORKDIR /app
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
COPY alembic.ini ./
COPY alembic ./alembic
USER abos
EXPOSE 8470
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8470/api/health', timeout=4).status == 200 else 1)"
CMD ["uvicorn", "abos.main:app", "--host", "0.0.0.0", "--port", "8470", "--proxy-headers", "--no-server-header"]
