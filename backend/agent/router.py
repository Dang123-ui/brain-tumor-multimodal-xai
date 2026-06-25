import json
import os
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

import crud
import models
from agent.graph import run_agent
from agent.llm import get_agent_model
from agent.memory import (
    list_conversations,
    load_conversation_messages,
    soft_delete_conversation,
    trim_messages,
    update_conversation_summary,
)
from agent.schemas import AgentChatRequest, AgentChatResponse
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


def _current_user_id(current_user: dict) -> int | None:
    raw = current_user.get("user_id") or current_user.get("sub") or current_user.get("id")
    try:
        return int(raw)
    except Exception:
        return None


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


@router.post("/chat", response_model=AgentChatResponse)
def chat(
    request: AgentChatRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = run_agent(
        db=db,
        current_user=current_user,
        message=request.message,
        thread_id=request.thread_id,
        patient_id=request.patient_id,
        image_id=request.image_id,
        selected_region=request.selected_region,
    )
    return AgentChatResponse(
        thread_id=result["thread_id"],
        message=result.get("final_response") or "",
        intent=result.get("intent") or "general",
        actions=result.get("actions") or [],
        tool_results=result.get("tool_results") or {},
    )


@router.post("/chat/stream")
async def chat_stream(
    request: AgentChatRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = run_agent(
        db=db,
        current_user=current_user,
        message=request.message,
        thread_id=request.thread_id,
        patient_id=request.patient_id,
        image_id=request.image_id,
        selected_region=request.selected_region,
    )
    intent = result.get("intent") or "general"
    reply = result.get("final_response") or ""
    actions = result.get("actions") or []
    thread_id = result["thread_id"]

    async def event_generator():
        yield f"event: tool_start\ndata: {json.dumps({'tool': 'route_intent', 'thread_id': thread_id})}\n\n"
        yield f"event: tool_result\ndata: {json.dumps({'intent': intent, 'actions': actions, 'tool_results': result.get('tool_results')}, ensure_ascii=False)}\n\n"
        for token in reply.split(" "):
            yield f"event: token\ndata: {json.dumps(token + ' ', ensure_ascii=False)}\n\n"
        yield f"event: final\ndata: {json.dumps({'thread_id': thread_id, 'intent': intent, 'message': reply, 'actions': actions}, ensure_ascii=False)}\n\n"

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


@router.get("/conversations")
def get_conversations(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = _current_user_id(current_user)
    conversations = list_conversations(db, user_id=user_id)
    return {
        "items": [
            {
                "thread_id": item.thread_id,
                "patient_id": item.patient_id,
                "image_id": item.image_id,
                "title": item.title,
                "status": item.status,
                "summary": item.summary,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            for item in conversations
        ]
    }


@router.get("/conversations/{thread_id}")
def get_conversation(
    thread_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    messages = load_conversation_messages(db, thread_id)
    return {
        "thread_id": thread_id,
        "messages": [
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "message_type": message.message_type,
                "metadata": message.metadata_json,
                "created_at": message.created_at,
            }
            for message in messages
        ],
    }


@router.delete("/conversations/{thread_id}")
def delete_conversation(
    thread_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    deleted = soft_delete_conversation(db, thread_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy hội thoại")
    return {"deleted": True}


@router.post("/conversations/{thread_id}/trim")
def trim_conversation(
    thread_id: str,
    keep_last: int = 20,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    deleted_count = trim_messages(db, thread_id, keep_last=max(4, min(keep_last, 100)))
    return {"thread_id": thread_id, "trimmed_messages": deleted_count}


@router.post("/conversations/{thread_id}/summarize")
def summarize_conversation(
    thread_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    messages = load_conversation_messages(db, thread_id, limit=80)
    if not messages:
        raise HTTPException(status_code=404, detail="Không có tin nhắn để tóm tắt")

    transcript = "\n".join(f"{msg.role}: {msg.content}" for msg in messages if msg.content)
    try:
        model = get_agent_model()
        response = model.invoke(
            [
                ("system", "Tóm tắt hội thoại y khoa bằng tiếng Việt, ngắn gọn, giữ các quyết định quan trọng."),
                ("human", transcript),
            ]
        )
        summary = getattr(response, "content", str(response))
    except Exception as exc:
        summary = f"Không thể gọi LLM để tóm tắt: {exc}"

    update_conversation_summary(db, thread_id, summary)
    return {"thread_id": thread_id, "summary": summary}


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

