FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir .
RUN playwright install chromium --with-deps

COPY config/ config/

RUN mkdir -p data

ENV NEWS_LOG_LEVEL=INFO

CMD ["python", "-m", "news_aggregator"]
