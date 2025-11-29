FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=esp_project.settings \
    CHROME_BIN=/usr/bin/chromium

WORKDIR /app

# System deps (only those you need)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc build-essential libpq-dev curl wget gnupg2 \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel cython \
 && pip install --no-cache-dir --retries 5 --timeout 120 -r requirements.txt

# Chromium + helpful runtime libs
RUN apt-get update \
 && apt-get install -y --no-install-recommends chromium \
    fonts-liberation libasound2 libnss3 libxss1 xdg-utils \
 && rm -rf /var/lib/apt/lists/*

# App code
COPY . .

# App dirs (own them before dropping privileges)
RUN mkdir -p /app/logs /app/media /app/static \
 && useradd -m appuser \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
# command is set in compose
