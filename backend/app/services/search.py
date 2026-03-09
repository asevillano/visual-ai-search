"""Search execution — Strategy A (vision), Strategy B (openai), and Compare mode."""

from __future__ import annotations
import asyncio
import logging
import time
from azure.search.documents.aio import SearchClient
from azure.search.documents.models import VectorizableTextQuery, VectorizedQuery
from azure.core.credentials import AzureKeyCredential

from app.config import get_settings
from app.models.search import (
    SearchRequest,
    SearchResponse,
    SearchResultSet,
    SearchResultItem,
    FacetValue,
)
from app.services import vision as vision_svc
from app.services import openai_embeddings as openai_svc
from app.utils.thumbnails import resize_for_vectorization
from app.services.blob_storage import refresh_sas_url

logger = logging.getLogger("app.search")

_search_client: SearchClient | None = None


def init() -> None:
    """Eagerly create the async SearchClient for queries."""
    global _search_client
    s = get_settings()
    logger.info("Search init — endpoint=%s, index=%s", s.azure_search_endpoint, s.azure_search_index_name)
    _search_client = SearchClient(
        endpoint=s.azure_search_endpoint,
        index_name=s.azure_search_index_name,
        credential=AzureKeyCredential(s.azure_search_api_key),
    )
    logger.info("Search init OK")


async def close() -> None:
    """Close the async SearchClient."""
    global _search_client
    if _search_client:
        await _search_client.close()
        _search_client = None
    logger.info("Search client closed")


# ---------------------------------------------------------------------------
# Facet definitions used in every query
# ---------------------------------------------------------------------------
FACET_SPECS = [
    "tags,count:20",
    "objects,count:20",
    "contentType",
]

# ---------------------------------------------------------------------------
# OData filter builder
# ---------------------------------------------------------------------------


def _build_filter(filters: dict[str, list[str]] | None) -> str | None:
    if not filters:
        return None
    clauses: list[str] = []
    for field, values in filters.items():
        if not values:
            continue
        if field in ("tags", "objects"):
            sub = " or ".join(f"{field}/any(t: t eq '{v}')" for v in values)
            clauses.append(f"({sub})")
        else:
            sub = " or ".join(f"{field} eq '{v}'" for v in values)
            clauses.append(f"({sub})")
    return " and ".join(clauses) if clauses else None


# ---------------------------------------------------------------------------
# Score normalisation → percentage (0-100)
#
# Azure AI Search returns different score scales depending on the query type:
#   • Vector-only (cosine):  0.0 – 1.0
#   • BM25 full-text only:   0.0 – unbounded (typically 0-30)
#   • Hybrid RRF:            0.0 – N/(k+1)  where k=60, N=num_retrievers
# ---------------------------------------------------------------------------

def _normalize_score(score: float | None, *, mode: str = "vector", num_retrievers: int = 1) -> float:
    """Convert a raw @search.score to a 0-100 relevance percentage.

    Args:
        score:  Raw score from Azure AI Search.
        mode:   "vector" | "hybrid" | "bm25".
        num_retrievers:  Number of retrieval sources in hybrid/RRF mode
                         (e.g. 1 BM25 + 2 vector queries = 3).
    """
    if score is None:
        return 0.0

    if mode == "vector":
        # Cosine similarity: already 0.0 – 1.0
        return round(max(0.0, min(score * 100, 100.0)), 1)

    if mode == "hybrid":
        # RRF with k=60 (Azure AI Search default).
        # Max possible = num_retrievers / (60 + 1).
        # Normalize so that a perfect rank-1 in all retrievers → 100%.
        max_rrf = num_retrievers / 61.0
        pct = (score / max_rrf) * 100 if max_rrf > 0 else 0.0
        return round(max(0.0, min(pct, 100.0)), 1)

    if mode == "bm25":
        # BM25 is unbounded; use sigmoid mapping  score/(1+score) → [0,1)
        pct = (score / (1.0 + score)) * 100
        return round(max(0.0, min(pct, 100.0)), 1)

    # Fallback — treat as cosine
    return round(max(0.0, min(score * 100, 100.0)), 1)


# ---------------------------------------------------------------------------
# Vector pre-computation — compute all needed vectors once, in parallel
# ---------------------------------------------------------------------------

async def _precompute_vectors(
    text_query: str | None,
    image_bytes: bytes | None,
    strategies: list[str],
) -> dict[str, list[float]]:
    """Return a dict with pre-computed vectors keyed by purpose.

    Keys: 'vision_text', 'vision_image', 'openai_text'
    Runs all vectorisation calls in parallel to minimise latency.
    """
    tasks: dict[str, asyncio.Task] = {}

    need_vision = any(s == "vision" for s in strategies)
    need_openai = any(s == "openai" for s in strategies)

    # Pre-warm the Vision token so parallel coroutines don't block on credential lock
    if need_vision and (text_query or image_bytes):
        await vision_svc._get_bearer_token()

    if text_query and need_vision:
        tasks["vision_text"] = asyncio.ensure_future(vision_svc.vectorize_text(text_query))
    if text_query and need_openai:
        tasks["openai_text"] = asyncio.ensure_future(openai_svc.embed_text(text_query))
    if image_bytes and (need_vision or need_openai):
        # Resize to ≤512px for vectorization — saves massive network + API time
        small = resize_for_vectorization(image_bytes)
        logger.info("  Image resized for vectorization: %d → %d bytes", len(image_bytes), len(small))
        tasks["vision_image"] = asyncio.ensure_future(vision_svc.vectorize_image(small))

    if tasks:
        results = await asyncio.gather(*tasks.values())
        return dict(zip(tasks.keys(), results))
    return {}


# ---------------------------------------------------------------------------
# Core search: runs a single-strategy search against Azure AI Search
# ---------------------------------------------------------------------------


async def _execute_search(
    *,
    text_query: str | None,
    image_bytes: bytes | None,
    strategy: str,
    filters: dict[str, list[str]] | None,
    page: int,
    page_size: int,
    precomputed: dict[str, list[float]] | None = None,
) -> SearchResultSet:
    t0 = time.perf_counter()
    logger.info("_execute_search — strategy=%s, text=%r, has_image=%s, page=%d/%d",
                strategy, text_query, image_bytes is not None, page, page_size)
    client = _search_client

    # --- Build vector queries from pre-computed (or compute now) ---
    vector_queries = []
    search_text = text_query if text_query else None

    if strategy == "vision":
        if text_query:
            text_vec = (precomputed or {}).get("vision_text") or await vision_svc.vectorize_text(text_query)
            vector_queries.append(
                VectorizedQuery(vector=text_vec, k_nearest_neighbors=50, fields="imageVector")
            )
        if image_bytes:
            img_vec = (precomputed or {}).get("vision_image") or await vision_svc.vectorize_image(resize_for_vectorization(image_bytes))
            vector_queries.append(
                VectorizedQuery(vector=img_vec, k_nearest_neighbors=50, fields="imageVector")
            )
    else:
        if text_query:
            text_vec = (precomputed or {}).get("openai_text") or await openai_svc.embed_text(text_query)
            vector_queries.append(
                VectorizedQuery(vector=text_vec, k_nearest_neighbors=50, fields="textVector")
            )
        if image_bytes:
            img_vec = (precomputed or {}).get("vision_image") or await vision_svc.vectorize_image(resize_for_vectorization(image_bytes))
            vector_queries.append(
                VectorizedQuery(vector=img_vec, k_nearest_neighbors=50, fields="imageVector")
            )

    odata_filter = _build_filter(filters)
    logger.info("  vector_queries=%d, search_text=%r, filter=%s", len(vector_queries), search_text, odata_filter)

    # Determine scoring mode for proper normalisation
    has_vectors = len(vector_queries) > 0
    has_text = search_text is not None
    if has_vectors and has_text:
        score_mode = "hybrid"
        # BM25 counts as 1 retriever + each vector query
        score_retrievers = 1 + len(vector_queries)
    elif has_vectors:
        score_mode = "vector"
        score_retrievers = len(vector_queries)
    else:
        score_mode = "bm25"
        score_retrievers = 1
    logger.info("  scoring: mode=%s, retrievers=%d", score_mode, score_retrievers)

    # Async search — does NOT block the event loop
    # Enable semantic ranking when full-text is involved (hybrid or bm25)
    use_semantic = has_text
    results = await client.search(
        search_text=search_text,
        vector_queries=vector_queries if vector_queries else None,
        query_type="semantic" if use_semantic else "simple",
        semantic_configuration_name="my-semantic-config" if use_semantic else None,
        filter=odata_filter,
        facets=FACET_SPECS,
        top=page_size,
        skip=(page - 1) * page_size,
        include_total_count=True,
        select="id,fileName,thumbnailUrl,originalUrl,caption,tags,objects,description,fileSize,width,height,uploadDate,contentType",
    )

    items: list[SearchResultItem] = []
    async for r in results:
        # Prefer semantic reranker score when available (0-4 scale)
        reranker_score = r.get("@search.reranker_score")
        if reranker_score is not None:
            relevance = round(max(0.0, min((reranker_score / 4.0) * 100, 100.0)), 1)
        else:
            relevance = _normalize_score(r.get("@search.score"), mode=score_mode, num_retrievers=score_retrievers)

        items.append(
            SearchResultItem(
                id=r["id"],
                file_name=r.get("fileName", ""),
                thumbnail_url=refresh_sas_url(r.get("thumbnailUrl", "")),
                original_url=refresh_sas_url(r.get("originalUrl", "")),
                caption=r.get("caption", ""),
                tags=r.get("tags", []),
                objects=r.get("objects", []),
                description=r.get("description"),
                relevance=relevance,
                file_size=r.get("fileSize", 0),
                width=r.get("width"),
                height=r.get("height"),
                upload_date=r.get("uploadDate"),
                content_type=r.get("contentType"),
            )
        )

    # Facets
    facets: dict[str, list[FacetValue]] = {}
    raw_facets = await results.get_facets()
    if raw_facets:
        for facet_name, facet_values in raw_facets.items():
            facets[facet_name] = [
                FacetValue(value=str(fv["value"]), count=fv["count"]) for fv in facet_values
            ]

    total = await results.get_count() or 0
    elapsed = (time.perf_counter() - t0) * 1000
    logger.info("  _execute_search done (%.0f ms) — strategy=%s, total=%d, returned=%d",
                elapsed, strategy, total, len(items))
    if items:
        logger.info("  Top result: id=%s, file=%s, relevance=%.1f%%", items[0].id, items[0].file_name, items[0].relevance)

    return SearchResultSet(
        strategy=strategy,
        total_count=total,
        results=items,
        facets=facets,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def execute_search(
    request: SearchRequest,
    image_bytes: bytes | None = None,
) -> SearchResponse:
    """Run search with the requested strategy. Returns SearchResponse."""
    logger.info("execute_search — strategy=%s, text=%r, has_image=%s",
                request.strategy, request.text_query, image_bytes is not None)

    if request.strategy == "compare":
        # 1. Pre-compute ALL vectors in parallel (vision_text + openai_text + vision_image)
        strategies = ["vision", "openai"]
        logger.info("  Compare mode → pre-computing all vectors in parallel")
        precomputed = await _precompute_vectors(request.text_query, image_bytes, strategies)
        logger.info("  Vectors ready: %s", list(precomputed.keys()))

        # 2. Run both search queries in parallel (async client → truly parallel)
        vision_task = _execute_search(
            text_query=request.text_query,
            image_bytes=image_bytes,
            strategy="vision",
            filters=request.filters,
            page=request.page,
            page_size=request.page_size,
            precomputed=precomputed,
        )
        openai_task = _execute_search(
            text_query=request.text_query,
            image_bytes=image_bytes,
            strategy="openai",
            filters=request.filters,
            page=request.page,
            page_size=request.page_size,
            precomputed=precomputed,
        )
        vision_results, openai_results = await asyncio.gather(vision_task, openai_task)
        return SearchResponse(mode="compare", vision=vision_results, openai=openai_results)
    else:
        # Single strategy — still pre-compute vectors in parallel if text + image
        precomputed = await _precompute_vectors(request.text_query, image_bytes, [request.strategy])

        result = await _execute_search(
            text_query=request.text_query,
            image_bytes=image_bytes,
            strategy=request.strategy,
            filters=request.filters,
            page=request.page,
            page_size=request.page_size,
            precomputed=precomputed,
        )
        if request.strategy == "vision":
            return SearchResponse(mode="single", vision=result)
        else:
            return SearchResponse(mode="single", openai=result)


async def get_facets() -> dict[str, list[FacetValue]]:
    """Get available facets from the index (empty search, facets only)."""
    logger.info("get_facets")
    client = _search_client
    results = await client.search(
        search_text="*",
        facets=FACET_SPECS,
        top=0,
        include_total_count=True,
    )
    facets: dict[str, list[FacetValue]] = {}
    raw_facets = await results.get_facets()
    if raw_facets:
        for name, values in raw_facets.items():
            facets[name] = [FacetValue(value=str(fv["value"]), count=fv["count"]) for fv in values]
    logger.info("get_facets done — %s", {k: len(v) for k, v in facets.items()})
    return facets
