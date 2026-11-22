# ShipProof Production Container (FastAPI + Acme Store + Node 20 + Kane CLI + Chromium runtime)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=8000 \
    KANE_CLI_PATH="/usr/local/bin/kane-cli" \
    ENVIRONMENT="production" \
    ALLOW_LOCAL_TARGETS="true" \
    WORKER_EXECUTION_MODE="subprocess"

# 1. Install system utilities, curl, gnupg, git, and Chromium runtime libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    procps \
    git \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    fonts-liberation \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Node.js 20 from NodeSource
RUN mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# 3. Install Kane CLI globally
RUN npm install -g @testmuai/kane-cli

WORKDIR /app

# 4. Install Python dependencies
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# 5. Copy application source
COPY . /app

# 6. Ensure persistent data directories and executable permissions
RUN mkdir -p /app/backend/data /app/backend/evidence && \
    chmod +x /app/scripts/start_production.sh 2>/dev/null || true

EXPOSE 8000 3005

CMD ["/bin/bash", "/app/scripts/start_production.sh"]
