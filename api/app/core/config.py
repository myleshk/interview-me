"""Application configuration via Pydantic Settings.

All values are read from environment variables or a ``.env`` file.
Never hard-code secrets — use ``api/.env`` instead.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralised, typed configuration for the interview-me API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── DeepSeek / OpenAI-compatible LLM ───────────────────
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-v4-flash"

    # ── Qdrant Vector Store ────────────────────────────────
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_name: str = "interview_me"
    qdrant_api_key: str | None = None

    # ── Embedding Service ──────────────────────────────────
    embedding_service_url: str = "http://embedding:8080"
    embedding_dim: int = 384

    # ── API ────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False

    # ── Security ───────────────────────────────────────────
    api_key: str | None = None  # Optional bearer-token gate
    allowed_origins: list[str] = ["*"]

    # ── Rate Limiting ──────────────────────────────────────
    rate_limit_requests: int = 30       # max requests per window
    rate_limit_window_seconds: int = 60  # window size in seconds


settings = Settings()
