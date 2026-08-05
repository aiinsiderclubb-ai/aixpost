# Facebook SaaS Platform - Production Docker Image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    DEBIAN_FRONTEND=noninteractive

# Set work directory
WORKDIR /app

# Install system dependencies for Selenium and Chrome
RUN apt-get update && apt-get install -y \
    # Chrome dependencies
    wget \
    gnupg \
    unzip \
    curl \
    xvfb \
    # PostgreSQL client
    postgresql-client \
    # Build tools
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver
RUN CHROMEDRIVER_VERSION=`curl -sS chromedriver.storage.googleapis.com/LATEST_RELEASE` \
    && wget -O /tmp/chromedriver.zip http://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip \
    && unzip /tmp/chromedriver.zip chromedriver -d /usr/local/bin/ \
    && rm /tmp/chromedriver.zip \
    && chmod +x /usr/local/bin/chromedriver

# Copy requirements first (for better Docker layer caching)
COPY requirements_saas.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements_saas.txt

# Create application user (security best practice)
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Create necessary directories
RUN mkdir -p /app/uploads \
             /app/screenshots \
             /app/facebook_sessions \
             /app/logs \
    && chown -R appuser:appuser /app

# Copy application code
COPY . .

# Set proper permissions
RUN chown -R appuser:appuser /app \
    && chmod +x run.py

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Wait for database\n\
echo "Waiting for database..."\n\
while ! pg_isready -h ${DATABASE_HOST:-postgres} -p ${DATABASE_PORT:-5432} -U ${DATABASE_USER:-facebook_user}; do\n\
  sleep 1\n\
done\n\
echo "Database is ready!"\n\
\n\
# Run database migrations\n\
echo "Running database migrations..."\n\
python run.py init-db || echo "Database already initialized"\n\
\n\
# Start the application\n\
echo "Starting application..."\n\
exec "$@"\n\
' > /app/entrypoint.sh \
    && chmod +x /app/entrypoint.sh \
    && chown appuser:appuser /app/entrypoint.sh

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Expose port
EXPOSE 5000

# Set entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "--keepalive", "2", "app:create_app()"]

# Multi-stage build for production optimization (optional)
FROM python:3.11-slim as base

# Production image
FROM base as production
ENV FLASK_ENV=production
COPY --from=base /app /app
WORKDIR /app
USER appuser
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "app:create_app()"]

# Development image
FROM base as development
ENV FLASK_ENV=development
ENV FLASK_DEBUG=True
COPY --from=base /app /app
WORKDIR /app
USER appuser
CMD ["python", "run.py", "runserver", "--host", "0.0.0.0", "--port", "5000"] 