# News Aggregator

News aggregator that scrapes multiple sources and posts to any output source you provide with.

## Features

- Scrapes any news sources
- Twitter/X feed scraping via Playwright
- Keyword filtering per source
- Deduplication via SQLite
- Docker deployment ready

## Quick Start

### Local Development

```bash
# Clone and setup
git clone git@github.com:danpasecinic/news-aggregator.git
cd news-aggregator

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
playwright install chromium

# Configure
cp .env.example .env
# Edit .env with your credentials

# Run once
python -m news_aggregator once

# Run scheduler
python -m news_aggregator
```

### Docker Deployment (Recommended)

```bash
# Configure
cp .env.example .env
# Edit .env with your credentials

# Build and run
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

## Configuration

### Adding Sources

Edit `config/sources.yaml`:

```yaml
sources:
  - name: "My Source"
    url: "https://example.com/news"
    type: "web"
    selectors:
      container: ".article"
      title: "h2 a"
      link: "h2 a"
      time: ".date"
    link_prefix: "https://example.com"
    keywords: [ finance" ]  # empty = all articles
    enabled: true
```

## Commands

```bash
python -m news_aggregator          # Run scheduler
python -m news_aggregator once     # Single scrape cycle
python -m news_aggregator stats    # Show statistics
python -m news_aggregator cleanup  # Clean old articles
```
