# BadCaseDoctor 主 Flask 应用
# 构建: docker build -t badcase-doctor:latest .
# 运行: docker run -d -p 5000:5000 --env-file .env badcase-doctor:latest

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    FLASK_ENV=production \
    FLASK_DEBUG=0 \
    FLASK_HOST=0.0.0.0 \
    PORT=5000 \
    WSGI_HOST=0.0.0.0 \
    WSGI_PORT=5000 \
    WSGI_TIMEOUT=3600 \
    WSGI_THREADS=8 \
    TRUST_PROXY=1 \
    CORS_ALLOW_NULL_ORIGIN=1 \
    BADCASE_MANAGE_LOCAL_PROXY=0

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        gcc \
        default-libmysqlclient-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:5000/health || exit 1

CMD ["python", "server_wsgi.py"]
