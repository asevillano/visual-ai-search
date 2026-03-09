"""Configuration — Pydantic Settings loaded from environment / .env."""

from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache

# .env lives at the project root (two levels up from this file)
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    # Azure Tenant (for AzureCliCredential)
    azure_tenant_id: str = ""

    # Azure AI Search
    azure_search_endpoint: str = ""
    azure_search_api_key: str = ""
    azure_search_index_name: str = "visual-search-index"

    # Azure AI Vision (image analysis + multimodal embeddings) — uses DefaultAzureCredential (Entra ID)
    azure_vision_endpoint: str = ""

    # Azure OpenAI — uses DefaultAzureCredential (Entra ID)
    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_embedding_deployment: str = "text-embedding-3-large"
    azure_openai_chat_deployment: str = "gpt-4.1"

    # Azure Blob Storage
    azure_storage_connection_string: str = ""
    azure_storage_container_originals: str = "originals"
    azure_storage_container_thumbnails: str = "thumbnails"

    # App
    backend_port: int = 8000
    frontend_url: str = "http://localhost:5173"

    # Search strategy exposed to frontend: "all" (show selector), "vision", or "openai"
    search_strategy: str = "all"

    model_config = {"env_file": str(_ENV_FILE), "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
