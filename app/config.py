from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "llama3.2:3b"
    ollama_embedding_model: str = "nomic-embed-text"
    chroma_dir: Path = ROOT / ".chroma"
    top_k: int = Field(default=4, ge=1, le=20)
    max_agent_rounds: int = Field(default=4, ge=1, le=8)
    max_tool_calls: int = Field(default=10, ge=1, le=20)
    session_ttl_seconds: int = Field(default=1800, ge=60, le=86400)
    max_sessions: int = Field(default=50, ge=1, le=500)

    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
