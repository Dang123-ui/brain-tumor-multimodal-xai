import io
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Tuple

import pydicom
from dotenv import load_dotenv
from minio import Minio
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

# ============================================================
# MINIO CLIENT
# ============================================================

minio_client = Minio(
    os.getenv("MINIO_URL", "minio:9000"),
    access_key=os.getenv("MINIO_ACCESS_KEY", "admin"),
    secret_key=os.getenv("MINIO_SECRET_KEY", "password123"),
    secure=os.getenv("MINIO_SECURE", "false").lower() in {"1", "true", "yes", "on"},
    region=os.getenv("MINIO_REGION") or None,
)


def ensure_bucket_exists(bucket_name: str):
    """Kiểm tra và tạo bucket trên MinIO nếu chưa có."""
    if not minio_client.bucket_exists(bucket_name):
        minio_client.make_bucket(bucket_name)


def anonymize_dicom(file_bytes: bytes) -> io.BytesIO:
    """Đọc và tự động ẩn danh các trường thông tin nhạy cảm trong file DICOM.

    Hỗ trợ cả các file DICOM thiếu File Meta Information/prefix `DICM`.
    """
    try:
        dicom_file = pydicom.dcmread(io.BytesIO(file_bytes))
    except Exception:
        dicom_file = pydicom.dcmread(io.BytesIO(file_bytes), force=True)

    # Tranh doc nham anh JPEG/PNG hoac file bat ky thanh "DICOM" khi force=True.
    if "PixelData" not in dicom_file:
        raise ValueError("File khong co PixelData, khong du dieu kien xu ly nhu DICOM.")

    sensitive_tags = {
        "PatientName": "ANONYMOUS",
        "PatientID": "ANON-0000",
        "PatientBirthDate": "",
        "InstitutionName": "HIDDEN HOSPITAL",
    }
    for tag, replacement in sensitive_tags.items():
        if tag in dicom_file:
            setattr(dicom_file, tag, replacement)

    output = io.BytesIO()
    dicom_file.save_as(output)
    output.seek(0)
    return output


def prepare_mri_upload(file_bytes: bytes, filename: str | None) -> Tuple[io.BytesIO, str]:
    """Chuẩn bị bytes để upload MRI.

    - Nếu là DICOM chuẩn hoặc DICOM thiếu preamble: đọc và ẩn danh, trả content type DICOM.
    - Nếu không đọc được như DICOM: giữ nguyên bytes để hỗ trợ ảnh thường dùng cho test.
    """
    try:
        clean_stream = anonymize_dicom(file_bytes)
        return clean_stream, "application/dicom"
    except Exception:
        fallback_stream = io.BytesIO(file_bytes)
        fallback_stream.seek(0)

        extension = (filename or "").rsplit(".", 1)[-1].lower() if filename and "." in filename else ""
        content_type_map = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "bmp": "image/bmp",
            "tif": "image/tiff",
            "tiff": "image/tiff",
        }
        return fallback_stream, content_type_map.get(extension, "application/octet-stream")


# ============================================================
# JWT & PASSWORD UTILITIES
# ============================================================

SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_IN_PRODUCTION_USE_STRONG_SECRET")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(plain_password: str) -> str:
    """Băm mật khẩu người dùng bằng bcrypt."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """So sánh mật khẩu thô với giá trị đã băm."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    """Tạo JWT chứa payload và thời gian hết hạn."""
    payload = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload.update({"exp": expire})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Giải mã JWT và trả về payload. Ném HTTPException nếu token không hợp lệ."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token không hợp lệ hoặc đã hết hạn",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise credentials_exception


# ============================================================
# FASTAPI DEPENDENCIES
# ============================================================

def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Dependency: giải mã token và trả về payload {user_id, role}."""
    return decode_token(token)


def require_role(*allowed_roles: str):
    """Dependency factory: chỉ cho phép các role được chỉ định truy cập."""
    def _check(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Yêu cầu quyền: {', '.join(allowed_roles)}",
            )
        return current_user
    return _check
