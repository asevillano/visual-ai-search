"""Azure Blob Storage service — upload originals & thumbnails.

Containers are PRIVATE.  Plain URLs (without SAS) are stored in the search
index so they never expire.  Fresh SAS tokens are generated on-the-fly by
``refresh_sas_url()`` every time URLs are served to the frontend.
"""

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions, ContentSettings
from app.config import get_settings

logger = logging.getLogger("app.blob_storage")

_client: BlobServiceClient | None = None


def init() -> None:
    """Eagerly create BlobServiceClient and ensure containers exist."""
    global _client
    settings = get_settings()
    conn = settings.azure_storage_connection_string
    acct = conn.split("AccountName=")[1].split(";")[0] if "AccountName=" in conn else "?"
    logger.info("Blob init — account=%s", acct)
    _client = BlobServiceClient.from_connection_string(conn)
    for name in (settings.azure_storage_container_originals, settings.azure_storage_container_thumbnails):
        container = _client.get_container_client(name)
        if not container.exists():
            logger.info("Creating container '%s' (private)", name)
            container.create_container()
        else:
            logger.info("Container '%s' already exists", name)
    logger.info("Blob init OK")


def close() -> None:
    """Close the BlobServiceClient."""
    global _client
    if _client:
        _client.close()
        _client = None
    logger.info("Blob client closed")


def get_sas_url(container_name: str, blob_name: str, expiry_hours: int = 24) -> str:
    """Generate a SAS URL for a blob (containers are private)."""
    settings = get_settings()
    account_name = _client.account_name
    account_key = _client.credential.account_key

    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container_name,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(hours=expiry_hours),
    )
    return f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"


def get_plain_url(container_name: str, blob_name: str) -> str:
    """Return the permanent plain URL for a blob (no SAS token)."""
    account_name = _client.account_name
    return f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}"


async def upload_blob(container_name: str, blob_name: str, data: bytes, content_type: str = "image/jpeg") -> str:
    """Upload bytes to a container and return the plain blob URL (no SAS).

    The plain URL is what gets stored in the search index.  To serve it
    to a browser, wrap it with ``refresh_sas_url()``.
    """
    logger.info("upload_blob: %s/%s  %d bytes  %s", container_name, blob_name, len(data), content_type)
    try:
        blob = _client.get_blob_client(container=container_name, blob=blob_name)
        blob.upload_blob(data, overwrite=True, content_settings=ContentSettings(content_type=content_type))
        plain_url = get_plain_url(container_name, blob_name)
        logger.info("upload_blob OK: %s/%s", container_name, blob_name)
        return plain_url
    except Exception as exc:
        logger.error("upload_blob FAILED (%s/%s): %s", container_name, blob_name, exc, exc_info=True)
        raise


async def upload_original(blob_name: str, data: bytes, content_type: str) -> str:
    settings = get_settings()
    return await upload_blob(settings.azure_storage_container_originals, blob_name, data, content_type)


async def upload_thumbnail(blob_name: str, data: bytes) -> str:
    settings = get_settings()
    return await upload_blob(settings.azure_storage_container_thumbnails, blob_name, data, "image/jpeg")


def refresh_sas_url(stored_url: str) -> str:
    """Return a fresh SAS URL for a stored blob URL.

    Works with both plain URLs (new) and legacy SAS URLs (old) —
    extracts container + blob from the path and generates a new token.
    Returns the original string unchanged if parsing fails.
    """
    if not stored_url:
        return stored_url
    try:
        parsed = urlparse(stored_url)
        # path = /<container>/<blob_name>
        parts = parsed.path.lstrip("/").split("/", 1)
        if len(parts) != 2:
            return stored_url
        container_name, blob_name = parts
        return get_sas_url(container_name, blob_name)
    except Exception:
        return stored_url
