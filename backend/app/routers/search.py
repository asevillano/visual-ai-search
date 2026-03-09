"""Search router — POST /api/search, GET /api/facets."""

from __future__ import annotations
import logging
from fastapi import APIRouter, UploadFile, File, Form
from typing import Optional

from app.models.search import SearchRequest, SearchResponse, FacetValue
from app.services.search import execute_search, get_facets

logger = logging.getLogger("app.search_router")
router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search(
    text_query: Optional[str] = Form(None),
    strategy: str = Form("vision"),
    filters: Optional[str] = Form(None),        # JSON string of filters
    page: int = Form(1),
    page_size: int = Form(20),
    image_file: Optional[UploadFile] = File(None),
):
    """Search images by text, image, or both."""
    import json

    has_image = image_file is not None and image_file.filename is not None
    logger.info("Search request — text=%r, strategy=%s, page=%d/%d, has_image=%s, filters=%s",
                text_query, strategy, page, page_size, has_image, filters)

    parsed_filters = None
    if filters:
        try:
            parsed_filters = json.loads(filters)
            logger.info("  Parsed filters: %s", parsed_filters)
        except json.JSONDecodeError as exc:
            logger.warning("  Invalid filters JSON (%s) — ignoring", exc)
            parsed_filters = None

    request = SearchRequest(
        text_query=text_query,
        strategy=strategy,  # type: ignore[arg-type]
        filters=parsed_filters,
        page=page,
        page_size=page_size,
    )

    image_bytes: bytes | None = None
    if image_file and image_file.content_type and image_file.content_type.startswith("image/"):
        image_bytes = await image_file.read()
        logger.info("  Image file: %s (%d bytes)", image_file.filename, len(image_bytes))

    try:
        response = await execute_search(request, image_bytes)
        logger.info("  Search complete — mode=%s", response.mode)
        if response.vision:
            logger.info("    Vision: %d results (total=%d)", len(response.vision.results), response.vision.total_count)
        if response.openai:
            logger.info("    OpenAI: %d results (total=%d)", len(response.openai.results), response.openai.total_count)
        return response
    except Exception as exc:
        logger.error("  Search FAILED: %s", exc, exc_info=True)
        raise


@router.get("/facets")
async def facets_endpoint() -> dict[str, list[FacetValue]]:
    """Return available facets from the index."""
    logger.info("Facets request")
    try:
        result = await get_facets()
        logger.info("  Facets returned: %s", {k: len(v) for k, v in result.items()})
        return result
    except Exception as exc:
        logger.error("  Facets FAILED: %s", exc, exc_info=True)
        raise
