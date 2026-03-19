"""Azure OpenAI — text-embedding-3-large (3072-d).

Uses DefaultAzureCredential (Entra ID) instead of API keys.
"""

from __future__ import annotations
import logging
import time
from openai import AsyncAzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from app.config import get_settings

logger = logging.getLogger("app.openai_embeddings")

_client: AsyncAzureOpenAI | None = None
_credential: DefaultAzureCredential | None = None
_deployment: str = ""


async def init() -> None:
    """Eagerly create credential + AsyncAzureOpenAI client and warm up token."""
    global _client, _credential, _deployment
    settings = get_settings()
    _deployment = settings.azure_openai_embedding_deployment
    logger.info("OpenAI init — endpoint=%s, deployment=%s",
                settings.azure_openai_endpoint, _deployment)
    _credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(
        _credential, "https://cognitiveservices.azure.com/.default"
    )
    _client = AsyncAzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        azure_ad_token_provider=token_provider,
        api_version=settings.azure_openai_api_version,
    )

    # Warm-up: force first token acquisition so the first real request is fast
    try:
        import time as _time
        t0 = _time.perf_counter()
        _credential.get_token("https://cognitiveservices.azure.com/.default")
        elapsed = (_time.perf_counter() - t0) * 1000
        logger.info("OpenAI init OK — token warm-up (%.0f ms)", elapsed)
    except Exception as exc:
        logger.warning("OpenAI init — token warm-up failed (non-fatal): %s", exc)


async def close() -> None:
    """Close the AsyncAzureOpenAI client."""
    global _client
    if _client:
        await _client.close()
        _client = None
    logger.info("OpenAI resources closed")


async def embed_text(text: str) -> list[float]:
    """Return 3072-d embedding for a text string using text-embedding-3-large."""
    t0 = time.perf_counter()
    logger.info("embed_text — '%s'", text[:120])
    try:
        response = await _client.embeddings.create(
            model=_deployment,
            input=text,
        )
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("embed_text OK (%.0f ms) — %d-d vector", elapsed, len(response.data[0].embedding))
        return response.data[0].embedding
    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        logger.error("embed_text FAILED (%.0f ms): %s", elapsed, exc, exc_info=True)
        raise
