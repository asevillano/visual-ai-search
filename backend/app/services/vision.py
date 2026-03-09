"""Azure AI Vision 4.0 — image analysis + multimodal embeddings (image & text).

Uses AzureCliCredential (Entra ID) for token acquisition.
All heavy resources (credential, HTTP client, token, URLs) are created once
at startup and reused across requests.
"""

from __future__ import annotations
import logging
import time
import httpx
from azure.identity import AzureCliCredential
from app.config import get_settings

logger = logging.getLogger("app.vision")

# ---------------------------------------------------------------------------
# Module-level state (populated once by init(), released by close())
# ---------------------------------------------------------------------------

_credential: AzureCliCredential | None = None
_http_client: httpx.AsyncClient | None = None
_VISION_SCOPE = "https://cognitiveservices.azure.com/.default"

# Pre-cached token (avoids blocking the event loop on every call)
_cached_token: str = ""
_token_expires_on: float = 0.0          # epoch seconds
_TOKEN_REFRESH_MARGIN = 120             # refresh 2 min before expiry

# Pre-built URLs (avoid string formatting on every call)
_url_analyze: str = ""
_url_vectorize_image: str = ""
_url_vectorize_text: str = ""
_PARAMS_ANALYZE = {"api-version": "2024-02-01", "features": "caption,tags,objects", "language": "en"}
_PARAMS_EMBED   = {"api-version": "2024-02-01", "model-version": "2023-04-15"}


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

async def init() -> None:
    """Create credential + HTTP client, pre-build URLs, warm-up token & connection."""
    global _credential, _http_client
    global _url_analyze, _url_vectorize_image, _url_vectorize_text

    settings = get_settings()
    base = settings.azure_vision_endpoint.rstrip("/")
    logger.info("Vision init — endpoint=%s", base)

    # 1. Pre-build URLs
    _url_analyze         = f"{base}/computervision/imageanalysis:analyze"
    _url_vectorize_image = f"{base}/computervision/retrieval:vectorizeImage"
    _url_vectorize_text  = f"{base}/computervision/retrieval:vectorizeText"

    # 2. AzureCliCredential (fast — no fallback chain) + HTTP client
    _credential = AzureCliCredential(tenant_id=settings.azure_tenant_id, process_timeout=30)
    _http_client = httpx.AsyncClient(
        timeout=60,
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    )

    # 3. Warm-up: acquire first token (sync call, ~1-4s once, then cached)
    _refresh_token()

    # 4. Warm-up: establish TCP+TLS connection to Vision endpoint
    try:
        t0 = time.perf_counter()
        probe = await _http_client.post(
            _url_vectorize_text,
            params=_PARAMS_EMBED,
            headers={"Authorization": f"Bearer {_cached_token}", "Content-Type": "application/json"},
            json={"text": "warmup"},
        )
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("Vision init OK — connection warm-up %d (%.0f ms)", probe.status_code, elapsed)
    except Exception as exc:
        logger.warning("Vision init — warm-up probe failed (non-fatal): %s", exc)


async def close() -> None:
    """Release HTTP client."""
    global _http_client, _credential, _cached_token, _token_expires_on
    if _http_client:
        await _http_client.aclose()
        _http_client = None
    _credential = None
    _cached_token = ""
    _token_expires_on = 0.0
    logger.info("Vision resources closed")


# ---------------------------------------------------------------------------
# Token management — sync credential.get_token() offloaded to a thread
# ---------------------------------------------------------------------------

def _refresh_token() -> None:
    """Fetch a new token (sync) and cache it locally.

    Uses sync AzureCliCredential.get_token() which calls `az` CLI.
    Fast (~100ms when token is cached by CLI, ~1-4s first time).
    Retries once on timeout / transient failures.
    """
    global _cached_token, _token_expires_on
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            token = _credential.get_token(_VISION_SCOPE)
            _cached_token = token.token
            _token_expires_on = token.expires_on
            logger.debug("Token refreshed (expires=%s)", _token_expires_on)
            return
        except Exception as exc:
            last_exc = exc
            logger.warning("Token refresh attempt %d failed: %s", attempt + 1, exc)
            if attempt == 0:
                import time as _time
                _time.sleep(1)          # brief pause before retry
    raise last_exc  # type: ignore[misc]


async def _get_bearer_token() -> str:
    """Return cached bearer token, refreshing only when close to expiry.

    Refresh is sync (~100ms from CLI cache) and only happens every ~55 min.
    """
    if time.time() > (_token_expires_on - _TOKEN_REFRESH_MARGIN):
        _refresh_token()
    return _cached_token


# ---------------------------------------------------------------------------
# Image Analysis  (caption, tags, objects)
# ---------------------------------------------------------------------------

async def analyze_image(image_bytes: bytes) -> dict:
    """Call Azure AI Vision 4.0 Image Analysis API.

    Returns dict with keys: caption, tags, objects.
    """
    t0 = time.perf_counter()
    logger.info("analyze_image — %d bytes", len(image_bytes))
    headers = {
        "Authorization": f"Bearer {await _get_bearer_token()}",
        "Content-Type": "application/octet-stream",
    }

    resp = await _http_client.post(_url_analyze, params=_PARAMS_ANALYZE, headers=headers, content=image_bytes)
    if resp.status_code != 200:
        logger.error("analyze_image HTTP %d — %s", resp.status_code, resp.text[:500])
    resp.raise_for_status()
    data = resp.json()

    caption = ""
    if "captionResult" in data:
        caption = data["captionResult"].get("text", "")

    tags: list[str] = []
    if "tagsResult" in data:
        tags = [t["name"] for t in data["tagsResult"].get("values", []) if t.get("confidence", 0) > 0.5]

    objects: list[str] = []
    if "objectsResult" in data:
        objects = list({o["tags"][0]["name"] for o in data["objectsResult"].get("values", []) if o.get("tags")})

    elapsed = (time.perf_counter() - t0) * 1000
    logger.info("analyze_image OK (%.0f ms) — caption='%s', %d tags, %d objects",
                elapsed, caption, len(tags), len(objects))
    return {"caption": caption, "tags": tags, "objects": objects}


# ---------------------------------------------------------------------------
# Multimodal Embeddings  (image → 1024-d  or  text → 1024-d)
# ---------------------------------------------------------------------------

async def vectorize_image(image_bytes: bytes) -> list[float]:
    """Get 1024-d embedding for an image via AI Vision multimodal embeddings."""
    t0 = time.perf_counter()
    logger.info("vectorize_image — %d bytes", len(image_bytes))
    headers = {
        "Authorization": f"Bearer {await _get_bearer_token()}",
        "Content-Type": "application/octet-stream",
    }

    resp = await _http_client.post(_url_vectorize_image, params=_PARAMS_EMBED, headers=headers, content=image_bytes)
    if resp.status_code != 200:
        logger.error("vectorize_image HTTP %d — %s", resp.status_code, resp.text[:500])
    resp.raise_for_status()
    data = resp.json()

    elapsed = (time.perf_counter() - t0) * 1000
    logger.info("vectorize_image OK (%.0f ms) — %d-d vector", elapsed, len(data["vector"]))
    return data["vector"]


async def vectorize_text(text: str) -> list[float]:
    """Get 1024-d embedding for text via AI Vision multimodal embeddings.

    This uses the SAME embedding space as vectorize_image — so text ↔ image
    similarity works natively.
    """
    t0 = time.perf_counter()
    logger.info("vectorize_text — '%s'", text[:120])
    headers = {
        "Authorization": f"Bearer {await _get_bearer_token()}",
        "Content-Type": "application/json",
    }
    body = {"text": text}

    resp = await _http_client.post(_url_vectorize_text, params=_PARAMS_EMBED, headers=headers, json=body)
    if resp.status_code != 200:
        logger.error("vectorize_text HTTP %d — %s", resp.status_code, resp.text[:500])
    resp.raise_for_status()
    data = resp.json()

    elapsed = (time.perf_counter() - t0) * 1000
    logger.info("vectorize_text OK (%.0f ms) — %d-d vector", elapsed, len(data["vector"]))
    return data["vector"]
