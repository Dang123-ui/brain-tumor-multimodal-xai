from sqlalchemy.orm import Session
import models


def current_user_id(current_user: dict | None) -> int | None:
    if not current_user:
        return None
    raw = current_user.get("user_id") or current_user.get("sub") or current_user.get("id")
    try:
        return int(raw)
    except Exception:
        return None


def patient_query_for_user(db: Session, current_user: dict):
    user_id = current_user_id(current_user)
    return db.query(models.Patient).filter(models.Patient.owner_user_id == user_id)


def get_patient_by_id_or_external(db: Session, identifier: str):
    """
    Tìm kiếm bệnh nhân dựa trên ID (số nguyên) hoặc Patient External ID (chuỗi).
    Hỗ trợ linh hoạt cho Frontend khi người dùng nhập Mã BN.
    """
    # 1. Thử tìm theo External ID (Ưu tiên vì người dùng thường nhập chuỗi này)
    patient = db.query(models.Patient).filter(models.Patient.patient_external_id == identifier).first()
    if patient:
        return patient

    # 2. Thử tìm theo ID nội bộ (nếu identifier là số)
    if identifier.isdigit():
        patient = db.query(models.Patient).filter(models.Patient.id == int(identifier)).first()
        if patient:
            return patient

    return None


def get_patient_for_user(db: Session, identifier: str, current_user: dict):
    patient = get_patient_by_id_or_external(db, identifier)
    user_id = current_user_id(current_user)
    if not patient or patient.owner_user_id != user_id:
        return None
    return patient


def get_image_for_user(db: Session, image_id: int, current_user: dict):
    user_id = current_user_id(current_user)
    return (
        db.query(models.Image)
        .join(models.Patient, models.Image.patient_id == models.Patient.id)
        .filter(models.Image.id == image_id, models.Patient.owner_user_id == user_id)
        .first()
    )


def user_has_second_opinion_image_access(db: Session, image_id: int, current_user: dict) -> bool:
    user_id = current_user_id(current_user)
    if user_id is None:
        return False
    return (
        db.query(models.NeuroSecondOpinionRequest)
        .filter(
            models.NeuroSecondOpinionRequest.case_image_id == image_id,
            (
                (models.NeuroSecondOpinionRequest.requester_doctor_id == user_id)
                | (models.NeuroSecondOpinionRequest.reviewer_doctor_id == user_id)
            ),
        )
        .first()
        is not None
    )


def get_image_for_user_or_second_opinion(db: Session, image_id: int, current_user: dict):
    image = get_image_for_user(db, image_id, current_user)
    if image:
        return image
    if not user_has_second_opinion_image_access(db, image_id, current_user):
        return None
    return db.query(models.Image).filter(models.Image.id == image_id).first()
