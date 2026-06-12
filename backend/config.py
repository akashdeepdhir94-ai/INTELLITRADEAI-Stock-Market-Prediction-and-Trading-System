"""
Centralised configuration — reads from environment variables with sane defaults.
Copy .env.example to .env and set your values.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./intellitrade.db"

    # JWT
    secret_key: str = "CHANGE_ME_IN_PRODUCTION_use_openssl_rand_hex_32"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # API rate-limiting
    rate_limit_per_minute: str = "60/minute"

    # yfinance / data
    default_history_period: str = "6mo"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
