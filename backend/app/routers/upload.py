"""Upload router — POST /api/upload."""

from __future__ import annotations
import asyncio
import logging
import time
from datetime import datetime, timezone
from fastapi import APIRouter, UploadFile, File, HTTPException

from app.models.upload import UploadResponse, UploadResult
from app.services import blob_storage, vision, openai_embeddings
from app.services import gpt_analysis
from app.services.blob_storage import refresh_sas_url
from app.utils.helpers import generate_id, build_text_representation
from app.utils.thumbnails import create_thumbnail, get_image_dimensions
from app.config import get_settings

from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

logger = logging.getLogger("app.upload")
router = APIRouter(prefix="/api", tags=["upload"])

_search_client: SearchClient | None = None


def init() -> None:
    """Create the reusable sync SearchClient for document upserts."""
    global _search_client
    s = get_settings()
    logger.info("Upload init — creating sync SearchClient for upserts")
    _search_client = SearchClient(
        endpoint=s.azure_search_endpoint,
        index_name=s.azure_search_index_name,
        credential=AzureKeyCredential(s.azure_search_api_key),
    )
    logger.info("Upload init OK")


@router.post("/upload", response_model=UploadResponse)
async def upload_images(files: list[UploadFile] = File(...)):
    """Upload one or more images for indexing."""
    logger.info("Upload request received — %d file(s)", len(files))
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    results: list[UploadResult] = []

    for i, file in enumerate(files):
        label = file.filename or f"file-{i}"
        if not file.content_type or not file.content_type.startswith("image/"):
            logger.warning("  [%s] Skipped — not an image (content_type=%s)", label, file.content_type)
            continue

        t0 = time.perf_counter()
        image_bytes = await file.read()
        doc_id = generate_id()
        ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "jpg"
        original_blob_name = f"{doc_id}.{ext}"
        thumbnail_blob_name = f"{doc_id}.jpg"
        logger.info("  [%s] id=%s  size=%d bytes  type=%s", label, doc_id, len(image_bytes), file.content_type)

        # 1. Thumbnail
        try:
            thumb_bytes = create_thumbnail(image_bytes, file.content_type)
            width, height = get_image_dimensions(image_bytes)
            logger.info("  [%s] Thumbnail OK — %d bytes, %dx%d", label, len(thumb_bytes), width, height)
        except Exception as exc:
            logger.error("  [%s] Thumbnail FAILED: %s", label, exc, exc_info=True)
            continue

        # 2. Parallel: blob upload + GPT-4.1 analysis + Vision vector
        original_url_task = blob_storage.upload_original(original_blob_name, image_bytes, file.content_type)
        thumbnail_url_task = blob_storage.upload_thumbnail(thumbnail_blob_name, thumb_bytes)
        analysis_task = gpt_analysis.analyze_image(image_bytes, file.content_type)
        image_vector_task = vision.vectorize_image(image_bytes)

        try:
            logger.info("  [%s] Starting parallel tasks (blob × 2, GPT analyze, vectorize)…", label)
            original_url, thumbnail_url, analysis, image_vector = await asyncio.gather(
                original_url_task, thumbnail_url_task, analysis_task, image_vector_task
            )
            logger.info("  [%s] Blob upload  OK — original=%s…", label, original_url[:80])
            logger.info("  [%s] GPT analysis  OK — caption='%s', tags=%s, objects=%s, details=%d chars",
                        label, analysis["caption"], analysis["tags"], analysis["objects"],
                        len(analysis.get("details", "")))
            logger.info("  [%s] Image vector  OK — %d-d", label, len(image_vector))
        except Exception as exc:
            logger.error("  [%s] Parallel tasks FAILED: %s", label, exc, exc_info=True)
            continue

        caption = analysis["caption"]
        tags = analysis["tags"]
        objects = analysis["objects"]
        details = analysis.get("details", "")

        # 3. Text embedding (needs caption+tags+details from GPT-4.1)
        text_repr = build_text_representation(caption, tags, objects, details)
        try:
            if text_repr:
                logger.info("  [%s] Generating OpenAI text embedding for: '%s'", label, text_repr[:120])
                text_vector = await openai_embeddings.embed_text(text_repr)
                logger.info("  [%s] Text vector   OK — %d-d", label, len(text_vector))
            else:
                text_vector = [0.0] * 3072
                logger.warning("  [%s] No text representation — using zero vector", label)
        except Exception as exc:
            logger.error("  [%s] Text embedding FAILED (using zero vector): %s", label, exc, exc_info=True)
            text_vector = [0.0] * 3072

        # 4. Upsert document to search index
        doc = {
            "id": doc_id,
            "fileName": file.filename or original_blob_name,
            "description": text_repr,
            "caption": caption,
            "tags": tags,
            "objects": objects,
            "fileSize": len(image_bytes),
            "width": width,
            "height": height,
            "uploadDate": datetime.now(timezone.utc).isoformat(),
            "contentType": file.content_type,
            "thumbnailUrl": thumbnail_url,
            "originalUrl": original_url,
            "imageVector": image_vector,
            "textVector": text_vector,
        }

        try:
            upsert_result = _search_client.upload_documents(documents=[doc])
            ok = upsert_result[0].succeeded
            elapsed = (time.perf_counter() - t0) * 1000
            if ok:
                logger.info("  [%s] ✓ Indexed OK (%.0f ms total)", label, elapsed)
            else:
                logger.error("  [%s] ✗ Index upsert failed: %s", label, upsert_result[0].error_message)
        except Exception as exc:
            logger.error("  [%s] ✗ Index upsert EXCEPTION: %s", label, exc, exc_info=True)
            continue

        results.append(
            UploadResult(
                id=doc_id,
                file_name=file.filename or original_blob_name,
                thumbnail_url=refresh_sas_url(thumbnail_url),
                original_url=refresh_sas_url(original_url),
                caption=caption,
                tags=tags,
                objects=objects,
            )
        )

    logger.info("Upload complete — %d/%d files indexed", len(results), len(files))
    return UploadResponse(status="ok", count=len(results), results=results)
