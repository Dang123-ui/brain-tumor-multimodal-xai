import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import crud
import models
import schemas
from celery_app import celery_app
from database import get_db
from utils import get_current_user

router = APIRouter(prefix="/inference", tags=["AI Inference"])

# Kết nối tới Celery broker (Redis) — cấu hình qua biến môi trường


def _create_inference_task(
    db: Session,
    task_type: str,
    target_id: int,
    celery_signature: str,
) -> models.InferenceTask:
    """Helper: tạo bản ghi InferenceTask trong DB rồi gửi task lên Celery."""
    placeholder_celery_id = str(uuid.uuid4())

    db_task = models.InferenceTask(
        celery_task_id=placeholder_celery_id,
        task_type=task_type,
        target_id=target_id,
        status="pending",
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)

    print(f"[API] Da tao record task_id={db_task.id} trong DB. Dang gui sang Celery...")

    try:
        # Gửi task bất đồng bộ tới Celery worker
        celery_app.send_task(
            celery_signature,
            args=[db_task.id, target_id],
            task_id=placeholder_celery_id,
        )
        print(f"[API] Da gui task_id={db_task.id} thanh cong.")
    except Exception as e:
        print(f"[API] LOI KHI GUI TASK SANG CELERY: {e}")
        db_task.status = "failed"
        db_task.error_message = f"Khong the gui task sang Celery: {e}"
        db.commit()
        raise HTTPException(status_code=503, detail=db_task.error_message) from e
        
    return db_task


def _ensure_celery_worker_available() -> None:
    try:
        responses = celery_app.control.ping(timeout=0.7)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Celery worker chua san sang: {exc}",
        ) from exc

    if not responses:
        raise HTTPException(
            status_code=503,
            detail=(
                "Celery worker chua chay nen pipeline se bi ket pending. "
                "Hay bat worker: backend\\.venv\\Scripts\\celery.exe -A celery_app.celery_app worker --loglevel=info --pool=solo"
            ),
        )


# ============================================================
# POST /inference/mri/{image_id}
# Kích hoạt pipeline chẩn đoán MRI (YOLOv5 → U-Net → DenseNet-ViT)
# ============================================================

@router.post("/mri/{image_id}", response_model=schemas.InferenceTaskResponse)
def trigger_mri_inference(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Xác minh ảnh tồn tại trong DB
    image = crud.get_image_for_user(db, image_id, current_user)
    if not image:
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh MRI")

    if image.modality not in ["MRI", "MRI_SERIES"]:
        raise HTTPException(
            status_code=400,
            detail=f"Ảnh này có modality='{image.modality}', endpoint này chỉ xử lý MRI hoặc MRI_SERIES",
        )

    _ensure_celery_worker_available()

    # Tương tự như Prognosis, bỏ qua việc check task cũ để tránh deadlock khi worker sập.

    db_task = _create_inference_task(
        db=db,
        task_type="mri_pipeline",
        target_id=image_id,
        celery_signature="tasks.run_mri_pipeline",
    )

    return schemas.InferenceTaskResponse(
        task_id=db_task.id,
        celery_task_id=db_task.celery_task_id,
        status=db_task.status,
        message=f"Pipeline MRI đã được kích hoạt. Dùng GET /inference/tasks/{db_task.id} để theo dõi tiến độ.",
    )


# ============================================================
# POST /inference/prognosis/{patient_id}
# Kích hoạt mô hình Attention-based Fusion (MRI + WSI + RNA)
# ============================================================

@router.post("/prognosis/{patient_id}", response_model=schemas.InferenceTaskResponse)
def trigger_prognosis_inference(
    patient_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Xác minh bệnh nhân tồn tại (hỗ trợ cả ID số và External ID chuỗi)
    patient = crud.get_patient_for_user(db, patient_id, current_user)
    if not patient:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy bệnh nhân với ID '{patient_id}'")

    # Sử dụng ID số nội bộ từ đây
    real_id = patient.id

    # Kiểm tra dữ liệu RNA đã được tải lên chưa (cần thiết cho Fusion Model)
    # RnaData is no longer strictly mandatory since the model handles missing data gracefully via masking,
    # but we still check if the patient has any data uploaded.
    rna = db.query(models.RnaData).filter(models.RnaData.patient_id == real_id).first()
    if not rna:
        print(f"[Warning] No RNA-seq data found cho bệnh nhân {patient_id}. The model will automatically skip it using Attention Mask.")

    _ensure_celery_worker_available()

    # Loại bỏ cơ chế kiểm tra tác vụ cũ vì nếu Worker sập, DB sẽ lưu trạng thái 'processing' mãi mãi.
    # Luôn luôn tạo một task mới khi người dùng yêu cầu để tránh bị kẹt (deadlock).

    db_task = _create_inference_task(
        db=db,
        task_type="prognosis",
        target_id=real_id,
        celery_signature="tasks.run_prognosis_pipeline",
    )

    return schemas.InferenceTaskResponse(
        task_id=db_task.id,
        celery_task_id=db_task.celery_task_id,
        status=db_task.status,
        message=f"Pipeline tiên lượng đã được kích hoạt. Dùng GET /inference/tasks/{db_task.id} để theo dõi tiến độ.",
    )


# ============================================================
# GET /inference/tasks/{task_id}
# Polling: kiểm tra trạng thái tiến độ tác vụ AI
# ============================================================

@router.get("/tasks/{task_id}", response_model=schemas.InferenceTaskStatus)
def get_task_status(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    task = db.query(models.InferenceTask).filter(models.InferenceTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tác vụ id={task_id}")

    if task.task_type == "mri_pipeline":
        image = crud.get_image_for_user(db, int(task.target_id), current_user)
        if not image:
            raise HTTPException(status_code=404, detail=f"Task id={task_id} not found")
    elif task.task_type == "prognosis":
        patient = (
            db.query(models.Patient)
            .filter(
                models.Patient.id == int(task.target_id),
                models.Patient.owner_user_id == crud.current_user_id(current_user),
            )
            .first()
        )
        if not patient:
            raise HTTPException(status_code=404, detail=f"Task id={task_id} not found")

    progress_percent = None
    progress_status = None

    # Nếu đang chạy, thử lấy meta-data từ Celery (Progress Bar)
    if task.status == "processing":
        from celery.result import AsyncResult
        res = AsyncResult(task.celery_task_id)
        if res.state == 'PROGRESS':
            progress_percent = res.info.get('percent')
            progress_status = res.info.get('status')

    return schemas.InferenceTaskStatus(
        task_id=task.id,
        celery_task_id=task.celery_task_id,
        task_type=task.task_type,
        status=task.status,
        progress_percent=progress_percent,
        progress_status=progress_status,
        result=task.result,
        error_message=task.error_message,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )
