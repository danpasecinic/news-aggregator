from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


class ScrapingConfig(BaseModel):
    interval_minutes: int = 10
    request_timeout: int = 30
    max_articles_per_source: int = 20
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


class StorageConfig(BaseModel):
    database_path: str = "data/news.db"
    keep_days: int = 7


class TelegramConfig(BaseModel):
    message_format: str = "📰 *{source}*\n{title}\n🔗 {url}\n⏰ {timestamp}"


class SourceSelectors(BaseModel):
    container: str
    title: str
    link: str
    time: str | None = None


class SourceConfig(BaseModel):
    name: str
    url: str | None = None
    type: str = "web"
    selectors: SourceSelectors | None = None
    link_prefix: str = ""
    keywords: list[str] = Field(default_factory=list)
    enabled: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = ""
    telegram_channel_id: str = ""
    twitter_username: str = ""
    twitter_password: str = ""
    scrape_interval: int = 10
    log_level: str = "INFO"

    scraping: ScrapingConfig = Field(default_factory=ScrapingConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)


class SourcesConfig(BaseModel):
    sources: list[SourceConfig] = Field(default_factory=list)


def load_sources(path: str = "config/sources.yaml") -> list[SourceConfig]:
    config_path = Path(path)
    if not config_path.exists():
        return []
    with open(config_path) as f:
        data = yaml.safe_load(f) or {}
    config = SourcesConfig.model_validate(data)
    return [s for s in config.sources if s.enabled]


settings = Settings()
