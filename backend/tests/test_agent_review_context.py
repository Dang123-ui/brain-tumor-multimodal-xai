import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from agent.tools.patient_tools import serialize_analysis_with_visuals
from database import Base


def _session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _analysis_fixture(db, *, label="Glioma", confidence=0.89):
    patient = models.Patient(
        name="Review Context Patient",
        patient_external_id="REV-001",
        age=52,
        gender="F",
    )
    db.add(patient)
    db.flush()
    image = models.Image(patient_id=patient.id, modality="MRI", file_path="/medical-data/review.png")
    db.add(image)
    db.flush()
    analysis = models.AnalysisResult(
        image_id=image.id,
        patient_id=patient.id,
        tumor_label=label,
        classification_confidence=confidence,
        risk_score=0.4,
        risk_group="medium",
    )
    db.add(analysis)
    db.commit()
    return analysis


def test_agent_analysis_context_flags_low_confidence_without_expert_label():
    db = _session()
    analysis = _analysis_fixture(db, label="Glioma", confidence=0.89)

    payload = serialize_analysis_with_visuals(db, analysis)

    assert payload["ai_tumor_label"] == "Glioma"
    assert payload["final_tumor_label"] == "Glioma"
    assert payload["expert_tumor_label"] is None
    assert payload["review_required"] is True
    assert payload["review_status"] == "needs_review"
    db.close()


def test_agent_analysis_context_uses_expert_label_as_final_label_after_review():
    db = _session()
    analysis = _analysis_fixture(db, label="Glioma", confidence=0.89)
    db.add(
        models.ClassificationReview(
            image_id=analysis.image_id,
            patient_id=analysis.patient_id,
            user_id=None,
            ai_tumor_label="Glioma",
            ai_confidence=0.89,
            expert_tumor_label="Meningioma",
            expert_comment="Expert corrected the label.",
            review_action="corrected",
        )
    )
    db.commit()

    payload = serialize_analysis_with_visuals(db, analysis)

    assert payload["ai_tumor_label"] == "Glioma"
    assert payload["expert_tumor_label"] == "Meningioma"
    assert payload["final_tumor_label"] == "Meningioma"
    assert payload["expert_comment"] == "Expert corrected the label."
    assert payload["review_required"] is False
    assert payload["review_status"] == "corrected"
    db.close()
