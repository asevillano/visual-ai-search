"""Documents router — GET /api/documents, DELETE /api/documents/:id, DELETE /api/documents."""

from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.services import blob_storage
from app.services.blob_storage import refresh_sas_url

from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

logger = logging.getLogger("app.documents")
router = APIRouter(prefix="/api", tags=["documents"])

_search_client: SearchClient | None = None


def init() -> None:
    """Create a sync SearchClient for document listing/deletion."""
    global _search_client
    s = get_settings()
    logger.info("Documents init — creating sync SearchClient")
    _search_client = SearchClient(
        endpoint=s.azure_search_endpoint,
        index_name=s.azure_search_index_name,
        credential=AzureKeyCredential(s.azure_search_api_key),
    )
    logger.info("Documents init OK")


# ── Models ──────────────────────────────────────────────────────────────

class DocumentItem(BaseModel):
    id: str
    file_name: str
    thumbnail_url: str
    original_url: str
    caption: str
    tags: list[str]
    objects: list[str]
    description: str | None = None
    file_size: int = 0
    width: int | None = None
    height: int | None = None
    upload_date: str | None = None
    content_type: str | None = None


class DocumentListResponse(BaseModel):
    total_count: int
    documents: list[DocumentItem]


class DeleteResponse(BaseModel):
    deleted: int
    ids: list[str]


# ── Endpoints ───────────────────────────────────────────────────────────

@router.get("/documents", response_model=DocumentListResponse)
def list_documents(page: int = 1, page_size: int = 50):
    """List all indexed documents (paginated, sorted by upload date desc)."""
    logger.info("list_documents — page=%d, page_size=%d", page, page_size)
    try:
        results = _search_client.search(
            search_text="*",
            select="id,fileName,thumbnailUrl,originalUrl,caption,tags,objects,description,fileSize,width,height,uploadDate,contentType",
            order_by=["uploadDate desc"],
            top=page_size,
            skip=(page - 1) * page_size,
            include_total_count=True,
        )

        items: list[DocumentItem] = []
        for r in results:
            items.append(DocumentItem(
                id=r["id"],
                file_name=r.get("fileName", ""),
                thumbnail_url=refresh_sas_url(r.get("thumbnailUrl", "")),
                original_url=refresh_sas_url(r.get("originalUrl", "")),
                caption=r.get("caption", ""),
                tags=r.get("tags", []),
                objects=r.get("objects", []),
                description=r.get("description"),
                file_size=r.get("fileSize", 0),
                width=r.get("width"),
                height=r.get("height"),
                upload_date=r.get("uploadDate"),
                content_type=r.get("contentType"),
            ))

        total = results.get_count() or 0
        logger.info("list_documents OK — total=%d, returned=%d", total, len(items))
        return DocumentListResponse(total_count=total, documents=items)

    except Exception as exc:
        logger.error("list_documents FAILED: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/documents/{doc_id}", response_model=DeleteResponse)
def delete_document(doc_id: str):
    """Delete a single document from the index and blob storage."""
    logger.info("delete_document — id=%s", doc_id)
    try:
        # 1. Get the doc first so we know blob names
        try:
            doc = _search_client.get_document(key=doc_id, selected_fields=["id", "fileName"])
            file_name = doc.get("fileName", "")
        except Exception:
            raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

        # 2. Delete from search index
        result = _search_client.delete_documents(documents=[{"id": doc_id}])
        ok = result[0].succeeded
        if not ok:
            logger.error("delete_document index removal failed: %s", result[0].error_message)
            raise HTTPException(status_code=500, detail="Failed to delete from search index")

        # 3. Best-effort delete from blob storage
        _delete_blobs_for_document(doc_id, file_name)

        logger.info("delete_document OK — id=%s", doc_id)
        return DeleteResponse(deleted=1, ids=[doc_id])

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("delete_document FAILED: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/documents", response_model=DeleteResponse)
def delete_all_documents():
    """Delete ALL documents from the index and blob storage."""
    logger.info("delete_all_documents")
    try:
        # Fetch all document IDs and file names
        all_docs: list[dict] = []
        results = _search_client.search(
            search_text="*",
            select="id,fileName",
            top=1000,
            include_total_count=True,
        )
        for r in results:
            all_docs.append({"id": r["id"], "fileName": r.get("fileName", "")})

        if not all_docs:
            logger.info("delete_all_documents — index is empty")
            return DeleteResponse(deleted=0, ids=[])

        # Delete from index in batches of 1000
        deleted_ids: list[str] = []
        batch_size = 1000
        for i in range(0, len(all_docs), batch_size):
            batch = all_docs[i:i + batch_size]
            docs_to_delete = [{"id": d["id"]} for d in batch]
            result = _search_client.delete_documents(documents=docs_to_delete)
            for j, r in enumerate(result):
                if r.succeeded:
                    deleted_ids.append(batch[j]["id"])
                else:
                    logger.warning("  Failed to delete id=%s: %s", batch[j]["id"], r.error_message)

        # Best-effort blob cleanup
        for d in all_docs:
            _delete_blobs_for_document(d["id"], d["fileName"])

        logger.info("delete_all_documents OK — deleted %d/%d", len(deleted_ids), len(all_docs))
        return DeleteResponse(deleted=len(deleted_ids), ids=deleted_ids)

    except Exception as exc:
        logger.error("delete_all_documents FAILED: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ── Helpers ─────────────────────────────────────────────────────────────

def _delete_blobs_for_document(doc_id: str, file_name: str) -> None:
    """Best-effort delete of original and thumbnail blobs."""
    settings = get_settings()
    ext = file_name.rsplit(".", 1)[-1] if file_name and "." in file_name else "jpg"
    original_name = f"{doc_id}.{ext}"
    thumbnail_name = f"{doc_id}.jpg"

    for container, blob_name in [
        (settings.azure_storage_container_originals, original_name),
        (settings.azure_storage_container_thumbnails, thumbnail_name),
    ]:
        try:
            blob = blob_storage._client.get_blob_client(container=container, blob=blob_name)
            blob.delete_blob()
            logger.info("  Deleted blob %s/%s", container, blob_name)
        except Exception as exc:
            logger.warning("  Blob delete failed %s/%s: %s", container, blob_name, exc)
