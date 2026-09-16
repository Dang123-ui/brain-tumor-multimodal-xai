import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base


def _database_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_seed_creates_social_posts_and_anonymized_clinical_cases_once():
    from neuroboard.seed import seed_neuroboard_demo

    db = _database_session()
    author = models.User(username="admin", hashed_password="hash", role="researcher")
    colleague = models.User(username="doctor_demo", hashed_password="hash", role="doctor")
    patient = models.Patient(
        name="Private Patient",
        patient_external_id="PRIVATE-001",
        age=45,
        gender="F",
    )
    db.add_all([author, colleague, patient])
    db.flush()

    for index, label in enumerate(("Glioma", "Meningioma", "Pituitary tumor"), start=1):
        image = models.Image(
            patient_id=patient.id,
            modality="MRI",
            file_path=f"/medical-data/demo-{index}.png",
        )
        db.add(image)
        db.flush()
        db.add(
            models.AnalysisResult(
                image_id=image.id,
                patient_id=patient.id,
                tumor_label=label,
                classification_confidence=0.9 + index / 100,
                risk_score=float(index),
                risk_group="high",
            )
        )
    db.commit()

    created = seed_neuroboard_demo(db)

    posts = db.query(models.NeuroPost).filter(models.NeuroPost.deleted_at.is_(None)).order_by(models.NeuroPost.created_at.desc()).all()
    clinical_posts = [post for post in posts if post.post_type == "clinical_case"]
    assert created == 5
    assert len(posts) == 5
    assert [post.post_type for post in posts].count("normal") == 3
    assert posts[0].content.startswith("Tất tần tật về VietFuture Awards 2026")
    assert posts[0].attachments[0].original_name == "vietfuture_awards_2026.jpg"
    assert len(clinical_posts) == 2
    assert {post.image_id for post in clinical_posts} == {2, 3}
    assert all(post.patient_id == patient.id for post in clinical_posts)
    assert all(post.anonymous_case_code.startswith("case-") for post in clinical_posts)
    assert db.query(models.User).filter(models.User.username == "dr_lan_nguyen").first() is not None
    assert len({post.author_id for post in posts}) > 1
    assert db.query(models.NeuroPostComment).count() >= 2
    assert db.query(models.NeuroPostReaction).count() >= 2

    assert seed_neuroboard_demo(db) == 0
    assert db.query(models.NeuroPost).filter(models.NeuroPost.deleted_at.is_(None)).count() == 5

    for post in posts:
        post.deleted_at = post.created_at
    db.commit()

    assert seed_neuroboard_demo(db) == 5
    assert db.query(models.NeuroPost).filter(models.NeuroPost.deleted_at.is_(None)).count() == 5
    db.close()


def test_seed_preserves_an_existing_active_feed():
    from neuroboard.seed import seed_neuroboard_demo

    db = _database_session()
    author = models.User(username="admin", hashed_password="hash", role="researcher")
    db.add(author)
    db.flush()
    db.add(
        models.NeuroPost(
            author_id=author.id,
            post_type="normal",
            content="Bai viet da ton tai.",
        )
    )
    db.commit()

    assert seed_neuroboard_demo(db) == 3
    active_posts = db.query(models.NeuroPost).filter(models.NeuroPost.deleted_at.is_(None)).all()
    assert len(active_posts) == 4
    assert any(post.content == "Bai viet da ton tai." for post in active_posts)
    db.close()
