"""GPT-4.1 Vision — custom image analysis with a configurable prompt.

Uses the same AsyncAzureOpenAI client pattern as openai_embeddings.py.
The IMAGE_ANALYSIS_PROMPT constant controls what information is extracted
from each image.  Edit it to adapt the system to any domain (vehicles,
medical, retail, construction…).
"""

from __future__ import annotations
import base64
import json
import logging
import time
from openai import AsyncAzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from app.config import get_settings

logger = logging.getLogger("app.gpt_analysis")

# ---------------------------------------------------------------------------
# ★  EDITABLE PROMPT  ★
#
# This system prompt defines WHAT information GPT-4.1 extracts from every
# uploaded image.  Change it freely to match your domain.
#
# The model MUST return valid JSON with at least these keys:
#   - caption   (str):  one-sentence description
#   - tags      (list[str]):  relevant keywords / labels
#   - objects   (list[str]):  distinct objects detected
#   - details   (str):  free-form detailed analysis (this is what gets
#                        embedded by OpenAI for semantic search)
# ---------------------------------------------------------------------------

IMAGE_ANALYSIS_PROMPT = """\
You are an expert image analyst.  Examine the provided image and return a
JSON object with the following keys (no markdown, no code fences, just raw JSON):

{
  "caption": "A single sentence describing the image.",
  "tags": ["keyword1", "keyword2", "..."],
  "objects": ["object1", "object2", "..."],
  "details": "A detailed paragraph describing everything relevant you see."
}

Guidelines for the analysis:
- **caption**: concise, one sentence.
- **tags**: include colours, materials, environment, weather, mood, brands,
  and any domain-specific labels (e.g. damage type, condition).
- **objects**: every distinct object/entity you can identify.
- **details**: this is the MOST IMPORTANT field.  Write a rich, detailed
  paragraph that covers:
    • General scene description
    • Condition and state of the main subject (scratches, dents, missing
      parts, wear, rust, cracks, stains…)
    • Colours, textures, lighting
    • Spatial relationships ("on the left", "in the background"…)
    • Any text, logos, or numbers visible
    • Anything unusual or noteworthy

Be thorough — the "details" field will be used for semantic search, so the
more descriptive you are, the better the search results will be.

Return ONLY the JSON object, nothing else.
"""

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_client: AsyncAzureOpenAI | None = None
_credential: DefaultAzureCredential | None = None
_deployment: str = ""


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

async def init() -> None:
    """Create credential + AsyncAzureOpenAI client for chat completions and warm up token."""
    global _client, _credential, _deployment
    settings = get_settings()
    _deployment = settings.azure_openai_chat_deployment
    logger.info("GPT Analysis init — endpoint=%s, deployment=%s",
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

    # Warm-up: force first token acquisition
    try:
        import time as _time
        t0 = _time.perf_counter()
        _credential.get_token("https://cognitiveservices.azure.com/.default")
        elapsed = (_time.perf_counter() - t0) * 1000
        logger.info("GPT Analysis init OK — token warm-up (%.0f ms)", elapsed)
    except Exception as exc:
        logger.warning("GPT Analysis init — token warm-up failed (non-fatal): %s", exc)


async def close() -> None:
    """Close the client."""
    global _client
    if _client:
        await _client.close()
        _client = None
    logger.info("GPT Analysis resources closed")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def analyze_image(image_bytes: bytes, content_type: str = "image/jpeg") -> dict:
    """Send an image to GPT-4.1 Vision and return structured analysis.

    Returns dict with keys: caption, tags, objects, details.
    Falls back to empty/default values on parse errors.
    """
    t0 = time.perf_counter()
    logger.info("analyze_image (GPT) — %d bytes, type=%s", len(image_bytes), content_type)

    # Encode image as data-URI for the vision message
    b64 = base64.b64encode(image_bytes).decode("ascii")
    media_type = content_type if content_type else "image/jpeg"
    data_uri = f"data:{media_type};base64,{b64}"

    try:
        response = await _client.chat.completions.create(
            model=_deployment,
            messages=[
                {"role": "system", "content": IMAGE_ANALYSIS_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this image:"},
                        {"type": "image_url", "image_url": {"url": data_uri, "detail": "high"}},
                    ],
                },
            ],
            temperature=0.2,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("analyze_image (GPT) OK (%.0f ms) — tokens: prompt=%s, completion=%s",
                     elapsed,
                     response.usage.prompt_tokens if response.usage else "?",
                     response.usage.completion_tokens if response.usage else "?")

        data = json.loads(raw)
        result = {
            "caption":  data.get("caption", ""),
            "tags":     data.get("tags", []),
            "objects":  data.get("objects", []),
            "details":  data.get("details", ""),
        }
        logger.info("  caption='%s'  tags=%d  objects=%d  details=%d chars",
                     result["caption"][:80], len(result["tags"]),
                     len(result["objects"]), len(result["details"]))
        return result

    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        logger.error("analyze_image (GPT) FAILED (%.0f ms): %s", elapsed, exc, exc_info=True)
        raise
