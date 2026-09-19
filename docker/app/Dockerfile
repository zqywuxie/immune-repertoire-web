FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLBACKEND=Agg MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk libgomp1 default-jre-headless libreoffice-impress && rm -rf /var/lib/apt/lists/*
COPY flask_app/requirements.txt flask_app/requirements.txt
COPY docker/app/requirements.txt docker/app/requirements.txt
RUN pip install --no-cache-dir -r docker/app/requirements.txt
COPY flask_app/ flask_app/
COPY analysis_workers/ analysis_workers/
COPY scripts/ scripts/
COPY docker/app/ docker/app/
RUN useradd --uid 10001 --user-group --create-home --shell /usr/sbin/nologin immune \
    && mkdir -p /app/flask_app/data /app/tmp \
    && chown -R 10001:10001 /app/flask_app/data /app/tmp
ENV HOME=/home/immune
USER 10001:10001
EXPOSE 5000
# Legacy task registries are process-local: keep one worker until migrated.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "--timeout", "600", "--access-logfile", "-", "flask_app.app:app"]
