import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

import models
from database import engine, SessionLocal
from utils import hash_password
from routers import upload, records, multimodal, inference, analysis, auth, admin
from agent.router import router as agent_router

# Tự động tạo tất cả bảng trong PostgreSQL khi khởi động
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="NeuroDiagnosis AI Backend",
    description=(
        "Backend API cho hệ thống chẩn đoán và tiên lượng u não đa mô thức. "
        "Hỗ trợ MRI (YOLOv5 + U-Net + DenseNet-ViT), WSI, RNA-seq và Fusion Model."
    ),
    version="2.0.0",
)

# CORS — cấu hình cho môi trường phát triển
def _get_cors_origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS") or os.getenv("FRONTEND_URL") or ""
    origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    return origins or ["http://localhost:3000", "http://127.0.0.1:3000"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def init_default_admin():
    db = SessionLocal()
    existing_user = db.query(models.User).filter(models.User.username == "admin").first()
    if not existing_user:
        new_user = models.User(
            username="admin",
            hashed_password=hash_password("123456"),
            role="researcher"
        )
        db.add(new_user)
        db.commit()
    db.close()

# ============================================================
# ĐĂNG KÝ CÁC ROUTER
# ============================================================

# --- Nhóm Upload (hiện có) ---
app.include_router(upload.router)

# --- Nhóm Quản lý hồ sơ (hiện có) ---
app.include_router(records.router)

# --- Nhóm Dữ liệu Đa mô thức (RNA + Lâm sàng) ---
app.include_router(multimodal.router)

# --- Nhóm AI Inference (Celery bất đồng bộ) ---
app.include_router(inference.router)

# --- Nhóm Kết quả & XAI (Grad-CAM, Survival Curve) ---
app.include_router(analysis.router)

# --- Nhóm Xác thực (JWT) ---
app.include_router(auth.router)

# --- Nhóm Quản trị (Access Log) ---
app.include_router(admin.router)

# --- Agent Chatbox ---
app.include_router(agent_router)


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/", tags=["Health"])
def read_root():
    return {
        "status": "running",
        "project": "NeuroDiagnosis AI Backend",
        "version": "2.0.0",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}
