import json
from functools import lru_cache
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "documents"
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    EMBEDDING_MODEL: str = "bge-m3:latest"
    EMBEDDING_DIMENSIONS: int = 1024
    LLM_MODEL: str = "gemma4:e4b"
    LLM_TEMPERATURE: float = 0.1
    LLM_TOP_P: float = 0.9
    LLM_NUM_PREDICT: int = 1024
    LLM_NUM_CTX: int = 65536
    LLM_THINK: bool = False
    CHUNK_MAX_TOKENS: int = 512
    CHUNK_MIN_CONTENT_LENGTH: int = 120
    TOP_K: int = 8
    MIN_SCORE: float = 0.35
    MAX_FILE_SIZE_MB: int = 100
    DB_PATH: str = "data/state.db"
    TEMP_DIR: str = "data/tmp"
    LLM_TIMEOUT: int = 900
    EMBEDDING_TIMEOUT: int = 600
    SUMMARY_MAP_BATCH_SIZE: int = 10
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
