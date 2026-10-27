from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "AI20K Agent"
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:3000"

    # LLM
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    model_name: str = "openai/gpt-4o-mini"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    # Database — lưu đồ thị lineage (storage_service.py), xem PRD.md mục 8
    database_url: str = "postgresql://lineage:lineage@localhost:5432/lineage"

    # Vector Store
    chroma_persist_dir: str = "./data/chroma"

    # Table description + semantic search
    description_enabled: bool = False
    embedding_url: str = "http://localhost:8080"
    embedding_dim: int = Field(default=1024, ge=1)
    embedding_timeout_seconds: float = Field(default=30.0, gt=0)
    description_confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)

    # Lineage Agent (PRD.md mục 8)
    confidence_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    sql_dialect: str = "postgres"

    # Chatbot lineage
    chat_max_edges: int = Field(default=80, ge=1)
    chat_max_definition_chars: int = Field(default=4000, ge=0)
    chat_default_traverse_depth: int = Field(default=2, ge=1)
    chat_answer_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    chat_session_ttl_seconds: int = Field(default=1800, ge=60)
    chat_max_history_turns: int = Field(default=6, ge=1)
    chat_max_sessions: int = Field(default=500, ge=1)
    chat_max_paths: int = Field(default=3, ge=1, le=10)
    chat_max_tool_calls: int = Field(default=6, ge=1)
    chat_max_agent_steps: int = Field(default=4, ge=1)
    chat_search_limit: int = Field(default=20, ge=1, le=100)
    chat_trace_enabled: bool = True
    chat_verify_mode: Literal["warn", "replace"] = "warn"

    # Auto re-ingest — tự động phát hiện file .sql đổi và re-ingest lại, không
    # cần user chủ động bấm nút mỗi lần. Mặc định TẮT: chỉ có ý nghĩa với
    # ingest theo path server bền vững (POST /ingest), vô hại với path upload
    # (thư mục tạm bị xoá ngay sau request nên tự bị bỏ qua ở watcher).
    auto_reingest_enabled: bool = False
    auto_reingest_interval_seconds: int = Field(default=300, ge=30)

    # Observability — LangSmith tracing, tắt mặc định (giống description_enabled/
    # auto_reingest_enabled) để không âm thầm gửi trace mỗi khi ai đó chạy
    # `pytest`/dev server mà chưa cố ý bật.
    langchain_tracing_enabled: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "ai20k-agent"
    langchain_endpoint: str = "https://api.smith.langchain.com"

    # Auth — JWT phiên đăng nhập + Google Sign-In (src/services/auth_service.py)
    jwt_secret: str = "dev-insecure-change-me-in-production-please"
    jwt_expires_minutes: int = Field(default=1440, ge=1)
    google_client_id: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
