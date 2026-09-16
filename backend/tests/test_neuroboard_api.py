import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base, get_db
import neuroboard.router as neuroboard_router
from neuroboard.router import get_current_user, router


@pytest.fixture()
def api_context():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    author = models.User(username="author", hashed_password="hash", role="doctor")
    viewer = models.User(username="viewer", hashed_password="hash", role="researcher")
    patient = models.Patient(
        name="Visible To Owner",
        patient_external_id="PRIVATE-001",
        age=44,
        gender="F",
    )
    db.add_all([author, viewer, patient])
    db.flush()
    image = models.Image(patient_id=patient.id, modality="MRI", file_path="/medical-data/mri.jpg")
    db.add(image)
    db.flush()
    db.add(
        models.AnalysisResult(
            image_id=image.id,
            patient_id=patient.id,
            tumor_label="Meningioma",
            classification_confidence=0.88,
            risk_score=0.72,
            risk_group="medium",
        )
    )
    db.commit()

    identity = {"sub": str(author.id), "role": "doctor"}
    app = FastAPI()
    app.include_router(router)

    def override_db():
        yield db

    def override_user():
        return identity

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user

    with TestClient(app) as client:
        yield {
            "client": client,
            "db": db,
            "identity": identity,
            "author": author,
            "viewer": viewer,
            "patient": patient,
            "image": image,
        }
    db.close()


def test_create_normal_post_and_read_it_from_feed(api_context):
    client = api_context["client"]

    response = client.post(
        "/neuroboard/posts",
        data={"post_type": "normal", "content": "Thong bao hoi chan sang thu Hai."},
    )

    assert response.status_code == 201
    created = response.json()
    assert created["post_type"] == "normal"
    assert created["content"] == "Thong bao hoi chan sang thu Hai."
    assert created["clinical_summary"] is None

    feed = client.get("/neuroboard/feed").json()
    assert feed["items"][0]["id"] == created["id"]
    assert feed["next_cursor"] is None


def test_clinical_post_requires_analyzed_mri(api_context):
    client = api_context["client"]

    missing = client.post(
        "/neuroboard/posts",
        data={"post_type": "clinical_case", "content": "Xin y kien."},
    )
    unknown = client.post(
        "/neuroboard/posts",
        data={"post_type": "clinical_case", "content": "Xin y kien.", "image_id": "9999"},
    )

    assert missing.status_code == 422
    assert unknown.status_code == 404


def test_clinical_feed_hides_identity_from_non_author(api_context):
    client = api_context["client"]
    image = api_context["image"]
    viewer = api_context["viewer"]
    identity = api_context["identity"]

    created = client.post(
        "/neuroboard/posts",
        data={
            "post_type": "clinical_case",
            "content": "Can them second opinion.",
            "image_id": str(image.id),
        },
    ).json()
    assert created["patient_external_id"] == "PRIVATE-001"

    identity["sub"] = str(viewer.id)
    visible_to_viewer = client.get("/neuroboard/feed").json()["items"][0]

    assert "patient_id" not in visible_to_viewer
    assert "patient_name" not in visible_to_viewer
    assert "patient_external_id" not in visible_to_viewer
    assert visible_to_viewer["anonymous_case_code"] == created["anonymous_case_code"]
    assert visible_to_viewer["clinical_summary"]["ai_label"] == "Meningioma"


def test_react_comment_reply_and_save_post(api_context):
    client = api_context["client"]
    created = client.post(
        "/neuroboard/posts",
        data={"post_type": "normal", "content": "Bai viet thao luan."},
    ).json()
    post_id = created["id"]

    reacted = client.put(
        f"/neuroboard/posts/{post_id}/reaction",
        json={"reaction_type": "support"},
    )
    assert reacted.status_code == 200
    assert reacted.json()["reaction_count"] == 1
    assert reacted.json()["viewer_reaction"] == "support"

    comment = client.post(
        f"/neuroboard/posts/{post_id}/comments",
        json={"content": "Toi dong y voi nhan xet nay."},
    )
    assert comment.status_code == 201
    comment_id = comment.json()["id"]

    reply = client.post(
        f"/neuroboard/posts/{post_id}/comments",
        json={"content": "Cam on ban.", "parent_id": comment_id},
    )
    assert reply.status_code == 201

    comments = client.get(f"/neuroboard/posts/{post_id}/comments").json()["items"]
    assert len(comments) == 1
    assert comments[0]["content"] == "Toi dong y voi nhan xet nay."
    assert comments[0]["replies"][0]["content"] == "Cam on ban."

    saved = client.put(f"/neuroboard/posts/{post_id}/save")
    assert saved.status_code == 200
    assert saved.json()["viewer_saved"] is True


def test_only_author_can_delete_post(api_context):
    client = api_context["client"]
    author = api_context["author"]
    viewer = api_context["viewer"]
    identity = api_context["identity"]
    created = client.post(
        "/neuroboard/posts",
        data={"post_type": "normal", "content": "Bai viet cua tac gia."},
    ).json()

    identity["sub"] = str(viewer.id)
    forbidden = client.delete(f"/neuroboard/posts/{created['id']}")
    assert forbidden.status_code == 403

    identity["sub"] = str(author.id)
    deleted = client.delete(f"/neuroboard/posts/{created['id']}")
    assert deleted.status_code == 204
    assert client.get("/neuroboard/feed").json()["items"] == []


def test_uploaded_media_returns_url_without_exposing_storage_path(api_context, monkeypatch):
    client = api_context["client"]

    async def fake_store(post_id, files):
        assert len(files) == 1
        return [
            {
                "object_path": f"/medical-data/neuroboard/{post_id}/scan.png",
                "content_type": "image/png",
                "original_name": "scan.png",
                "sort_order": 0,
            }
        ]

    monkeypatch.setattr(neuroboard_router, "store_post_images", fake_store)
    monkeypatch.setattr(
        neuroboard_router,
        "display_media_url",
        lambda path: "https://storage.example/scan.png" if path else None,
    )

    response = client.post(
        "/neuroboard/posts",
        data={"post_type": "normal", "content": "Anh thao luan."},
        files={"files": ("scan.png", b"image-bytes", "image/png")},
    )

    assert response.status_code == 201
    attachment = response.json()["attachments"][0]
    assert attachment["url"] == "https://storage.example/scan.png"
    assert "object_path" not in attachment


def test_feed_scopes_filter_my_posts_and_saved_posts(api_context):
    client = api_context["client"]
    author = api_context["author"]
    viewer = api_context["viewer"]
    identity = api_context["identity"]

    author_post = client.post(
        "/neuroboard/posts",
        data={"post_type": "normal", "content": "Bai cua author."},
    ).json()

    identity["sub"] = str(viewer.id)
    viewer_post = client.post(
        "/neuroboard/posts",
        data={"post_type": "normal", "content": "Bai cua viewer."},
    ).json()

    identity["sub"] = str(author.id)
    client.put(f"/neuroboard/posts/{viewer_post['id']}/save")

    mine = client.get("/neuroboard/feed", params={"scope": "mine"}).json()["items"]
    saved = client.get("/neuroboard/feed", params={"scope": "saved"}).json()["items"]

    assert [item["id"] for item in mine] == [author_post["id"]]
    assert [item["id"] for item in saved] == [viewer_post["id"]]


def test_clinical_case_detail_supports_roi_comment_and_ai_reply(api_context):
    client = api_context["client"]
    image = api_context["image"]

    created = client.post(
        "/neuroboard/posts",
        data={
            "post_type": "clinical_case",
            "content": "Can xem ROI tren XAI.",
            "image_id": str(image.id),
        },
    ).json()

    empty_detail = client.get(f"/neuroboard/posts/{created['id']}/case-detail")
    assert empty_detail.status_code == 200
    assert empty_detail.json()["post"]["id"] == created["id"]
    assert empty_detail.json()["roi_comments"] == []

    response = client.post(
        f"/neuroboard/posts/{created['id']}/roi-comments",
        json={
            "visual_label": "XAI Detection (ODAM)",
            "x": 0.1,
            "y": 0.2,
            "width": 0.3,
            "height": 0.25,
            "content": "@AI vung nay co khop voi bbox khong?",
        },
    )

    assert response.status_code == 201
    items = response.json()["items"]
    assert len(items) == 2
    assert items[0]["is_ai"] is False
    assert items[0]["roi"] == {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.25}
    assert items[1]["is_ai"] is True
    assert items[1]["reply_to_id"] == items[0]["id"]
    assert "Meningioma" in items[1]["content"]

    detail = client.get(f"/neuroboard/posts/{created['id']}/case-detail").json()
    assert len(detail["roi_comments"]) == 2


def test_roi_comment_recall_keeps_thread_but_hides_content_and_roi(api_context):
    client = api_context["client"]
    image = api_context["image"]

    created = client.post(
        "/neuroboard/posts",
        data={
            "post_type": "clinical_case",
            "content": "Can hoi chan ROI.",
            "image_id": str(image.id),
        },
    ).json()
    root = client.post(
        f"/neuroboard/posts/{created['id']}/roi-comments",
        json={
            "visual_label": "MRI",
            "x": 0.12,
            "y": 0.22,
            "width": 0.2,
            "height": 0.2,
            "content": "Bac A nhan xet ROI nay.",
        },
    ).json()["items"][0]
    reply = client.post(
        f"/neuroboard/posts/{created['id']}/roi-comments",
        json={
            "reply_to_id": root["id"],
            "visual_label": "MRI",
            "x": 0.12,
            "y": 0.22,
            "width": 0.2,
            "height": 0.2,
            "content": "Bac B reply lai bac A.",
        },
    ).json()["items"][0]

    recalled = client.delete(f"/neuroboard/posts/{created['id']}/roi-comments/{root['id']}")

    assert recalled.status_code == 200
    assert recalled.json()["is_deleted"] is True
    assert recalled.json()["content"] == "Đã thu hồi"
    assert recalled.json()["roi"] is None

    detail = client.get(f"/neuroboard/posts/{created['id']}/case-detail").json()
    comments = detail["roi_comments"]
    assert [item["id"] for item in comments] == [root["id"], reply["id"]]
    assert comments[0]["is_deleted"] is True
    assert comments[0]["content"] == "Đã thu hồi"
    assert comments[0]["roi"] is None
    assert comments[1]["reply_to_id"] == root["id"]
    assert comments[1]["content"] == "Bac B reply lai bac A."


def test_roi_ai_reply_can_be_recalled_by_user_who_triggered_it(api_context):
    client = api_context["client"]
    image = api_context["image"]
    viewer = api_context["viewer"]
    identity = api_context["identity"]

    created = client.post(
        "/neuroboard/posts",
        data={
            "post_type": "clinical_case",
            "content": "Can hoi AI ve ROI.",
            "image_id": str(image.id),
        },
    ).json()

    identity["sub"] = str(viewer.id)
    items = client.post(
        f"/neuroboard/posts/{created['id']}/roi-comments",
        json={
            "visual_label": "XAI Detection (ODAM)",
            "x": 0.1,
            "y": 0.2,
            "width": 0.3,
            "height": 0.25,
            "content": "@AI vung nay co khop voi bbox khong?",
        },
    ).json()["items"]
    user_comment, ai_reply = items

    recalled = client.delete(
        f"/neuroboard/posts/{created['id']}/roi-comments/{ai_reply['id']}"
    )

    assert recalled.status_code == 200
    assert recalled.json()["is_deleted"] is True
    assert recalled.json()["content"] == "Đã thu hồi"
    assert recalled.json()["roi"] is None

    detail = client.get(f"/neuroboard/posts/{created['id']}/case-detail").json()
    comments = detail["roi_comments"]
    assert comments[0]["id"] == user_comment["id"]
    assert comments[0]["is_deleted"] is False
    assert comments[1]["id"] == ai_reply["id"]
    assert comments[1]["reply_to_id"] == user_comment["id"]
    assert comments[1]["is_deleted"] is True


def test_roi_comment_rejects_normal_post(api_context):
    client = api_context["client"]
    post = client.post(
        "/neuroboard/posts",
        data={"post_type": "normal", "content": "Bai thuong."},
    ).json()

    response = client.post(
        f"/neuroboard/posts/{post['id']}/roi-comments",
        json={
            "visual_label": "MRI",
            "x": 0.1,
            "y": 0.1,
            "width": 0.2,
            "height": 0.2,
            "content": "ROI tren bai thuong.",
        },
    )

    assert response.status_code == 422
