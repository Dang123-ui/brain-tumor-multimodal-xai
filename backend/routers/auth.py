from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db
from utils import verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ============================================================
# POST /auth/login — Xác thực và cấp JWT
# ============================================================

@router.post("/login", response_model=schemas.Token)
def login(
    username: str = Form(..., description="Tên đăng nhập"),
    password: str = Form(..., description="Mật khẩu"),
    db: Session = Depends(get_db),
):
    """
    Xác thực người dùng bằng username/password (form data).
    Trả về JWT token theo vai trò (doctor/researcher).
    """
    user = db.query(models.User).filter(models.User.username == username).first()

    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tên đăng nhập hoặc mật khẩu không đúng",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị vô hiệu hóa. Vui lòng liên hệ quản trị viên.",
        )

    token_payload = {"sub": str(user.id), "role": user.role, "username": user.username}
    access_token = create_access_token(data=token_payload)

    # Ghi access log
    log = models.AccessLog(
        user_id=user.id,
        method="POST",
        endpoint="/auth/login",
        client_ip="unknown",
        status_code=200,
    )
    db.add(log)
    db.commit()

    return schemas.Token(
        access_token=access_token,
        token_type="bearer",
        role=user.role,
        username=user.username,
        user_id=user.id,
    )
