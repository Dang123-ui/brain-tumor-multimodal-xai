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


def _patient_display(patient: models.Patient) -> str:
    code = patient.patient_external_id or str(patient.id)
    name = patient.name or "Bá»‡nh nhÃ¢n"
    return f"{name} ({code})"


def _summarize_image_result(result: dict[str, Any] | None, patient: models.Patient | None = None) -> str:
    patient_text = f" cho {_patient_display(patient)}" if patient else ""
    if not result:
        return f"ÄÃ£ táº¡o task phÃ¢n tÃ­ch MRI{patient_text}. TÃ´i sáº½ tiáº¿p tá»¥c theo dÃµi tiáº¿n trÃ¬nh vÃ  tÃ³m táº¯t khi cÃ³ káº¿t quáº£."

    if result.get("no_tumor_detected"):
        return (
            f"ÄÃ£ cháº¡y xong MRI pipeline{patient_text}. Káº¿t quáº£: khÃ´ng phÃ¡t hiá»‡n khá»‘i u trÃªn áº£nh MRI nÃ y. "
            "KhÃ´ng cháº¡y tiÃªn lÆ°á»£ng/risk score vÃ¬ khÃ´ng cÃ³ khá»‘i u Ä‘á»ƒ Ä‘Ã¡nh giÃ¡."
        )

    label = result.get("tumor_label") or "chÆ°a cÃ³ nhÃ£n"
    confidence = result.get("classification_confidence")
    confidence_text = f" vá»›i confidence {confidence * 100:.2f}%" if isinstance(confidence, (int, float)) else ""
    xai_parts = []
    if result.get("detection_xai_data_url"):
        xai_parts.append("ODAM")
    if result.get("segmentation_xai_data_url"):
        xai_parts.append("Seg-Eigen-CAM")
    if result.get("classification_xai_data_url"):
        xai_parts.append("Finer-CAM")
    xai_text = f" ÄÃ£ sinh XAI: {', '.join(xai_parts)}." if xai_parts else ""
    return (
        f"ÄÃ£ cháº¡y xong MRI pipeline{patient_text}. Káº¿t quáº£: phÃ¢n loáº¡i {label}{confidence_text}."
        f"{xai_text} TÃ´i sáº½ má»Ÿ trang káº¿t quáº£ chi tiáº¿t Ä‘á»ƒ bÃ¡c sÄ© xem áº£nh, mask, heatmap vÃ  xÃ¡c nháº­n láº¡i nhÃ£n náº¿u cáº§n."
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
                "reason": "Cáº§n chá»n bá»‡nh nhÃ¢n Ä‘á»ƒ lÆ°u áº£nh MRI vÃ  káº¿t quáº£ cháº©n Ä‘oÃ¡n.",
            },
        )

    patient = crud.get_patient_by_id_or_external(db, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail=f"KhÃ´ng tÃ¬m tháº¥y bá»‡nh nhÃ¢n '{patient_id}'")

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
            "message": "ÄÃ£ upload MRI qua chatbox vÃ  táº¡o task MRI pipeline.",
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
        raise HTTPException(status_code=500, detail=f"Lá»—i quick MRI diagnosis: {exc}") from exc


@router.get("/quick-mri/{image_id}/summary")
def quick_mri_summary(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    image = db.query(models.Image).filter(models.Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="KhÃ´ng tÃ¬m tháº¥y áº£nh MRI")

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
        items.append({"type": "review_required", "message": f"CÃ³ {low_confidence} ca confidence tháº¥p cáº§n review."})
    if stale_risk:
        items.append({"type": "stale_risk", "message": f"CÃ³ {stale_risk} ca khÃ´ng phÃ¡t hiá»‡n u nhÆ°ng váº«n cÃ³ risk score."})
    return {"items": items}

