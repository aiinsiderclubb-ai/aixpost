# AIPostX — production image with Chrome for Selenium workers
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    FLASK_DEBUG=false \
    DEBIAN_FRONTEND=noninteractive \
    PORT=8080

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg unzip curl xvfb x11vnc novnc websockify fluxbox \
    fonts-liberation libasound2 libatk-bridge2.0-0 libatk1.0-0 libcups2 \
    libdbus-1-3 libdrm2 libgbm1 libgtk-3-0 libnspr4 libnss3 libx11-xcb1 \
    libxcomposite1 libxdamage1 libxrandr2 xdg-utils \
    gcc g++ \
    && mkdir -p /etc/apt/keyrings \
    && wget -qO- https://dl.google.com/linux/linux_signing_key.pub \
       | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
       > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn eventlet psycopg2-binary

RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && mkdir -p /app/uploads /app/screenshots /app/user_data /app/data /app/logs /app/tmp \
    && chown -R appuser:appuser /app

COPY . .
RUN chmod +x /app/scripts/start_web.sh /app/scripts/start_worker.sh /app/scripts/start_browser_worker.sh \
    && chown -R appuser:appuser /app

# Chrome needs writable dirs; keep root for Xvfb on workers (override in web if needed).
USER root

EXPOSE 8080

# Default: web. Override dockerCommand for workers.
CMD ["bash", "/app/scripts/start_web.sh"]
