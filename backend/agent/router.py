import json
import os
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

import crud
import models
from database import get_db
from routers.inference import _create_inference_task
from utils import (
    ensure_bucket_exists,
    get_current_user,
    minio_client,
    prepare_mri_upload,
)


router = APIRouter(prefix="/agent", tags=["Agent"])

BUCKET_NAME = os.getenv("MINIO_BUCKET") or os.getenv("R2_BUCKET") or "medical-data"


class AgentChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    patient_id: Optional[str] = None
    image_id: Optional[int] = None
    selected_region: Optional[dict[str, Any]] = None


class AgentChatResponse(BaseModel):
    thread_id: str
    message: str
    intent: str
    actions: list[dict[str, Any]] = Field(default_factory=list)


def _patient_display(patient: models.Patient) -> str:
    code = patient.patient_external_id or str(patient.id)
    name = patient.name or "Bệnh nhân"
    return f"{name} ({code})"


def _summarize_image_result(result: dict[str, Any] | None, patient: models.Patient | None = None) -> str:
    patient_text = f" cho {_patient_display(patient)}" if patient else ""
    if not result:
        return f"Đã tạo task phân tích MRI{patient_text}. Tôi sẽ tiếp tục theo dõi tiến trình và tóm tắt khi có kết quả."

    if result.get("no_tumor_detected"):
        return (
            f"Đã chạy xong MRI pipeline{patient_text}. Kết quả: không phát hiện khối u trên ảnh MRI này. "
            "Không chạy tiên lượng/risk score vì không có khối u để đánh giá."
        )

    label = result.get("tumor_label") or "chưa có nhãn"
    confidence = result.get("classification_confidence")
    confidence_text = f" với confidence {confidence * 100:.2f}%" if isinstance(confidence, (int, float)) else ""
    xai_parts = []
    if result.get("detection_xai_data_url"):
        xai_parts.append("ODAM")
    if result.get("segmentation_xai_data_url"):
        xai_parts.append("Seg-Eigen-CAM")
    if result.get("classification_xai_data_url"):
        xai_parts.append("Finer-CAM")
    xai_text = f" Đã sinh XAI: {', '.join(xai_parts)}." if xai_parts else ""
    return (
        f"Đã chạy xong MRI pipeline{patient_text}. Kết quả: phân loại {label}{confidence_text}."
        f"{xai_text} Tôi sẽ mở trang kết quả chi tiết để bác sĩ xem ảnh, mask, heatmap và xác nhận lại nhãn nếu cần."
    )


def _basic_agent_reply(request: AgentChatRequest) -> tuple[str, str, list[dict[str, Any]]]:
    message = request.message.lower().strip()
    actions: list[dict[str, Any]] = []

    if any(keyword in message for keyword in ["chuan doan", "chẩn đoán", "mri", "pipeline"]):
        actions.append({"type": "quick_mri_hint", "label": "Attach MRI và chọn/nhập mã bệnh nhân"})
        return (
            "quick_mri",
            "Bác sĩ có thể attach ảnh MRI trực tiếp trong chatbox. Nếu chưa có mã bệnh nhân, tôi sẽ yêu cầu chọn bệnh nhân trước khi chạy pipeline.",
            actions,
        )

    if any(keyword in message for keyword in ["review", "xac nhan", "xác nhận", "chinh nhan", "chỉnh nhãn"]):
        actions.append({"type": "classification_review_hint", "image_id": request.image_id})
        return (
            "classification_review",
            "Tôi có thể mở form xác nhận hoặc chỉnh nhãn phân loại cho ảnh đang xem. Kết quả chỉ được ghi vào classification_reviews sau khi bác sĩ bấm xác nhận.",
            actions,
        )

    if any(keyword in message for keyword in ["lich su", "lịch sử", "timeline", "dien tien", "diễn tiến"]):
        return (
            "timeline_reasoning",
            "Tôi sẽ đọc lịch sử chẩn đoán của bệnh nhân từ database và tóm tắt diễn tiến theo từng lần chẩn đoán.",
            actions,
        )

    return (
        "general",
        "Tôi là NeuroDiagnosis Agent. Bác sĩ có thể hỏi về hồ sơ bệnh nhân, giải thích XAI, chạy chẩn đoán nhanh MRI qua chatbox, hoặc mở form xác nhận/chỉnh nhãn.",
        actions,
    )


@router.post("/chat", response_model=AgentChatResponse)
def chat(
    request: AgentChatRequest,
    current_user: dict = Depends(get_current_user),
):
    intent, reply, actions = _basic_agent_reply(request)
    return AgentChatResponse(
        thread_id=request.thread_id or str(uuid.uuid4()),
        message=reply,
        intent=intent,
        actions=actions,
    )


@router.post("/chat/stream")
async def chat_stream(
    request: AgentChatRequest,
    current_user: dict = Depends(get_current_user),
):
    intent, reply, actions = _basic_agent_reply(request)
    thread_id = request.thread_id or str(uuid.uuid4())

    async def event_generator():
        yield f"event: tool_start\ndata: {json.dumps({'tool': 'route_intent', 'thread_id': thread_id})}\n\n"
        yield f"event: tool_result\ndata: {json.dumps({'intent': intent, 'actions': actions})}\n\n"
        for token in reply.split(" "):
            yield f"event: token\ndata: {json.dumps(token + ' ')}\n\n"
        yield f"event: final\ndata: {json.dumps({'thread_id': thread_id, 'intent': intent, 'message': reply, 'actions': actions})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/patients/search")
def search_patients(
    q: str = "",
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    keyword = f"%{q.strip()}%"
    query = db.query(models.Patient)
    if q.strip():
        query = query.filter(
            or_(
                models.Patient.patient_external_id.ilike(keyword),
                models.Patient.name.ilike(keyword),
            )
        )
    patients = query.order_by(models.Patient.id.desc()).limit(min(limit, 30)).all()
    return {
        "items": [
            {
                "id": patient.id,
                "patient_external_id": patient.patient_external_id,
                "name": patient.name,
                "age": patient.age,
                "gender": patient.gender,
            }
            for patient in patients
        ]
    }


@router.post("/quick-mri")
async def quick_mri_diagnosis(
    patient_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if not patient_id:
        raise HTTPException(
            status_code=409,
            detail={
                "type": "select_patient",
                "reason": "Cần chọn bệnh nhân để lưu ảnh MRI và kết quả chẩn đoán.",
            },
        )

    patient = crud.get_patient_by_id_or_external(db, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy bệnh nhân '{patient_id}'")

    ensure_bucket_exists(BUCKET_NAME)

    try:
        file_bytes = await file.read()
        prepared_stream, content_type = prepare_mri_upload(file_bytes, file.filename)
        unique_filename = f"{uuid.uuid4()}_{file.filename or 'chat_mri'}"

        minio_client.put_object(
            bucket_name=BUCKET_NAME,
            object_name=unique_filename,
            data=prepared_stream,
            length=prepared_stream.getbuffer().nbytes,
            content_type=content_type,
        )

        image = models.Image(
            patient_id=patient.id,
            modality="MRI",
            file_path=f"/{BUCKET_NAME}/{unique_filename}",
        )
        db.add(image)
        db.commit()
        db.refresh(image)

        task = _create_inference_task(
            db=db,
            task_type="mri_pipeline",
            target_id=image.id,
            celery_signature="tasks.run_mri_pipeline",
        )

        return {
            "message": "Đã upload MRI qua chatbox và tạo task MRI pipeline.",
            "patient": {
                "id": patient.id,
                "patient_external_id": patient.patient_external_id,
                "name": patient.name,
            },
            "image_id": image.id,
            "task_id": task.id,
            "status": task.status,
            "summary": _summarize_image_result(None, patient),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi quick MRI diagnosis: {exc}") from exc


@router.get("/quick-mri/{image_id}/summary")
def quick_mri_summary(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    image = db.query(models.Image).filter(models.Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh MRI")

    patient = db.query(models.Patient).filter(models.Patient.id == image.patient_id).first()
    task = (
        db.query(models.InferenceTask)
        .filter(
            models.InferenceTask.task_type == "mri_pipeline",
            models.InferenceTask.target_id == image_id,
        )
        .order_by(models.InferenceTask.created_at.desc())
        .first()
    )
    analysis = db.query(models.AnalysisResult).filter(models.AnalysisResult.image_id == image_id).first()
    result_payload = task.result if task and isinstance(task.result, dict) else {}
    result = {
        "no_tumor_detected": analysis.no_tumor_detected if analysis else result_payload.get("no_tumor_detected"),
        "tumor_label": analysis.tumor_label if analysis else result_payload.get("tumor_label"),
        "classification_confidence": analysis.classification_confidence if analysis else result_payload.get("classification_confidence"),
        "detection_xai_data_url": result_payload.get("detection_xai_path") or result_payload.get("odam_path"),
        "segmentation_xai_data_url": result_payload.get("segmentation_xai_path") or result_payload.get("seg_eigen_cam_path"),
        "classification_xai_data_url": result_payload.get("classification_xai_path"),
    }
    return {
        "image_id": image_id,
        "patient_id": patient.patient_external_id or str(patient.id) if patient else str(image.patient_id),
        "status": task.status if task else "unknown",
        "summary": _summarize_image_result(result, patient),
        "result": result,
    }


@router.get("/notifications")
def notifications(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    low_confidence = (
        db.query(models.AnalysisResult)
        .filter(
            models.AnalysisResult.no_tumor_detected.is_(False),
            models.AnalysisResult.classification_confidence.isnot(None),
            models.AnalysisResult.classification_confidence < 0.95,
        )
        .count()
    )
    stale_risk = (
        db.query(models.AnalysisResult)
        .filter(
            models.AnalysisResult.no_tumor_detected.is_(True),
            models.AnalysisResult.risk_score.isnot(None),
        )
        .count()
    )
    items = []
    if low_confidence:
        items.append({"type": "review_required", "message": f"Có {low_confidence} ca confidence thấp cần review."})
    if stale_risk:
        items.append({"type": "stale_risk", "message": f"Có {stale_risk} ca không phát hiện u nhưng vẫn có risk score."})
    return {"items": items}
