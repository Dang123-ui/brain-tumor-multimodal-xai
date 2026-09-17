import hashlib
import datetime
import json
import os
import re
import shutil
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

import crud
import models
import schemas
from database import get_db
from review_utils import classification_review_state
from utils import get_current_user, minio_client

router = APIRouter(prefix="/records", tags=["Records"])
BUCKET_NAME = os.getenv("MINIO_BUCKET") or os.getenv("R2_BUCKET") or "medical-data"
REPORT_TYPE_DIAGNOSIS_HISTORY = "diagnosis_history"
REPORT_PROMPT_VERSION = "patient-history-v1"
NO_TUMOR_LABEL = "Không phát hiện khối u"


def _natural_sort_key(text: str):
    """Tach chuoi thanh so va chu de sap xep tu nhien: patch_2 < patch_10."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]


def _parse_storage_path(file_path: str | None) -> tuple[str, str] | None:
    if not file_path:
        return None
    normalized = file_path.lstrip("/")
    if "/" in normalized:
        bucket_name, object_name = normalized.split("/", 1)
        return bucket_name, object_name
    return BUCKET_NAME, normalized

LABEL_MAP = {
    "class_0": "Glioma",
    "class_1": "Meningioma",
    "class_2": "Pituitary tumor",
}


def _display_diagnosis(label: str | None) -> str | None:
    if not label:
        return None
    return LABEL_MAP.get(label, label)


def _diagnosis_label(label: str | None, no_tumor_detected: bool = False) -> str | None:
    if no_tumor_detected:
        return NO_TUMOR_LABEL
    return _display_diagnosis(label)


def _safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _pct(value):
    number = _safe_float(value)
    if number is None:
        return "chua co"
    return f"{number * 100:.2f}%"


def _risk_display(value: str | None) -> str:
    if not value:
        return "chua co"
    lowered = str(value).lower()
    if lowered == "high":
        return "nguy co cao"
    if lowered == "low":
        return "nguy co thap"
    return str(value)


def _image_preview_url(image: models.Image) -> str | None:
    if image.is_series:
        return f"/records/analysis/image/{image.id}/slice/{image.key_slice_index or 0}"

    storage_path = _parse_storage_path(image.file_path)
    if not storage_path:
        return None

    bucket_name, object_name = storage_path
    try:
        from utils import build_minio_presigned_url
        return build_minio_presigned_url(bucket_name, object_name)
    except Exception:
        return None


def _latest_mri_task(db: Session, image_id: int) -> models.InferenceTask | None:
    return (
        db.query(models.InferenceTask)
        .filter(
            models.InferenceTask.task_type == "mri_pipeline",
            models.InferenceTask.target_id == image_id,
        )
        .order_by(models.InferenceTask.created_at.desc())
        .first()
    )


def _report_texts_ready(report: models.PatientHistoryReport | None, data_hash: str) -> bool:
    if not report:
        return False
    required = [
        report.summary_text,
        report.classification_trend_text,
        report.risk_trend_text,
        report.conclusion_text,
    ]
    return report.status == "ready" and report.data_hash == data_hash and all(bool((item or "").strip()) for item in required)


def _build_patient_history_payload(db: Session, patient: models.Patient) -> dict:
    images = (
        db.query(models.Image)
        .filter(
            models.Image.patient_id == patient.id,
            models.Image.modality.in_(["MRI", "MRI_SERIES"]),
        )
        .order_by(models.Image.scan_date.desc())
        .all()
    )

    timeline = []
    for display_idx, img in enumerate(images, start=1):
        analysis = db.query(models.AnalysisResult).filter(models.AnalysisResult.image_id == img.id).first()
        latest_task = _latest_mri_task(db, img.id)
        status = "done" if analysis else "ready"
        if latest_task:
            status = latest_task.status
        no_tumor_detected = bool(analysis and getattr(analysis, "no_tumor_detected", False))
        ai_label = _diagnosis_label(analysis.tumor_label, no_tumor_detected) if analysis else None
        ai_confidence = None if no_tumor_detected else (analysis.classification_confidence if analysis else None)
        review_state = classification_review_state(db, img.id, ai_label, ai_confidence)

        timeline.append(
            {
                "diagnosis_index": display_idx,
                "image_id": img.id,
                "modality": img.modality,
                "scan_date": img.scan_date.isoformat() if img.scan_date else None,
                "image_url": _image_preview_url(img),
                "ai_status": status,
                "no_tumor_detected": no_tumor_detected,
                "tumor_label": ai_label,
                "classification_confidence": ai_confidence,
                "ai_tumor_label": review_state["ai_tumor_label"],
                "final_tumor_label": review_state["final_tumor_label"],
                "expert_tumor_label": review_state["expert_tumor_label"],
                "review_status": review_state["review_status"],
                "review_required": review_state["review_required"],
                "expert_comment": review_state["expert_comment"],
                "risk_score": None if no_tumor_detected else (analysis.risk_score if analysis else None),
                "risk_group": None if no_tumor_detected else (analysis.risk_group if analysis else None),
                "is_series": bool(img.is_series),
                "num_slices": img.num_slices or 1,
                "key_slice_index": img.key_slice_index or 0,
            }
        )

    chronological = list(reversed(timeline))
    for idx, item in enumerate(chronological, start=1):
        item["chronological_index"] = idx
        item["diagnosis_index"] = idx

    risk_trend = [
        {
            "diagnosis_index": item["chronological_index"],
            "risk_score": item["risk_score"],
            "risk_group": item["risk_group"],
            "scan_date": item["scan_date"],
            "tumor_label": item["tumor_label"],
            "classification_confidence": item["classification_confidence"],
        }
        for item in chronological
        if item.get("risk_score") is not None
    ]
    no_tumor_risk_notes = [
        {
            "diagnosis_index": item["chronological_index"],
            "scan_date": item["scan_date"],
            "message": f"Lần {item['chronological_index']} không phát hiện khối u nên không tính risk score.",
        }
        for item in chronological
        if item.get("no_tumor_detected")
    ]

    rna_record = (
        db.query(models.RnaData)
        .filter(models.RnaData.patient_id == patient.id)
        .order_by(models.RnaData.upload_date.desc())
        .first()
    )
    wsi_count = (
        db.query(models.Image)
        .filter(models.Image.patient_id == patient.id, models.Image.modality.in_(["WSI", "WSI_SERIES"]))
        .count()
    )

    validations = (
        db.query(models.ExpertValidation)
        .filter(models.ExpertValidation.image_id.in_([item["image_id"] for item in timeline] or [-1]))
        .order_by(models.ExpertValidation.created_at.desc())
        .all()
    )

    latest = timeline[0] if timeline else {}
    payload = {
        "patient": {
            "id": patient.id,
            "name": patient.name,
            "external_id": patient.patient_external_id,
            "age": patient.age,
            "gender": patient.gender,
        },
        "summary": {
            "diagnosis_count": len(timeline),
            "latest_tumor_label": latest.get("tumor_label"),
            "latest_final_tumor_label": latest.get("final_tumor_label"),
            "latest_review_status": latest.get("review_status"),
            "latest_review_required": latest.get("review_required"),
            "review_required_count": len([item for item in timeline if item.get("review_required")]),
            "review_corrected_count": len([item for item in timeline if item.get("review_status") == "corrected"]),
            "review_confirmed_count": len([item for item in timeline if item.get("review_status") == "confirmed"]),
            "latest_classification_confidence": latest.get("classification_confidence"),
            "latest_risk_score": latest.get("risk_score"),
            "latest_risk_group": latest.get("risk_group"),
            "last_diagnosis_time": latest.get("scan_date"),
            "latest_no_tumor_detected": latest.get("no_tumor_detected"),
        },
        "timeline": timeline,
        "risk_trend": risk_trend,
        "no_tumor_risk_notes": no_tumor_risk_notes,
        "multimodal_data": {
            "has_mri": len(timeline) > 0,
            "has_wsi": wsi_count > 0,
            "has_rna": rna_record is not None,
            "has_clinical": patient.clinical_data is not None,
            "rna_uploaded_at": rna_record.upload_date.isoformat() if rna_record else None,
            "clinical_updated_at": patient.clinical_data.updated_at.isoformat()
            if patient.clinical_data and patient.clinical_data.updated_at
            else None,
        },
        "expert_validations": [
            {
                "image_id": item.image_id,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "rating": item.rating,
                "comments": item.comments,
            }
            for item in validations
        ],
    }
    return payload


def _history_data_hash(payload: dict) -> str:
    relevant = {
        "patient": payload.get("patient"),
        "summary": payload.get("summary"),
        "timeline": [
            {
                "image_id": item.get("image_id"),
                "scan_date": item.get("scan_date"),
                "modality": item.get("modality"),
                "ai_status": item.get("ai_status"),
                "tumor_label": item.get("tumor_label"),
                "classification_confidence": item.get("classification_confidence"),
                "final_tumor_label": item.get("final_tumor_label"),
                "no_tumor_detected": item.get("no_tumor_detected"),
                "review_status": item.get("review_status"),
                "expert_comment": item.get("expert_comment"),
                "risk_score": item.get("risk_score"),
                "risk_group": item.get("risk_group"),
            }
            for item in payload.get("timeline", [])
        ],
        "multimodal_data": payload.get("multimodal_data"),
        "expert_validations": payload.get("expert_validations"),
    }
    raw = json.dumps(relevant, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _fallback_history_texts(payload: dict) -> dict[str, str]:
    summary = payload.get("summary", {})
    timeline = payload.get("timeline", [])
    risk_trend = payload.get("risk_trend", [])
    latest_label = summary.get("latest_tumor_label") or "chua co ket qua phan loai"
    latest_no_tumor = bool(summary.get("latest_no_tumor_detected"))
    latest_conf = _pct(summary.get("latest_classification_confidence"))
    latest_risk = summary.get("latest_risk_score")
    latest_risk_text = "chua co" if latest_risk is None else f"{latest_risk:.4f}"
    latest_group = _risk_display(summary.get("latest_risk_group"))
    no_tumor_items = [item for item in reversed(timeline) if item.get("no_tumor_detected")]

    labels = [item.get("tumor_label") for item in reversed(timeline) if item.get("tumor_label")]
    unique_labels = list(dict.fromkeys(labels))
    if not labels:
        class_trend = "Chua co du lieu phan loai du de nhan xet xu huong theo thoi gian."
    elif len(unique_labels) == 1:
        class_trend = f"Cac lan chan doan co ket qua phan loai on dinh voi nhan {unique_labels[0]}."
    else:
        class_trend = f"Nhãn phân loại thay đổi qua các lần chẩn đoán: {', '.join(unique_labels)}. Can doi chieu chat luong anh va danh gia chuyen khoa."

    if no_tumor_items:
        no_tumor_text = ", ".join([f"lan {item.get('chronological_index')}" for item in no_tumor_items])
        class_trend += f" Luu y: {no_tumor_text} khong con phat hien khoi u."

    if len(risk_trend) >= 2:
        first = _safe_float(risk_trend[0].get("risk_score")) or 0
        last = _safe_float(risk_trend[-1].get("risk_score")) or 0
        direction = "tang" if last > first else "giam" if last < first else "on dinh"
        risk_text = f"Risk score co xu huong {direction} tu {first:.4f} den {last:.4f} qua {len(risk_trend)} lan co du lieu tien luong."
    elif len(risk_trend) == 1:
        risk_text = f"Hien chi co mot diem risk score ({risk_trend[0].get('risk_score'):.4f}), chua du de danh gia xu huong."
    else:
        risk_text = "Chua co du lieu risk score de ve va nhan xet xu huong tien luong."
    if no_tumor_items:
        skipped = ", ".join([f"lan {item.get('chronological_index')}" for item in no_tumor_items])
        risk_text += f" Luu y: {skipped} khong phat hien khoi u nen khong tinh risk score."

    return {
        "summary_text": (
            f"Benh nhan co {len(timeline)} lan upload/chan doan MRI trong he thong. "
            + (
                f"Ket qua gan nhat ghi nhan {NO_TUMOR_LABEL}; khong tinh risk score cho lan nay."
                if latest_no_tumor
                else f"Ket qua gan nhat ghi nhan {latest_label} voi do tin cay {latest_conf}; risk score gan nhat la {latest_risk_text}, thuoc nhom {latest_group}."
            )
        ),
        "classification_trend_text": class_trend,
        "risk_trend_text": risk_text,
        "conclusion_text": (
            (
                f"Ket qua gan nhat la {NO_TUMOR_LABEL}; risk score/risk group khong ap dung cho lan nay. "
                if latest_no_tumor
                else f"Ket qua gan nhat la {latest_label}, risk group {latest_group}. "
            )
            + "Bao cao nay tong hop lich su AI theo du lieu da luu va chi co vai tro ho tro tham khao; "
            + "can doi chieu voi danh gia lam sang cua bac si chuyen khoa."
        ),
    }


def _generate_history_texts(payload: dict) -> tuple[dict[str, str], str]:
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    api_key = os.getenv("GEMINI_API_KEY")
    fallback = _fallback_history_texts(payload)
    if not api_key:
        return fallback, model_name

    try:
        import google.generativeai as genai

        prompt = f"""
Ban la tro ly viet bao cao y khoa tieng Viet trong he thong NeuroDiagnosis AI.
Chi dua tren JSON du lieu duoc cung cap, khong bia them so lieu hay chan doan.
Viet ngan gon, than trong, tu nhien. Khong dua phac do dieu tri.

Hay tra ve JSON hop le voi dung 4 key:
summary_text, classification_trend_text, risk_trend_text, conclusion_text.

Du lieu:
{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}
""".strip()

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            [prompt],
            generation_config={"temperature": 0.15, "top_p": 0.9, "max_output_tokens": 1800},
        )
        text = (getattr(response, "text", None) or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.MULTILINE).strip()
        parsed = json.loads(text)
        result = {
            "summary_text": str(parsed.get("summary_text") or fallback["summary_text"]).strip(),
            "classification_trend_text": str(parsed.get("classification_trend_text") or fallback["classification_trend_text"]).strip(),
            "risk_trend_text": str(parsed.get("risk_trend_text") or fallback["risk_trend_text"]).strip(),
            "conclusion_text": str(parsed.get("conclusion_text") or fallback["conclusion_text"]).strip(),
        }
        return result, model_name
    except Exception as exc:
        print(f"[HistoryReport] LLM generation failed, using fallback: {exc}")
        return fallback, model_name


def _get_or_create_history_report(db: Session, patient_id: int) -> models.PatientHistoryReport:
    report = (
        db.query(models.PatientHistoryReport)
        .filter(
            models.PatientHistoryReport.patient_id == patient_id,
            models.PatientHistoryReport.report_type == REPORT_TYPE_DIAGNOSIS_HISTORY,
        )
        .order_by(models.PatientHistoryReport.updated_at.desc())
        .first()
    )
    if report:
        return report

    report = models.PatientHistoryReport(
        patient_id=patient_id,
        report_type=REPORT_TYPE_DIAGNOSIS_HISTORY,
        status="not_created",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def _history_report_status(db: Session, patient: models.Patient) -> tuple[str, str]:
    payload = _build_patient_history_payload(db, patient)
    data_hash = _history_data_hash(payload)
    report = (
        db.query(models.PatientHistoryReport)
        .filter(
            models.PatientHistoryReport.patient_id == patient.id,
            models.PatientHistoryReport.report_type == REPORT_TYPE_DIAGNOSIS_HISTORY,
        )
        .order_by(models.PatientHistoryReport.updated_at.desc())
        .first()
    )
    if _report_texts_ready(report, data_hash):
        return "ready", data_hash
    if report and report.status == "generating":
        return "generating", data_hash
    if report and report.status == "failed":
        return "failed", data_hash
    if report and report.data_hash and report.data_hash != data_hash:
        return "stale", data_hash
    return "not_created", data_hash


def _make_history_report_response(db: Session, patient: models.Patient, generate_if_missing: bool = False) -> dict:
    payload = _build_patient_history_payload(db, patient)
    data_hash = _history_data_hash(payload)
    report = _get_or_create_history_report(db, patient.id)

    if generate_if_missing and not _report_texts_ready(report, data_hash):
        report.status = "generating"
        report.error_message = None
        db.commit()
        try:
            texts, model_name = _generate_history_texts(payload)
            report.summary_text = texts["summary_text"]
            report.classification_trend_text = texts["classification_trend_text"]
            report.risk_trend_text = texts["risk_trend_text"]
            report.conclusion_text = texts["conclusion_text"]
            report.llm_model = model_name
            report.prompt_version = REPORT_PROMPT_VERSION
            report.source_metadata = payload
            report.data_hash = data_hash
            report.status = "ready"
            report.error_message = None
            db.commit()
            db.refresh(report)
        except Exception as exc:
            report.status = "failed"
            report.error_message = str(exc)
            db.commit()
            db.refresh(report)

    status = "ready" if _report_texts_ready(report, data_hash) else report.status
    if report.data_hash and report.data_hash != data_hash and status == "ready":
        status = "stale"
    fallback_texts = _fallback_history_texts(payload)
    display_texts = {
        "summary_text": report.summary_text,
        "classification_trend_text": report.classification_trend_text,
        "risk_trend_text": report.risk_trend_text,
        "conclusion_text": report.conclusion_text,
    }
    if status != "ready":
        display_texts = fallback_texts

    return {
        **payload,
        "report_status": status,
        "data_hash": data_hash,
        "texts": display_texts,
        "error_message": report.error_message,
    }


def _build_history_pdf(report: dict) -> bytes:
    page = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(page)
    font_title = ImageFont.load_default()
    font = ImageFont.load_default()

    y = 60
    patient = report["patient"]
    draw.text((60, y), "BAO CAO LICH SU CHAN DOAN BENH NHAN", fill=(15, 23, 42), font=font_title)
    y += 45
    draw.text((60, y), f"Benh nhan: {patient.get('name') or '-'} | Ma: {patient.get('external_id') or patient.get('id')}", fill=(30, 41, 59), font=font)
    y += 45

    sections = [
        ("1. Thong tin tom tat", report["texts"].get("summary_text")),
        ("2. Dien tien phan loai u", report["texts"].get("classification_trend_text")),
        ("3. Dien tien risk score", report["texts"].get("risk_trend_text")),
        ("4. Ket luan tong hop", report["texts"].get("conclusion_text")),
    ]
    for title, text in sections:
        draw.text((60, y), title, fill=(14, 116, 144), font=font_title)
        y += 28
        for line in re.findall(".{1,120}(?:\\s+|$)", text or "Chua co du lieu."):
            draw.text((80, y), line.strip(), fill=(30, 41, 59), font=font)
            y += 22
        y += 18

    draw.text((60, y), "Timeline chan doan", fill=(14, 116, 144), font=font_title)
    y += 32
    for item in report.get("timeline", [])[:12]:
        row = (
            f"Lan {item.get('diagnosis_index')}: {item.get('scan_date') or '-'} | "
            f"{item.get('modality') or '-'} | {item.get('tumor_label') or '-'} | "
            f"conf={_pct(item.get('classification_confidence'))} | "
            f"risk={item.get('risk_score') if item.get('risk_score') is not None else '-'} | "
            f"group={item.get('risk_group') or '-'}"
        )
        draw.text((80, y), row[:160], fill=(30, 41, 59), font=font)
        y += 22
        if y > 1660:
            break

    buffer = BytesIO()
    page.save(buffer, format="PDF", resolution=150)
    return buffer.getvalue()


@router.post("/patients/", status_code=201)
def create_patient(
    patient: schemas.PatientCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    new_patient = models.Patient(
        owner_user_id=crud.current_user_id(current_user),
        name=patient.name,
        patient_external_id=patient.external_id,
        age=patient.age,
        gender=patient.gender,
    )
    db.add(new_patient)
    db.commit()
    db.refresh(new_patient)
    return {
        "id": new_patient.id,
        "name": new_patient.name,
        "external_id": new_patient.patient_external_id,
        "age": new_patient.age,
        "gender": new_patient.gender,
    }


@router.get("/patients/")
def get_all_patients(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    patients = crud.patient_query_for_user(db, current_user).all()
    response = []

    for patient in patients:
        latest_image = (
            db.query(models.Image)
            .filter(models.Image.patient_id == patient.id)
            .order_by(models.Image.scan_date.desc())
            .first()
        )
        latest_analysis = (
            db.query(models.AnalysisResult)
            .filter(models.AnalysisResult.patient_id == patient.id)
            .order_by(models.AnalysisResult.created_at.desc())
            .first()
        )
        no_tumor_detected = bool(latest_analysis and getattr(latest_analysis, "no_tumor_detected", False))
        review_state = classification_review_state(
            db,
            latest_analysis.image_id if latest_analysis else None,
            None if no_tumor_detected else (_display_diagnosis(latest_analysis.tumor_label) if latest_analysis else None),
            None if no_tumor_detected else (latest_analysis.classification_confidence if latest_analysis else None),
        )

        response.append(
            {
                "id": patient.id,
                "name": patient.name,
                "external_id": patient.patient_external_id,
                "age": patient.age,
                "gender": patient.gender,
                "lastVisit": latest_image.scan_date.isoformat() if latest_image and latest_image.scan_date else None,
                "no_tumor_detected": no_tumor_detected,
                "diagnosis": NO_TUMOR_LABEL if no_tumor_detected else review_state["final_tumor_label"],
                "aiDiagnosis": NO_TUMOR_LABEL if no_tumor_detected else review_state["ai_tumor_label"],
                "reviewStatus": review_state["review_status"],
                "reviewRequired": review_state["review_required"],
                "riskScore": None if no_tumor_detected else (latest_analysis.risk_score if latest_analysis and latest_analysis.risk_score is not None else None),
            }
        )

    return response


@router.get("/patients/diagnosis-history", response_model=schemas.DiagnosisHistoryListResponse)
def get_diagnosis_history_patients(
    search: str | None = None,
    risk_group: str | None = None,
    sort: str = "latest_desc",
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    patients = crud.patient_query_for_user(db, current_user).all()
    items = []
    query_text = (search or "").strip().lower()
    risk_filter = (risk_group or "").strip().lower()

    for patient in patients:
        mri_count = (
            db.query(models.Image)
            .filter(
                models.Image.patient_id == patient.id,
                models.Image.modality.in_(["MRI", "MRI_SERIES"]),
            )
            .count()
        )
        if mri_count == 0:
            continue

        latest_image = (
            db.query(models.Image)
            .filter(
                models.Image.patient_id == patient.id,
                models.Image.modality.in_(["MRI", "MRI_SERIES"]),
            )
            .order_by(models.Image.scan_date.desc())
            .first()
        )
        latest_analysis = (
            db.query(models.AnalysisResult)
            .filter(models.AnalysisResult.patient_id == patient.id)
            .order_by(models.AnalysisResult.created_at.desc())
            .first()
        )

        if query_text:
            haystack = " ".join(
                [
                    str(patient.id),
                    patient.name or "",
                    patient.patient_external_id or "",
                ]
            ).lower()
            if query_text not in haystack:
                continue

        latest_no_tumor_detected = bool(latest_analysis and getattr(latest_analysis, "no_tumor_detected", False))
        latest_risk_group = None if latest_no_tumor_detected else (latest_analysis.risk_group if latest_analysis else None)
        if risk_filter and risk_filter not in {"all", "tat_ca"}:
            if risk_filter == "na":
                if latest_risk_group:
                    continue
            elif (latest_risk_group or "").lower() != risk_filter:
                continue

        status, _data_hash = _history_report_status(db, patient)
        patient_analyses = (
            db.query(models.AnalysisResult)
            .filter(models.AnalysisResult.patient_id == patient.id)
            .all()
        )
        review_states = [
            classification_review_state(
                db,
                analysis.image_id,
                None if getattr(analysis, "no_tumor_detected", False) else _display_diagnosis(analysis.tumor_label),
                None if getattr(analysis, "no_tumor_detected", False) else analysis.classification_confidence,
            )
            for analysis in patient_analyses
        ]
        latest_review = classification_review_state(
            db,
            latest_analysis.image_id if latest_analysis else None,
            None if latest_no_tumor_detected else (_display_diagnosis(latest_analysis.tumor_label) if latest_analysis else None),
            None if latest_no_tumor_detected else (latest_analysis.classification_confidence if latest_analysis else None),
        )
        items.append(
            {
                "patient_id": patient.id,
                "patient_external_id": patient.patient_external_id,
                "patient_name": patient.name,
                "last_diagnosis_time": latest_image.scan_date if latest_image else None,
                "latest_no_tumor_detected": latest_no_tumor_detected,
                "latest_tumor_label": NO_TUMOR_LABEL if latest_no_tumor_detected else (_display_diagnosis(latest_analysis.tumor_label) if latest_analysis else None),
                "latest_classification_confidence": None if latest_no_tumor_detected else (latest_analysis.classification_confidence if latest_analysis else None),
                "latest_ai_tumor_label": NO_TUMOR_LABEL if latest_no_tumor_detected else latest_review["ai_tumor_label"],
                "latest_final_tumor_label": NO_TUMOR_LABEL if latest_no_tumor_detected else latest_review["final_tumor_label"],
                "latest_review_status": latest_review["review_status"],
                "latest_review_required": latest_review["review_required"],
                "review_required_count": len([item for item in review_states if item["review_required"]]),
                "review_corrected_count": len([item for item in review_states if item["review_status"] == "corrected"]),
                "review_confirmed_count": len([item for item in review_states if item["review_status"] == "confirmed"]),
                "latest_risk_score": None if latest_no_tumor_detected else (latest_analysis.risk_score if latest_analysis else None),
                "latest_risk_group": latest_risk_group,
                "diagnosis_count": mri_count,
                "history_report_status": status,
            }
        )

    reverse = sort not in {"latest_asc", "risk_asc", "name_asc"}
    if sort in {"risk_desc", "risk_asc"}:
        items.sort(key=lambda item: item["latest_risk_score"] if item["latest_risk_score"] is not None else -999999, reverse=reverse)
    elif sort in {"name_desc", "name_asc"}:
        items.sort(key=lambda item: (item["patient_name"] or "").lower(), reverse=reverse)
    else:
        items.sort(key=lambda item: item["last_diagnosis_time"] or datetime.datetime.min, reverse=reverse)

    safe_page = max(1, page)
    safe_size = min(max(1, page_size), 100)
    total = len(items)
    start = (safe_page - 1) * safe_size
    end = start + safe_size
    return {
        "items": items[start:end],
        "page": safe_page,
        "page_size": safe_size,
        "total": total,
    }


@router.get("/patients/{patient_id}/history-report", response_model=schemas.PatientHistoryReportResponse)
def get_patient_history_report(
    patient_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    patient = crud.get_patient_for_user(db, patient_id, current_user)
    if not patient:
        raise HTTPException(status_code=404, detail="Khong tim thay benh nhan")
    return _make_history_report_response(db, patient, generate_if_missing=False)


@router.post("/patients/{patient_id}/history-report/regenerate", response_model=schemas.PatientHistoryReportResponse)
def regenerate_patient_history_report(
    patient_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    patient = crud.get_patient_for_user(db, patient_id, current_user)
    if not patient:
        raise HTTPException(status_code=404, detail="Khong tim thay benh nhan")
    return _make_history_report_response(db, patient, generate_if_missing=True)


@router.get("/patients/{patient_id}/history-report/pdf")
def download_patient_history_report_pdf(
    patient_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    patient = crud.get_patient_for_user(db, patient_id, current_user)
    if not patient:
        raise HTTPException(status_code=404, detail="Khong tim thay benh nhan")

    report = _make_history_report_response(db, patient, generate_if_missing=False)
    if report["report_status"] != "ready":
        raise HTTPException(status_code=409, detail="Bao cao lich su chua san sang. Hay sinh nhan xet AI truoc.")

    pdf_bytes = _build_history_pdf(report)
    filename = f"patient_history_report_{patient.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/patients/{patient_id}")
def get_patient_records(
    patient_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    patient = crud.get_patient_for_user(db, patient_id, current_user)
    if not patient:
        raise HTTPException(status_code=404, detail="Khong tim thay benh nhan")

    images = (
        db.query(models.Image)
        .filter(models.Image.patient_id == patient.id)
        .order_by(models.Image.scan_date.desc())
        .all()
    )
    image_list = []

    for img in images:
        object_name = img.file_path.split("/")[-1]
        try:
            url = minio_client.presigned_get_object(bucket_name=BUCKET_NAME, object_name=object_name)
        except Exception:
            url = None

        latest_task = (
            db.query(models.InferenceTask)
            .filter(
                models.InferenceTask.task_type == "mri_pipeline",
                models.InferenceTask.target_id == img.id,
            )
            .order_by(models.InferenceTask.created_at.desc())
            .first()
        )
        image_analysis = db.query(models.AnalysisResult).filter(models.AnalysisResult.image_id == img.id).first()
        no_tumor_detected = bool(image_analysis and getattr(image_analysis, "no_tumor_detected", False))
        review_state = classification_review_state(
            db,
            img.id,
            None if no_tumor_detected else (_display_diagnosis(image_analysis.tumor_label) if image_analysis else None),
            None if no_tumor_detected else (image_analysis.classification_confidence if image_analysis else None),
        )

        ai_status = "done" if image_analysis else "ready"
        latest_task_id = None
        latest_error_message = None
        if latest_task:
            ai_status = latest_task.status
            latest_task_id = latest_task.id
            latest_error_message = latest_task.error_message

        image_list.append(
            {
                "image_id": img.id,
                "modality": img.modality,
                "scan_date": img.scan_date,
                "minio_url": url,
                "image_url": url,
                "ai_status": ai_status,
                "latest_task_id": latest_task_id,
                "latest_error_message": latest_error_message,
                "has_analysis": image_analysis is not None,
                "no_tumor_detected": no_tumor_detected,
                "tumor_label": None if no_tumor_detected else (_display_diagnosis(image_analysis.tumor_label) if image_analysis else None),
                "classification_confidence": None if no_tumor_detected else (image_analysis.classification_confidence if image_analysis else None),
                "ai_tumor_label": review_state["ai_tumor_label"],
                "final_tumor_label": review_state["final_tumor_label"],
                "expert_tumor_label": review_state["expert_tumor_label"],
                "expert_comment": review_state["expert_comment"],
                "review_required": review_state["review_required"],
                "review_status": review_state["review_status"],
                "review_action": review_state["review_action"],
                "reviewed_at": review_state["reviewed_at"],
                "risk_score": None if no_tumor_detected else (image_analysis.risk_score if image_analysis else None),
                "risk_group": None if no_tumor_detected else (image_analysis.risk_group if image_analysis else None),
                "is_series": img.is_series,
                "num_slices": img.num_slices,
                "key_slice_index": img.key_slice_index,
            }
        )

    rna_record = db.query(models.RnaData).filter(models.RnaData.patient_id == patient.id).order_by(models.RnaData.upload_date.desc()).first()
    
    return {
        "patient": {
            "id": patient.id,
            "name": patient.name,
            "external_id": patient.patient_external_id,
            "age": patient.age,
            "gender": patient.gender,
        },
        "images": image_list,
        "rna_uploaded": rna_record is not None,
        "rna_info": {
            "filename": rna_record.file_path.split("/")[-1].split("_", 1)[-1] if rna_record else None,
            "uploaded_at": rna_record.upload_date.isoformat() if rna_record else None,
        } if rna_record else None,
        "clinical_data": {
            "ki67_index": patient.clinical_data.ki67_index,
            "biochemistry_markers": patient.clinical_data.biochemistry_markers,
            "initial_status": patient.clinical_data.initial_status,
            "grade": patient.clinical_data.grade,
            "prior_treatment": patient.clinical_data.prior_treatment,
            "idh_mutation": patient.clinical_data.idh_mutation,
            "mgmt_methylation": patient.clinical_data.mgmt_methylation,
            "updated_at": patient.clinical_data.updated_at.isoformat() if patient.clinical_data and patient.clinical_data.updated_at else None,
        } if patient.clinical_data else None,
    }


@router.get("/patients/{patient_id}/upload-status")
def get_upload_status(
    patient_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Lightweight check: which modalities have been uploaded for this patient."""
    patient = crud.get_patient_for_user(db, patient_id, current_user)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    has_mri = db.query(models.Image).filter(
        models.Image.patient_id == patient.id,
        models.Image.modality.in_(["MRI", "MRI_SERIES"]),
    ).first() is not None

    has_wsi = db.query(models.Image).filter(
        models.Image.patient_id == patient.id,
        models.Image.modality == "WSI_SERIES",
    ).first() is not None

    has_rna = db.query(models.RnaData).filter(
        models.RnaData.patient_id == patient.id
    ).first() is not None

    clinical = None
    has_clinical = False
    if patient.clinical_data:
        has_clinical = True
        clinical = {
            "ki67_index": patient.clinical_data.ki67_index,
            "grade": patient.clinical_data.grade,
            "idh_mutation": patient.clinical_data.idh_mutation,
            "mgmt_methylation": patient.clinical_data.mgmt_methylation,
        }

    return {
        "has_mri": has_mri,
        "has_wsi": has_wsi,
        "has_rna": has_rna,
        "has_clinical": has_clinical,
        "clinical": clinical,
    }


@router.patch("/patients/{patient_id}")
def update_patient_info(
    patient_id: str,
    patient_update: schemas.PatientUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    patient = crud.get_patient_for_user(db, patient_id, current_user)
    if not patient:
        raise HTTPException(status_code=404, detail="Khong tim thay benh nhan")

    if patient_update.age is not None:
        patient.age = patient_update.age
    if patient_update.gender is not None:
        patient.gender = patient_update.gender

    db.commit()
    db.refresh(patient)
    return {"message": "Cap nhat thanh cong", "patient": patient}


@router.delete("/images/{image_id}")
def delete_image_record(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    image = crud.get_image_for_user(db, image_id, current_user)
    if not image:
        raise HTTPException(status_code=404, detail="Khong tim thay hinh anh")

    storage_path = _parse_storage_path(image.file_path)
    if storage_path:
        bucket_name, object_name = storage_path
        try:
            minio_client.remove_object(bucket_name=bucket_name, object_name=object_name)
        except Exception as exc:
            print(f"[Warning] Could not delete object storage file {bucket_name}/{object_name}: {exc}")

    analysis = db.query(models.AnalysisResult).filter(models.AnalysisResult.image_id == image_id).first()
    if analysis:
        db.delete(analysis)

    diagnoses = db.query(models.Diagnosis).filter(models.Diagnosis.image_id == image_id).all()
    for diagnosis in diagnoses:
        db.delete(diagnosis)

    explanations = db.query(models.AIExplanation).filter(models.AIExplanation.image_id == image_id).all()
    for explanation in explanations:
        db.delete(explanation)

    validations = db.query(models.ExpertValidation).filter(models.ExpertValidation.image_id == image_id).all()
    for validation in validations:
        db.delete(validation)

    classification_reviews = db.query(models.ClassificationReview).filter(models.ClassificationReview.image_id == image_id).all()
    for review in classification_reviews:
        db.delete(review)

    tasks = db.query(models.InferenceTask).filter(
        models.InferenceTask.task_type == "mri_pipeline",
        models.InferenceTask.target_id == image_id,
    ).all()
    for task in tasks:
        db.delete(task)

    analysis_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "analysis_results", str(image_id))
    if os.path.isdir(analysis_dir):
        shutil.rmtree(analysis_dir, ignore_errors=True)

    db.delete(image)
    db.commit()

    return {"message": "Da xoa dong ket qua va anh MRI thanh cong"}

@router.get("/analysis/image/{image_id}/slice/{index}")
def get_series_slice(
    image_id: int,
    index: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Lấy một lát cắt cụ thể từ chuỗi ảnh (Series) để hiển thị trên Viewer."""
    from fastapi.responses import Response
    import io
    import cv2
    import numpy as np

    image = crud.get_image_for_user(db, image_id, current_user)
    if not image:
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh")
    
    if not image.is_series:
        # Nếu không phải series, trả về chính nó (index=0)
        bucket_name, object_name = image.file_path.lstrip("/").split("/", 1)
        response = minio_client.get_object(bucket_name, object_name)
    else:
        # Xử lý chuỗi ảnh
        bucket_name, folder_prefix = image.file_path.lstrip("/").split("/", 1)
        objects = list(minio_client.list_objects(bucket_name, prefix=folder_prefix, recursive=True))
        sorted_objs = sorted(objects, key=lambda x: _natural_sort_key(x.object_name))
        
        if index < 0 or index >= len(sorted_objs):
            raise HTTPException(status_code=404, detail=f"Index {index} vượt quá số lượng lát cắt ({len(sorted_objs)})")
        
        response = minio_client.get_object(bucket_name, sorted_objs[index].object_name)

    try:
        file_bytes = response.read()
    finally:
        response.close()
        response.release_conn()

    # Decode ảnh (PNG/JPG hoặc DICOM)
    # Tái sử dụng logic decode cơ bản
    def _decode(data: bytes):
        # Thử DICOM trước
        import pydicom
        try:
            dicom = pydicom.dcmread(io.BytesIO(data), force=True)
            if hasattr(dicom, "PixelData"):
                arr = dicom.pixel_array.astype(np.float32)
                arr -= arr.min()
                if arr.max() > 0: arr /= arr.max()
                arr = (arr * 255).astype(np.uint8)
                return arr
        except: pass
        # Thử ảnh thường
        arr = np.frombuffer(data, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
        return img

    img_arr = _decode(file_bytes)
    if img_arr is None:
        raise HTTPException(status_code=500, detail="Không thể giải mã lát cắt")

    # Encode sang PNG để browser hiển thị được
    success, encoded_img = cv2.imencode(".png", img_arr)
    if not success:
        raise HTTPException(status_code=500, detail="Lỗi khi nén ảnh")

    return Response(content=encoded_img.tobytes(), media_type="image/png")
