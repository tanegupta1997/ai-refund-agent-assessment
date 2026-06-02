from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OPENAI_API_KEY: str = ""
    MODEL_NAME: str = "gpt-4o-mini"
    LLM_BASE_URL: str | None = None
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 1000
    LLM_MAX_RETRIES: int = 2
    DATABASE_URL: str = "sqlite:///./refund_agent.db"
    ADMIN_SECRET: str = "changeme"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
