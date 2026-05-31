FROM python:3.11-slim

ENV TZ=Asia/Shanghai \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.docker.txt /app/requirements.docker.txt

RUN pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple -r /app/requirements.docker.txt

COPY . /app

# 创建 drf-yasg 静态文件目录并复制静态文件
RUN mkdir -p /app/static/drf-yasg && \
    cp -r /usr/local/lib/python3.11/site-packages/drf_yasg/static/drf-yasg/* /app/static/drf-yasg/

EXPOSE 8000

CMD ["sh", "-c", "DISABLE_SCHEDULER=1 python manage.py migrate && DISABLE_SCHEDULER=1 python manage.py collectstatic --noinput && gunicorn --bind 0.0.0.0:8000 djangoProject.wsgi:application"]
