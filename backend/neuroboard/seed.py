from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

import models
from utils import hash_password


DEMO_PASSWORD = "123456"
DEMO_USERS = (
    ("admin", "researcher"),
    ("dr_lan_nguyen", "doctor"),
    ("dr_minh_tran", "doctor"),
    ("researcher_an", "researcher"),
    ("resident_khoa", "doctor"),
)

VIETFUTURE_POST = """Tất tần tật về VietFuture Awards 2026 gói gọn trong một tấm ảnh!
Lưu lại ngay để khỏi "lạc trôi" khi làm hồ sơ, rồi nghiên cứu dần nha

HƯỚNG DẪN ĐĂNG KÝ
Bước 1: Sinh viên nộp hồ sơ dự án cho Trường sơ loại và tạo hồ sơ cá nhân (CV/Profile) trên nền tảng InnoConnect: https://innoconnect.vn/
Bước 2: Nhà Trường sơ loại và điền Phiếu đăng ký tham dự Giải thưởng (theo mẫu BTC)
Bước 3: Hoàn thiện hồ sơ đăng ký dự thi tại website VietFuture: https://vietfuture.vinasa.org.vn
------------------------------------
Truy cập website hoặc liên hệ BTC để nhận bộ tài liệu hướng dẫn chi tiết
Hotline: 0937 551 871 (Ms. Phương Anh)
Website: https://vietfuture.world
Group Zalo Hỗ trợ Sinh viên: https://zalo.me/g/upinxb548"""

NORMAL_POSTS = (
    (
        "Tuần này nhóm sẽ rà soát lại checklist chia sẻ clinical case: ảnh MRI gốc, BBOX, mask, "
        "tumor contour và phần nhận xét cần được trình bày đủ để người xem có thể đối chiếu nhanh."
    ),
    (
        "Gợi ý thực hành: confidence cao thể hiện mức độ tự tin của mô hình, không phải kết luận "
        "lâm sàng cuối cùng. Khi đăng case, mọi người nên ghi rõ điểm cần xin ý kiến để phần bình luận "
        "tập trung hơn."
    ),
)

SAMPLE_COMMENTS = (
    "Case đã ẩn danh rõ, bộ ảnh đủ để đối chiếu nhanh vùng nghi ngờ.",
    "Nên kiểm tra thêm tương quan giữa BBOX và contour trước khi xác nhận nhãn cuối.",
    "Thông tin hữu ích, mình đã lưu lại để hướng dẫn sinh viên trong nhóm.",
)


def _demo_asset_path(filename: str) -> str | None:
    path = Path(__file__).resolve().parent / "assets" / filename
    return str(path) if path.exists() else None


def _ensure_demo_users(db: Session) -> dict[str, models.User]:
    users: dict[str, models.User] = {}
    for username, role in DEMO_USERS:
        user = db.query(models.User).filter(models.User.username == username).first()
        if user is None:
            user = models.User(
                username=username,
                hashed_password=hash_password(DEMO_PASSWORD),
                role=role,
                is_active=True,
            )
            db.add(user)
            db.flush()
        elif not user.is_active:
            user.is_active = True
        users[username] = user
    return users


def _current_demo_exists(db: Session) -> bool:
    return (
        db.query(models.NeuroPost.id)
        .filter(
            models.NeuroPost.deleted_at.is_(None),
            models.NeuroPost.content == VIETFUTURE_POST,
        )
        .first()
        is not None
    )


def _looks_like_prior_demo(post: models.NeuroPost) -> bool:
    content = post.content or ""
    return (
        "Chào mừng đến với NeuroBoard" in content
        or "ChÃ o má»«ng Ä‘áº¿n vá»›i NeuroBoard" in content
        or "confidence cao" in content
        or "VietFuture Awards 2026" in content
        or "Mời cộng đồng trao đổi thêm" in content
        or "Má»i cá»™ng Ä‘á»“ng" in content
        or (post.anonymous_case_code or "").startswith("CASE-DEMO-")
    )


def _soft_delete_prior_demo_posts(db: Session) -> None:
    posts = (
        db.query(models.NeuroPost)
        .filter(models.NeuroPost.deleted_at.is_(None))
        .all()
    )
    now = datetime.utcnow()
    for post in posts:
        if _looks_like_prior_demo(post):
            post.deleted_at = now


def _latest_analyzed_images(db: Session, limit: int = 2) -> list[tuple[models.AnalysisResult, models.Image]]:
    return (
        db.query(models.AnalysisResult, models.Image)
        .join(models.Image, models.Image.id == models.AnalysisResult.image_id)
        .order_by(models.AnalysisResult.created_at.desc(), models.AnalysisResult.id.desc())
        .limit(limit)
        .all()
    )


def _unique_case_code(db: Session, image_id: int) -> str:
    base_code = f"case-{image_id:04d}"
    existing = {
        value
        for (value,) in db.query(models.NeuroPost.anonymous_case_code)
        .filter(models.NeuroPost.anonymous_case_code.like(f"{base_code}%"))
        .all()
        if value
    }
    if base_code not in existing:
        return base_code
    suffix = 2
    while f"{base_code}-{suffix}" in existing:
        suffix += 1
    return f"{base_code}-{suffix}"


def seed_neuroboard_demo(db: Session) -> int:
    """Populate NeuroBoard with realistic, anonymized demo content."""
    users = _ensure_demo_users(db)
    if _current_demo_exists(db):
        db.commit()
        return 0

    _soft_delete_prior_demo_posts(db)

    base_time = datetime(2026, 9, 16, 9, 30)
    created_posts: list[models.NeuroPost] = []

    try:
        vietfuture_post = models.NeuroPost(
            author_id=users["researcher_an"].id,
            post_type="normal",
            content=VIETFUTURE_POST,
            created_at=base_time,
            updated_at=base_time,
        )
        db.add(vietfuture_post)
        db.flush()
        created_posts.append(vietfuture_post)

        vietfuture_asset = _demo_asset_path("vietfuture_awards_2026.jpg")
        if vietfuture_asset:
            db.add(
                models.NeuroPostAttachment(
                    post_id=vietfuture_post.id,
                    object_path=vietfuture_asset,
                    content_type="image/jpeg",
                    original_name="vietfuture_awards_2026.jpg",
                    sort_order=0,
                )
            )

        for index, (analysis, image) in enumerate(_latest_analyzed_images(db), start=1):
            label = "không phát hiện khối u" if analysis.no_tumor_detected else (
                analysis.tumor_label or "chưa có nhãn"
            )
            confidence = (
                f"{analysis.classification_confidence * 100:.2f}%"
                if analysis.classification_confidence is not None
                else "chưa có dữ liệu"
            )
            author = users["dr_lan_nguyen"] if index == 1 else users["dr_minh_tran"]
            created_at = base_time - timedelta(minutes=20 + (index - 1) * 10)
            post = models.NeuroPost(
                author_id=author.id,
                post_type="clinical_case",
                content=(
                    "Mời mọi người cho ý kiến chuyên môn về ca MRI đã ẩn danh này. "
                    f"AI label hiện tại: {label}; confidence: {confidence}. "
                    "Mình muốn đối chiếu thêm BBOX, mask và tumor contour trước khi ghi nhận nhãn cuối."
                ),
                image_id=image.id,
                patient_id=image.patient_id,
                anonymous_case_code=_unique_case_code(db, image.id),
                created_at=created_at,
                updated_at=created_at,
            )
            db.add(post)
            db.flush()
            created_posts.append(post)

        for index, content in enumerate(NORMAL_POSTS, start=1):
            created_at = base_time - timedelta(hours=2 + index)
            post = models.NeuroPost(
                author_id=users["resident_khoa"].id if index == 1 else users["admin"].id,
                post_type="normal",
                content=content,
                created_at=created_at,
                updated_at=created_at,
            )
            db.add(post)
            db.flush()
            created_posts.append(post)

        commenters = [users["dr_minh_tran"], users["resident_khoa"], users["dr_lan_nguyen"]]
        for post, comment_text, commenter in zip(created_posts[:3], SAMPLE_COMMENTS, commenters):
            db.add(
                models.NeuroPostComment(
                    post_id=post.id,
                    author_id=commenter.id,
                    content=comment_text,
                    created_at=post.created_at + timedelta(minutes=8),
                    updated_at=post.created_at + timedelta(minutes=8),
                )
            )
            db.add(
                models.NeuroPostReaction(
                    post_id=post.id,
                    user_id=commenter.id,
                    reaction_type="support",
                    created_at=post.created_at + timedelta(minutes=5),
                )
            )

        db.commit()
        return len(created_posts)
    except Exception:
        db.rollback()
        raise
