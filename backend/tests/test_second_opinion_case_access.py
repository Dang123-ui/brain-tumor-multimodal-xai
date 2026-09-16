import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI
from fastapi.testclient import TestClient

import crud
import models
from database import Base
from database import get_db
import neuroboard.router as neuroboard_router
from neuroboard.router import router as neuroboard_api_router
from routers.analysis import router as analysis_router
from utils import get_current_user as analysis_get_current_user


def _session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _fixture(db):
    owner = models.User(username="admin", hashed_password="hash", role="doctor")
    reviewer = models.User(username="doctor_lan", hashed_password="hash", role="doctor")
    outsider = models.User(username="outsider", hashed_password="hash", role="doctor")
    db.add_all([owner, reviewer, outsider])
    db.flush()
    patient = models.Patient(
        owner_user_id=owner.id,
        name="Shared Patient",
        patient_external_id="SHARED-001",
        age=50,
        gender="F",
    )
    db.add(patient)
    db.flush()
    image = models.Image(patient_id=patient.id, modality="MRI", file_path="/medical-data/shared.png")
    db.add(image)
    db.flush()
    db.add(
        models.AnalysisResult(
            image_id=image.id,
            patient_id=patient.id,
            tumor_label="Glioma",
            classification_confidence=0.87,
            risk_score=0.71,
            risk_group="High",
        )
    )
    conversation = models.NeuroConversation(user_1_id=owner.id, user_2_id=reviewer.id)
    db.add(conversation)
    db.flush()
    message = models.NeuroMessage(
        conversation_id=conversation.id,
        sender_id=owner.id,
        message_type="case",
        content="Please review this case.",
        case_image_id=image.id,
    )
    db.add(message)
    db.flush()
    db.add(
        models.NeuroSecondOpinionRequest(
            case_image_id=image.id,
            requester_doctor_id=owner.id,
            reviewer_doctor_id=reviewer.id,
            conversation_id=conversation.id,
            message_id=message.id,
            status="Pending",
        )
    )
    db.commit()
    return owner, reviewer, outsider, image


def _client(db, identity):
    app = FastAPI()
    app.include_router(neuroboard_api_router)
    app.include_router(analysis_router)

    def override_db():
        yield db

    def override_user():
        return identity

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[neuroboard_router.get_current_user] = override_user
    app.dependency_overrides[analysis_get_current_user] = override_user
    return TestClient(app)


def test_second_opinion_reviewer_can_access_shared_image():
    db = _session()
    _, reviewer, _, image = _fixture(db)

    shared_image = crud.get_image_for_user_or_second_opinion(db, image.id, {"sub": str(reviewer.id)})

    assert shared_image is not None
    assert shared_image.id == image.id
    db.close()


def test_unrelated_user_cannot_access_second_opinion_image():
    db = _session()
    _, _, outsider, image = _fixture(db)

    shared_image = crud.get_image_for_user_or_second_opinion(db, image.id, {"sub": str(outsider.id)})

    assert shared_image is None
    db.close()


def test_second_opinion_reviewer_can_share_case_and_complete_review():
    db = _session()
    _, reviewer, _, image = _fixture(db)
    identity = {"sub": str(reviewer.id), "role": "doctor"}

    with _client(db, identity) as client:
        created = client.post(
            "/neuroboard/posts",
            data={
                "post_type": "clinical_case",
                "content": "Second opinion case shared for board discussion.",
                "image_id": str(image.id),
            },
        )
        assert created.status_code == 201
        assert created.json()["clinical_summary"]["ai_label"] == "Glioma"

        review = client.post(
            f"/records/analysis/image/{image.id}/classification-review",
            json={
                "expert_tumor_label": "Glioma",
                "expert_comment": "Reviewed by doctor_lan.",
            },
        )
        assert review.status_code == 200
        assert review.json()["review_status"] == "confirmed"

    request = (
        db.query(models.NeuroSecondOpinionRequest)
        .filter(models.NeuroSecondOpinionRequest.case_image_id == image.id)
        .one()
    )
    assert request.status == "Completed"
    assert request.completed_at is not None
    assert request.opinion == "Reviewed by doctor_lan."
    db.close()
