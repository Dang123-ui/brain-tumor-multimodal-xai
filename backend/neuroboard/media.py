from __future__ import annotations

import io
import os
import re
import uuid
import base64
import mimetypes
from datetime import timedelta
from pathlib import Path

from fastapi import HTTPException, UploadFile


BUCKET_NAME = os.getenv("MINIO_BUCKET") or os.getenv("R2_BUCKET") or "medical-data"
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES_PER_POST = 6
ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}


def _safe_filename(filename: str | None) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", filename or "image")
    return cleaned.strip("-.") or "image"


async def store_post_images(post_id: int, files: list[UploadFile]) -> list[dict[str, str | int]]:
    if len(files) > MAX_FILES_PER_POST:
        raise HTTPException(status_code=422, detail=f"Mỗi bài đăng chỉ được tối đa {MAX_FILES_PER_POST} ảnh")

    from utils import ensure_bucket_exists, minio_client

    ensure_bucket_exists(BUCKET_NAME)
    stored: list[dict[str, str | int]] = []
    for index, upload in enumerate(files):
        content_type = (upload.content_type or "").lower()
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=422, detail=f"Định dạng ảnh không được hỗ trợ: {upload.filename}")
        content = await upload.read(MAX_FILE_BYTES + 1)
        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail=f"Ảnh vượt quá 10 MB: {upload.filename}")
        if not content:
            raise HTTPException(status_code=422, detail=f"Ảnh rỗng: {upload.filename}")

        object_name = f"neuroboard/{post_id}/{uuid.uuid4().hex}_{_safe_filename(upload.filename)}"
        minio_client.put_object(
            bucket_name=BUCKET_NAME,
            object_name=object_name,
            data=io.BytesIO(content),
            length=len(content),
            content_type=content_type,
        )
        stored.append(
            {
                "object_path": f"/{BUCKET_NAME}/{object_name}",
                "content_type": content_type,
                "original_name": upload.filename or "image",
                "sort_order": index,
            }
        )
    return stored


async def store_message_image(conversation_id: int, upload: UploadFile) -> dict[str, str]:
    from utils import ensure_bucket_exists, minio_client

    content_type = (upload.content_type or "").lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=422, detail=f"Dinh dang anh khong duoc ho tro: {upload.filename}")
    content = await upload.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"Anh vuot qua 10 MB: {upload.filename}")
    if not content:
        raise HTTPException(status_code=422, detail=f"Anh rong: {upload.filename}")

    ensure_bucket_exists(BUCKET_NAME)
    object_name = f"neuroboard/messages/{conversation_id}/{uuid.uuid4().hex}_{_safe_filename(upload.filename)}"
    minio_client.put_object(
        bucket_name=BUCKET_NAME,
        object_name=object_name,
        data=io.BytesIO(content),
        length=len(content),
        content_type=content_type,
    )
    return {
        "image_path": f"/{BUCKET_NAME}/{object_name}",
        "image_content_type": content_type,
        "image_original_name": upload.filename or "image",
    }


def presigned_media_url(path: str | None) -> str | None:
    if not path:
        return None
    normalized = path.lstrip("/")
    parts = normalized.split("/", 1)
    if len(parts) != 2:
        return None
    bucket, object_name = parts
    try:
        from utils import build_minio_presigned_url

        return build_minio_presigned_url(bucket, object_name, expires=timedelta(hours=1))
    except Exception:
        return None


def display_media_url(path: str | None) -> str | None:
    """Return a browser-readable URL for MinIO paths or local result artifacts."""
    if not path:
        return None
    if path.startswith("/app/neuroboard/assets/"):
        asset_name = Path(path).name
        local_asset = Path(__file__).resolve().parent / "assets" / asset_name
        path = str(local_asset)
    if os.path.exists(path):
        mime_type = mimetypes.guess_type(path)[0] or "image/png"
        try:
            with open(path, "rb") as image_file:
                encoded = base64.b64encode(image_file.read()).decode("ascii")
            return f"data:{mime_type};base64,{encoded}"
        except Exception:
            return None
    return presigned_media_url(path)
