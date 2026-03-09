"""Quick test — full upload pipeline."""
import asyncio, sys, os

BASE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(BASE, "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

import importlib
from PIL import Image
import io
from app.services import blob_storage, vision, openai_embeddings
from app.services.search_index import ensure_index
from app.utils.helpers import generate_id, build_text_representation
from app.utils.thumbnails import create_thumbnail, get_image_dimensions
from app.config import get_settings
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from datetime import datetime, timezone

importlib.reload(blob_storage)


async def main():
    img = Image.new("RGB", (200, 150), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    ib = buf.getvalue()

    ensure_index()
    did = generate_id()
    tb = create_thumbnail(ib, "image/jpeg")
    w, h = get_image_dimensions(ib)

    ou = await blob_storage.upload_original(f"{did}.jpg", ib, "image/jpeg")
    tu = await blob_storage.upload_thumbnail(f"{did}.jpg", tb)
    print("Blob OK")

    a = await vision.analyze_image(ib)
    print(f"Vision OK: {a['caption']}")

    iv = await vision.vectorize_image(ib)
    print(f"ImgVec: {len(iv)}")

    tr = build_text_representation(a["caption"], a["tags"])
    tv = await openai_embeddings.embed_text(tr)
    print(f"TxtVec: {len(tv)}")

    s = get_settings()
    sc = SearchClient(
        endpoint=s.azure_search_endpoint,
        index_name=s.azure_search_index_name,
        credential=AzureKeyCredential(s.azure_search_api_key),
    )
    doc = {
        "id": did,
        "fileName": "test_blue.jpg",
        "description": tr,
        "caption": a["caption"],
        "tags": a["tags"],
        "objects": a["objects"],
        "fileSize": len(ib),
        "width": w,
        "height": h,
        "uploadDate": datetime.now(timezone.utc).isoformat(),
        "contentType": "image/jpeg",
        "thumbnailUrl": tu,
        "originalUrl": ou,
        "imageVector": iv,
        "textVector": tv,
    }
    r = sc.upload_documents(documents=[doc])
    print(f"Index upload: {r[0].succeeded}")
    print("\n=== ALL OK ===")


asyncio.run(main())
