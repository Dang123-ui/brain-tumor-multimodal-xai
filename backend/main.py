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
from neuroboard.router import router as neuroboard_router
from neuroboard.seed import seed_neuroboard_demo

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
    local_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    return list(dict.fromkeys([*origins, *local_origins]))


def _get_cors_origin_regex() -> str | None:
    configured = os.getenv("CORS_ORIGIN_REGEX", "").strip()
    if configured:
        return configured

    allow_vercel_previews = os.getenv("ALLOW_VERCEL_PREVIEWS", "true").strip().lower()
    if allow_vercel_previews not in {"0", "false", "no", "off"}:
        return r"https://.*\.vercel\.app"

    return None


app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_origin_regex=_get_cors_origin_regex(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def init_default_admin():
    db = SessionLocal()
    try:
        demo_users = [
            ("admin", "123456", "researcher"),
            ("doctor_lan", "123456", "doctor"),
            ("doctor_minh", "123456", "doctor"),
        ]
        seeded_users = {}
        for username, password, role in demo_users:
            user = db.query(models.User).filter(models.User.username == username).first()
            if not user:
                user = models.User(
                    username=username,
                    hashed_password=hash_password(password),
                    role=role,
                )
                db.add(user)
                db.flush()
            else:
                user.role = role
                if not user.hashed_password:
                    user.hashed_password = hash_password(password)
            seeded_users[username] = user

        admin_user = seeded_users["admin"]
        legacy_patients = (
            db.query(models.Patient)
            .filter(models.Patient.owner_user_id.is_(None))
            .all()
        )
        for patient in legacy_patients:
            patient.owner_user_id = admin_user.id
        db.commit()

        seed_enabled = os.getenv("NEUROBOARD_SEED_DEMO", "true").strip().lower()
        if seed_enabled not in {"0", "false", "no", "off"}:
            created_count = seed_neuroboard_demo(db)
            if created_count:
                print(f"[NEUROBOARD] Seeded {created_count} demo posts")
    finally:
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

# --- NeuroBoard collaboration feed ---
app.include_router(neuroboard_router)


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
