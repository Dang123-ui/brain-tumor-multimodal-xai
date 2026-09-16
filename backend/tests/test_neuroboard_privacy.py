import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from neuroboard.service import serialize_post


def _session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _clinical_post_fixture(db):
    author = models.User(
        username="case-owner",
        hashed_password="hash",
        role="doctor",
    )
    viewer = models.User(
        username="case-viewer",
        hashed_password="hash",
        role="researcher",
    )
    patient = models.Patient(
        name="Nguyen Van A",
        patient_external_id="UCSF-001",
        age=51,
        gender="M",
    )
    db.add_all([author, viewer, patient])
    db.flush()

    image = models.Image(patient_id=patient.id, modality="MRI", file_path="/medical-data/mri.png")
    db.add(image)
    db.flush()
    db.add(
        models.AnalysisResult(
            image_id=image.id,
            patient_id=patient.id,
            tumor_label="Glioma",
            classification_confidence=0.91,
            risk_score=1.42,
            risk_group="high",
        )
    )
    post = models.NeuroPost(
        author_id=author.id,
        post_type="clinical_case",
        content="Xin y kien ve ca MRI nay.",
        image_id=image.id,
        patient_id=patient.id,
        anonymous_case_code="case-abc123",
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return author, viewer, post


def test_clinical_post_author_receives_patient_identity():
    db = _session()
    author, _, post = _clinical_post_fixture(db)

    payload = serialize_post(db, post, viewer_user_id=author.id)

    assert payload["patient_id"] == post.patient_id
    assert payload["patient_name"] == "Nguyen Van A"
    assert payload["patient_external_id"] == "UCSF-001"
    assert payload["anonymous_case_code"] == "case-abc123"


def test_clinical_post_hides_patient_identity_from_other_users():
    db = _session()
    _, viewer, post = _clinical_post_fixture(db)

    payload = serialize_post(db, post, viewer_user_id=viewer.id)

    assert "patient_id" not in payload
    assert "patient_name" not in payload
    assert "patient_external_id" not in payload
    assert payload["anonymous_case_code"] == "case-abc123"
    assert payload["clinical_summary"] == {
        "image_id": post.image_id,
        "ai_label": "Glioma",
        "confidence": 0.91,
        "risk_score": 1.42,
        "risk_group": "high",
        "no_tumor_detected": False,
    }
