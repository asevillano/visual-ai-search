"""Azure Blob Storage service — upload originals & thumbnails.

Containers are PRIVATE.  Plain URLs (without SAS) are stored in the search
index so they never expire.  Fresh SAS tokens are generated on-the-fly by
``refresh_sas_url()`` every time URLs are served to the frontend.

Auth: Managed Identity (DefaultAzureCredential) — no account keys required.
SAS tokens are created via **User Delegation Keys** (Entra ID).
"""

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from azure.identity import DefaultAzureCredential
from azure.storage.blob import (
    BlobServiceClient,
    generate_blob_sas,
    BlobSasPermissions,
    ContentSettings,
    UserDelegationKey,
)
from app.config import get_settings

logger = logging.getLogger("app.blob_storage")

_client: BlobServiceClient | None = None
_credential: DefaultAzureCredential | None = None
_user_delegation_key: UserDelegationKey | None = None
_udk_expiry: datetime | None = None


def _get_user_delegation_key() -> UserDelegationKey:
    """Return a cached User Delegation Key, refreshing if close to expiry."""
    global _user_delegation_key, _udk_expiry
    now = datetime.now(timezone.utc)
    # Refresh when missing or within 1 hour of expiry
    if _user_delegation_key is None or _udk_expiry is None or now >= _udk_expiry - timedelta(hours=1):
        start = now - timedelta(minutes=5)
        expiry = now + timedelta(hours=24)
        logger.info("Requesting new User Delegation Key (valid for 24 h)")
        _user_delegation_key = _client.get_user_delegation_key(start, expiry)
        _udk_expiry = expiry
    return _user_delegation_key


def init() -> None:
    """Eagerly create BlobServiceClient and ensure containers exist."""
    global _client, _credential
    settings = get_settings()

    # Prefer account name (Managed Identity), fall back to connection string (local dev)
    if settings.azure_storage_account_name:
        account_name = settings.azure_storage_account_name
        logger.info("Blob init — account=%s (Managed Identity)", account_name)
        _credential = DefaultAzureCredential()
        account_url = f"https://{account_name}.blob.core.windows.net"
        _client = BlobServiceClient(account_url, credential=_credential)
    elif settings.azure_storage_connection_string:
        conn = settings.azure_storage_connection_string
        acct = conn.split("AccountName=")[1].split(";")[0] if "AccountName=" in conn else "?"
        logger.info("Blob init — account=%s (connection string)", acct)
        _client = BlobServiceClient.from_connection_string(conn)
    else:
        raise ValueError("Set AZURE_STORAGE_ACCOUNT_NAME or AZURE_STORAGE_CONNECTION_STRING")

    for name in (settings.azure_storage_container_originals, settings.azure_storage_container_thumbnails):
        container = _client.get_container_client(name)
        if not container.exists():
            logger.info("Creating container '%s' (private)", name)
            container.create_container()
        else:
            logger.info("Container '%s' already exists", name)

    # Pre-warm User Delegation Key when using Managed Identity
    if _credential is not None:
        _get_user_delegation_key()

    logger.info("Blob init OK")


def close() -> None:
    """Close the BlobServiceClient."""
    global _client, _credential, _user_delegation_key, _udk_expiry
    if _client:
        _client.close()
        _client = None
    _credential = None
    _user_delegation_key = None
    _udk_expiry = None
    logger.info("Blob client closed")


def get_sas_url(container_name: str, blob_name: str, expiry_hours: int = 24) -> str:
    """Generate a SAS URL for a blob (containers are private).

    Uses User Delegation SAS (Entra ID) when Managed Identity is configured,
    falls back to account-key SAS for local dev with connection string.
    """
    account_name = _client.account_name

    if _credential is not None:
        # User Delegation SAS — no account key needed
        udk = _get_user_delegation_key()
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container_name,
            blob_name=blob_name,
            user_delegation_key=udk,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(hours=expiry_hours),
        )
    else:
        # Account-key SAS (local dev with connection string)
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
