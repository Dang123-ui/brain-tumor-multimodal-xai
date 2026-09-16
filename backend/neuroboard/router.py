from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

import models
import crud
from database import get_db
from neuroboard.media import display_media_url, store_message_image, store_post_images
from neuroboard.schemas import CommentCreate, ReactionCreate, RoiCommentCreate
from neuroboard.service import serialize_post


router = APIRouter(prefix="/neuroboard", tags=["NeuroBoard"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict[str, Any]:
    from utils import decode_token

    return decode_token(token)


def _user_id(current_user: dict[str, Any]) -> int:
    value = current_user.get("user_id") or current_user.get("sub") or current_user.get("id")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Không xác định được người dùng") from exc


def _post_or_404(db: Session, post_id: int) -> models.NeuroPost:
    post = (
        db.query(models.NeuroPost)
        .filter(models.NeuroPost.id == post_id, models.NeuroPost.deleted_at.is_(None))
        .first()
    )
    if post is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài đăng")
    return post


def _latest_mri_task_result(db: Session, image_id: int) -> dict[str, Any]:
    task = (
        db.query(models.InferenceTask)
        .filter(
            models.InferenceTask.target_id == image_id,
            models.InferenceTask.task_type == "mri_pipeline",
        )
        .order_by(models.InferenceTask.created_at.desc(), models.InferenceTask.id.desc())
        .first()
    )
    return task.result or {} if task else {}


def _local_artifact_path(image_id: int, filename: str) -> str | None:
    backend_dir = Path(__file__).resolve().parents[1]
    candidates = (
        backend_dir / "analysis_results" / str(image_id) / filename,
        backend_dir / "multimodal_results" / str(image_id) / filename,
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _clinical_media_payload(
    db: Session,
    image: models.Image | None,
    analysis: models.AnalysisResult | None,
) -> dict[str, Any]:
    if image is None:
        return {"visuals": []}

    result = _latest_mri_task_result(db, image.id)
    specs = (
        ("MRI", result.get("original_image_path") or image.file_path),
        ("Detection (BBOX)", result.get("bbox_image_path") or _local_artifact_path(image.id, "step1_bbox.png")),
        (
            "Segmentation (Mask)",
            result.get("mask_overlay_path")
            or _local_artifact_path(image.id, "step5_mask_overlay.png")
            or (analysis.mask_path if analysis else None),
        ),
        (
            "Tumor contour",
            result.get("contour_overlay_path") or _local_artifact_path(image.id, "step6_contour_overlay.png"),
        ),
        (
            "XAI Detection (ODAM)",
            result.get("detection_xai_path")
            or result.get("odam_path")
            or (analysis.odam_path if analysis else None)
            or _local_artifact_path(image.id, "step7_detection_odam.png"),
        ),
        (
            "XAI Segmentation",
            result.get("segmentation_xai_path")
            or result.get("seg_eigen_cam_path")
            or (analysis.seg_eigen_cam_path if analysis else None)
            or _local_artifact_path(image.id, "step8_seg_eigen_cam.png"),
        ),
        (
            "XAI Classification",
            result.get("classification_xai_path")
            or result.get("finer_cam_path")
            or (analysis.finer_cam_path if analysis else None)
            or _local_artifact_path(image.id, "step9_classification_finer_cam.png"),
        ),
    )
    visuals = []
    seen_urls: set[str] = set()
    for label, path in specs:
        url = display_media_url(path)
        if url and url not in seen_urls:
            visuals.append({"label": label, "url": url})
            seen_urls.add(url)

    return {
        "visuals": visuals,
        "mri_url": visuals[0]["url"] if visuals else None,
    }


def _post_payload(db: Session, post: models.NeuroPost, viewer_user_id: int) -> dict[str, Any]:
    payload = serialize_post(db, post, viewer_user_id)
    for attachment in payload["attachments"]:
        object_path = attachment.pop("object_path", None)
        attachment["url"] = display_media_url(object_path)

    if post.post_type == "clinical_case" and post.image_id is not None:
        image = db.query(models.Image).filter(models.Image.id == post.image_id).first()
        analysis = (
            db.query(models.AnalysisResult)
            .filter(models.AnalysisResult.image_id == post.image_id)
            .first()
        )
        payload["clinical_media"] = _clinical_media_payload(db, image, analysis)
        if payload.get("clinical_summary"):
            result = _latest_mri_task_result(db, post.image_id)
            payload["clinical_summary"]["class_probabilities"] = result.get("class_probabilities")
            payload["clinical_summary"]["bbox_confidence"] = result.get("bbox_confidence")
    else:
        payload["clinical_media"] = None
    return payload


@router.get("/me")
def get_me(
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    user_id = _user_id(current_user)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
    }


@router.get("/feed")
def get_feed(
    post_type: Optional[str] = None,
    scope: str = "all",
    cursor: Optional[int] = None,
    limit: int = 15,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    viewer_user_id = _user_id(current_user)
    if post_type not in {None, "normal", "clinical_case"}:
        raise HTTPException(status_code=422, detail="Loại bài đăng không hợp lệ")
    if scope not in {"all", "mine", "saved"}:
        raise HTTPException(status_code=422, detail="Phạm vi bảng tin không hợp lệ")
    limit = max(1, min(limit, 50))
    query = db.query(models.NeuroPost).filter(models.NeuroPost.deleted_at.is_(None))
    if scope == "mine":
        query = query.filter(models.NeuroPost.author_id == viewer_user_id)
    elif scope == "saved":
        query = query.join(
            models.NeuroPostSave,
            models.NeuroPostSave.post_id == models.NeuroPost.id,
        ).filter(models.NeuroPostSave.user_id == viewer_user_id)
    if post_type:
        query = query.filter(models.NeuroPost.post_type == post_type)
    if cursor:
        query = query.filter(models.NeuroPost.id < cursor)
    posts = query.order_by(models.NeuroPost.created_at.desc(), models.NeuroPost.id.desc()).limit(limit + 1).all()
    has_more = len(posts) > limit
    items = posts[:limit]
    return {
        "items": [_post_payload(db, post, viewer_user_id) for post in items],
        "next_cursor": items[-1].id if has_more and items else None,
    }


@router.post("/posts", status_code=status.HTTP_201_CREATED)
async def create_post(
    post_type: str = Form(...),
    content: str = Form(""),
    image_id: Optional[int] = Form(None),
    files: Optional[list[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    author_id = _user_id(current_user)
    normalized_content = content.strip()
    uploads = files or []
    if post_type not in {"normal", "clinical_case"}:
        raise HTTPException(status_code=422, detail="Loại bài đăng không hợp lệ")
    if post_type == "normal" and not normalized_content and not uploads:
        raise HTTPException(status_code=422, detail="Bài đăng cần nội dung hoặc hình ảnh")

    patient_id: int | None = None
    anonymous_case_code: str | None = None
    if post_type == "clinical_case":
        if image_id is None:
            raise HTTPException(status_code=422, detail="Clinical case cần chọn một ảnh MRI")
        image = crud.get_image_for_user_or_second_opinion(db, image_id, current_user)
        analysis = (
            db.query(models.AnalysisResult)
            .filter(models.AnalysisResult.image_id == image_id)
            .first()
        )
        if image is None or analysis is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy MRI đã phân tích")
        patient_id = image.patient_id
        anonymous_case_code = f"case-{uuid.uuid4().hex[:8]}"

    post = models.NeuroPost(
        author_id=author_id,
        post_type=post_type,
        content=normalized_content or None,
        image_id=image_id if post_type == "clinical_case" else None,
        patient_id=patient_id,
        anonymous_case_code=anonymous_case_code,
    )
    db.add(post)
    db.flush()
    try:
        for stored in await store_post_images(post.id, uploads) if uploads else []:
            db.add(models.NeuroPostAttachment(post_id=post.id, **stored))
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Không thể tạo bài đăng: {exc}") from exc
    db.refresh(post)
    return _post_payload(db, post, author_id)


@router.get("/posts/{post_id}")
def get_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    return _post_payload(db, _post_or_404(db, post_id), _user_id(current_user))


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    post = _post_or_404(db, post_id)
    if post.author_id != _user_id(current_user):
        raise HTTPException(status_code=403, detail="Chỉ tác giả được xóa bài đăng")
    post.deleted_at = datetime.utcnow()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/posts/{post_id}/reaction")
def set_reaction(
    post_id: int,
    request: ReactionCreate,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    post = _post_or_404(db, post_id)
    user_id = _user_id(current_user)
    reaction = (
        db.query(models.NeuroPostReaction)
        .filter(
            models.NeuroPostReaction.post_id == post_id,
            models.NeuroPostReaction.user_id == user_id,
        )
        .first()
    )
    if reaction:
        reaction.reaction_type = request.reaction_type
    else:
        db.add(
            models.NeuroPostReaction(
                post_id=post_id,
                user_id=user_id,
                reaction_type=request.reaction_type,
            )
        )
    db.commit()
    return _post_payload(db, post, user_id)


@router.delete("/posts/{post_id}/reaction")
def remove_reaction(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    post = _post_or_404(db, post_id)
    user_id = _user_id(current_user)
    db.query(models.NeuroPostReaction).filter(
        models.NeuroPostReaction.post_id == post_id,
        models.NeuroPostReaction.user_id == user_id,
    ).delete(synchronize_session=False)
    db.commit()
    return _post_payload(db, post, user_id)


def _serialize_comment(comment: models.NeuroPostComment) -> dict[str, Any]:
    return {
        "id": comment.id,
        "post_id": comment.post_id,
        "parent_id": comment.parent_id,
        "content": comment.content,
        "author": {
            "id": comment.author.id,
            "username": comment.author.username,
        },
        "created_at": comment.created_at,
    }


def _serialize_roi_comment(comment: models.NeuroRoiComment) -> dict[str, Any]:
    is_deleted = comment.deleted_at is not None
    return {
        "id": comment.id,
        "post_id": comment.post_id,
        "reply_to_id": comment.reply_to_id,
        "visual_label": comment.visual_label,
        "roi": None
        if is_deleted
        else {
            "x": comment.x,
            "y": comment.y,
            "width": comment.width,
            "height": comment.height,
        },
        "content": "Đã thu hồi" if is_deleted else comment.content,
        "is_ai": bool(comment.is_ai),
        "is_deleted": is_deleted,
        "author": {
            "id": comment.author.id if comment.author else None,
            "username": comment.author.username if comment.author else "NeuroBoard AI",
        },
        "created_at": comment.created_at,
        "deleted_at": comment.deleted_at,
    }


def _can_recall_roi_comment(
    db: Session,
    comment: models.NeuroRoiComment,
    post: models.NeuroPost,
    user_id: int,
    role: str | None,
) -> bool:
    if role == "admin" or post.author_id == user_id or comment.author_id == user_id:
        return True
    if not comment.is_ai or comment.reply_to_id is None:
        return False
    parent = (
        db.query(models.NeuroRoiComment)
        .filter(
            models.NeuroRoiComment.id == comment.reply_to_id,
            models.NeuroRoiComment.post_id == post.id,
        )
        .first()
    )
    return parent is not None and parent.author_id == user_id


def _require_clinical_case(post: models.NeuroPost) -> None:
    if post.post_type != "clinical_case" or post.image_id is None:
        raise HTTPException(status_code=422, detail="Chuc nang nay chi dung cho Clinical Case")


def _ai_roi_reply(db: Session, post: models.NeuroPost, request: RoiCommentCreate) -> str:
    analysis = (
        db.query(models.AnalysisResult)
        .filter(models.AnalysisResult.image_id == post.image_id)
        .first()
    )
    label = "khong co nhan"
    confidence = "khong co confidence"
    risk = "khong co risk score"
    if analysis:
        label = "khong phat hien u" if analysis.no_tumor_detected else (analysis.tumor_label or label)
        if isinstance(analysis.classification_confidence, (float, int)):
            confidence = f"{analysis.classification_confidence * 100:.2f}%"
        if isinstance(analysis.risk_score, (float, int)):
            risk = f"{analysis.risk_score:.3f}"
            if analysis.risk_group:
                risk = f"{risk} ({analysis.risk_group})"
    x1 = request.x * 100
    y1 = request.y * 100
    x2 = (request.x + request.width) * 100
    y2 = (request.y + request.height) * 100
    intent = request.content.lower()
    base = (
        f"Case hien tai: AI label {label}, confidence {confidence}, risk {risk}. "
        f"ROI dang chon tren {request.visual_label}: "
        f"x={x1:.1f}-{x2:.1f}%, y={y1:.1f}-{y2:.1f}% cua anh. "
    )
    if "timeline" in intent or "dien tien" in intent or "diễn tiến" in intent:
        return base + "Timeline can doi chieu cac lan MRI truoc/sau cua cung benh nhan; tren trang case nay AI chi tom tat theo image dang duoc chia se."
    if "mask" in intent or "heatmap" in intent or "xai" in intent:
        return base + "Khi so sanh mask voi heatmap, hay kiem tra vung nong XAI co nam trong hoac sat vung mask/contour hay khong. Neu lech ro, nen uu tien review thu cong."
    if "confidence" in intent or "do tin cay" in intent or "độ tin cậy" in intent:
        return base + "Confidence chi phan anh muc do tu tin cua mo hinh voi nhan AI, khong phai ket luan lam sang cuoi cung."
    if "tom tat" in intent or "tóm tắt" in intent or "summary" in intent:
        return base + "Tom tat: day la Clinical Case da an danh, can xem dong thoi MRI goc, BBox, mask/contour va XAI truoc khi dua ra second opinion."
    return base + "Nen doi chieu ROI nay voi MRI goc, BBox, mask/contour va XAI truoc khi ket luan."


@router.get("/posts/{post_id}/case-detail")
def get_case_detail(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    viewer_user_id = _user_id(current_user)
    post = _post_or_404(db, post_id)
    _require_clinical_case(post)
    return {
        "post": _post_payload(db, post, viewer_user_id),
        "roi_comments": [
            _serialize_roi_comment(comment)
            for comment in (
                db.query(models.NeuroRoiComment)
                .filter(models.NeuroRoiComment.post_id == post_id)
                .order_by(models.NeuroRoiComment.created_at.asc(), models.NeuroRoiComment.id.asc())
                .all()
            )
        ],
    }


@router.get("/posts/{post_id}/roi-comments")
def get_roi_comments(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    _user_id(current_user)
    post = _post_or_404(db, post_id)
    _require_clinical_case(post)
    comments = (
        db.query(models.NeuroRoiComment)
        .filter(models.NeuroRoiComment.post_id == post_id)
        .order_by(models.NeuroRoiComment.created_at.asc(), models.NeuroRoiComment.id.asc())
        .all()
    )
    return {"items": [_serialize_roi_comment(comment) for comment in comments]}


@router.post("/posts/{post_id}/roi-comments", status_code=status.HTTP_201_CREATED)
def create_roi_comment(
    post_id: int,
    request: RoiCommentCreate,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    post = _post_or_404(db, post_id)
    _require_clinical_case(post)
    if request.reply_to_id is not None:
        parent = (
            db.query(models.NeuroRoiComment)
            .filter(
                models.NeuroRoiComment.id == request.reply_to_id,
                models.NeuroRoiComment.post_id == post_id,
                models.NeuroRoiComment.deleted_at.is_(None),
            )
            .first()
        )
        if parent is None:
            raise HTTPException(status_code=422, detail="ROI comment cha khong hop le")
    user_comment = models.NeuroRoiComment(
        post_id=post_id,
        author_id=_user_id(current_user),
        reply_to_id=request.reply_to_id,
        visual_label=request.visual_label,
        x=request.x,
        y=request.y,
        width=request.width,
        height=request.height,
        content=request.content,
        is_ai=False,
    )
    db.add(user_comment)
    db.flush()
    created = [user_comment]
    if "@ai" in request.content.lower():
        ai_comment = models.NeuroRoiComment(
            post_id=post_id,
            author_id=None,
            reply_to_id=user_comment.id,
            visual_label=request.visual_label,
            x=request.x,
            y=request.y,
            width=request.width,
            height=request.height,
            content=_ai_roi_reply(db, post, request),
            is_ai=True,
        )
        db.add(ai_comment)
        created.append(ai_comment)
    db.commit()
    for comment in created:
        db.refresh(comment)
    return {"items": [_serialize_roi_comment(comment) for comment in created]}


@router.delete("/posts/{post_id}/roi-comments/{comment_id}")
def recall_roi_comment(
    post_id: int,
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    post = _post_or_404(db, post_id)
    _require_clinical_case(post)
    comment = (
        db.query(models.NeuroRoiComment)
        .filter(
            models.NeuroRoiComment.id == comment_id,
            models.NeuroRoiComment.post_id == post_id,
        )
        .first()
    )
    if comment is None:
        raise HTTPException(status_code=404, detail="Khong tim thay ROI comment")
    user_id = _user_id(current_user)
    role = current_user.get("role")
    if not _can_recall_roi_comment(db, comment, post, user_id, role):
        raise HTTPException(status_code=403, detail="Khong co quyen thu hoi ROI comment nay")
    if comment.deleted_at is None:
        comment.deleted_at = datetime.utcnow()
        db.commit()
        db.refresh(comment)
    return _serialize_roi_comment(comment)


@router.post("/posts/{post_id}/comments", status_code=status.HTTP_201_CREATED)
def create_comment(
    post_id: int,
    request: CommentCreate,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    _post_or_404(db, post_id)
    if request.parent_id is not None:
        parent = (
            db.query(models.NeuroPostComment)
            .filter(
                models.NeuroPostComment.id == request.parent_id,
                models.NeuroPostComment.post_id == post_id,
                models.NeuroPostComment.deleted_at.is_(None),
            )
            .first()
        )
        if parent is None or parent.parent_id is not None:
            raise HTTPException(status_code=422, detail="Bình luận cha không hợp lệ")
    comment = models.NeuroPostComment(
        post_id=post_id,
        author_id=_user_id(current_user),
        parent_id=request.parent_id,
        content=request.content,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return _serialize_comment(comment)


@router.get("/posts/{post_id}/comments")
def get_comments(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    _user_id(current_user)
    _post_or_404(db, post_id)
    comments = (
        db.query(models.NeuroPostComment)
        .filter(
            models.NeuroPostComment.post_id == post_id,
            models.NeuroPostComment.deleted_at.is_(None),
        )
        .order_by(models.NeuroPostComment.created_at.asc())
        .all()
    )
    replies_by_parent: dict[int, list[dict[str, Any]]] = {}
    roots: list[dict[str, Any]] = []
    for comment in comments:
        serialized = _serialize_comment(comment)
        if comment.parent_id is None:
            serialized["replies"] = []
            roots.append(serialized)
        else:
            replies_by_parent.setdefault(comment.parent_id, []).append(serialized)
    for root in roots:
        root["replies"] = replies_by_parent.get(root["id"], [])
    return {"items": roots}


@router.put("/posts/{post_id}/save")
def save_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    post = _post_or_404(db, post_id)
    user_id = _user_id(current_user)
    exists = (
        db.query(models.NeuroPostSave.id)
        .filter(models.NeuroPostSave.post_id == post_id, models.NeuroPostSave.user_id == user_id)
        .first()
    )
    if exists is None:
        db.add(models.NeuroPostSave(post_id=post_id, user_id=user_id))
        db.commit()
    return _post_payload(db, post, user_id)


@router.delete("/posts/{post_id}/save")
def unsave_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    post = _post_or_404(db, post_id)
    user_id = _user_id(current_user)
    db.query(models.NeuroPostSave).filter(
        models.NeuroPostSave.post_id == post_id,
        models.NeuroPostSave.user_id == user_id,
    ).delete(synchronize_session=False)
    db.commit()
    return _post_payload(db, post, user_id)


def _pair_ids(user_a: int, user_b: int) -> tuple[int, int]:
    if user_a == user_b:
        raise HTTPException(status_code=422, detail="Khong the tao hoi thoai voi chinh minh")
    return (user_a, user_b) if user_a < user_b else (user_b, user_a)


def _get_or_create_conversation(db: Session, user_a: int, user_b: int) -> models.NeuroConversation:
    user_1_id, user_2_id = _pair_ids(user_a, user_b)
    conversation = (
        db.query(models.NeuroConversation)
        .filter(
            models.NeuroConversation.user_1_id == user_1_id,
            models.NeuroConversation.user_2_id == user_2_id,
        )
        .first()
    )
    if conversation:
        return conversation
    conversation = models.NeuroConversation(user_1_id=user_1_id, user_2_id=user_2_id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def _conversation_for_user(db: Session, conversation_id: int, user_id: int) -> models.NeuroConversation:
    conversation = (
        db.query(models.NeuroConversation)
        .filter(
            models.NeuroConversation.id == conversation_id,
            ((models.NeuroConversation.user_1_id == user_id) | (models.NeuroConversation.user_2_id == user_id)),
        )
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Khong tim thay hoi thoai")
    return conversation


def _other_user_id(conversation: models.NeuroConversation, user_id: int) -> int:
    return conversation.user_2_id if conversation.user_1_id == user_id else conversation.user_1_id


def _user_display(user: models.User | None) -> dict[str, Any]:
    username = user.username if user else "unknown"
    display_name = username.replace("_", " ").replace(".", " ").title()
    if username.startswith("doctor_"):
        display_name = "Dr. " + username.replace("doctor_", "").replace("_", " ").title()
    elif username.startswith("dr_"):
        display_name = "Dr. " + username.replace("dr_", "").replace("_", " ").title()
    return {
        "id": user.id if user else None,
        "username": username,
        "display_name": display_name,
        "role": user.role if user else None,
    }


def _last_active(db: Session, user_id: int) -> datetime | None:
    log = (
        db.query(models.AccessLog)
        .filter(models.AccessLog.user_id == user_id)
        .order_by(models.AccessLog.timestamp.desc())
        .first()
    )
    return log.timestamp if log else None


def _doctor_payload(db: Session, user: models.User, current_user_id: int) -> dict[str, Any]:
    conversation = None
    try:
        user_1_id, user_2_id = _pair_ids(user.id, current_user_id)
        conversation = (
            db.query(models.NeuroConversation)
            .filter(
                models.NeuroConversation.user_1_id == user_1_id,
                models.NeuroConversation.user_2_id == user_2_id,
            )
            .first()
        )
    except HTTPException:
        conversation = None
    unread_count = 0
    latest_message = None
    if conversation:
        unread_count = (
            db.query(models.NeuroMessage)
            .filter(
                models.NeuroMessage.conversation_id == conversation.id,
                models.NeuroMessage.sender_id == user.id,
                models.NeuroMessage.read_at.is_(None),
            )
            .count()
        )
        latest_message = (
            db.query(models.NeuroMessage)
            .filter(models.NeuroMessage.conversation_id == conversation.id)
            .order_by(models.NeuroMessage.created_at.desc(), models.NeuroMessage.id.desc())
            .first()
        )
    last_active = _last_active(db, user.id)
    is_online = bool(last_active and last_active >= datetime.utcnow() - timedelta(minutes=15))
    return {
        **_user_display(user),
        "is_online": is_online,
        "last_active_at": last_active,
        "unread_count": unread_count,
        "conversation_id": conversation.id if conversation else None,
        "latest_message_at": latest_message.created_at if latest_message else None,
    }


def _case_payload(db: Session, image: models.Image, analysis: models.AnalysisResult | None) -> dict[str, Any]:
    patient = db.query(models.Patient).filter(models.Patient.id == image.patient_id).first()
    second_opinion = (
        db.query(models.NeuroSecondOpinionRequest)
        .filter(models.NeuroSecondOpinionRequest.case_image_id == image.id)
        .order_by(models.NeuroSecondOpinionRequest.created_at.desc())
        .first()
    )
    media = _clinical_media_payload(db, image, analysis)
    return {
        "case_id": image.id,
        "image_id": image.id,
        "patient_id": patient.id if patient else image.patient_id,
        "patient_name": patient.name if patient else None,
        "patient_external_id": patient.patient_external_id if patient else None,
        "scan_date": image.scan_date,
        "thumbnail_url": media.get("mri_url"),
        "ai_label": "No tumor" if analysis and analysis.no_tumor_detected else (analysis.tumor_label if analysis else None),
        "confidence": analysis.classification_confidence if analysis else None,
        "risk_score": None if analysis and analysis.no_tumor_detected else (analysis.risk_score if analysis else None),
        "risk_group": None if analysis and analysis.no_tumor_detected else (analysis.risk_group if analysis else None),
        "review_status": "completed"
        if db.query(models.ClassificationReview).filter(models.ClassificationReview.image_id == image.id).first()
        else ("needs_review" if analysis and analysis.classification_confidence is not None and analysis.classification_confidence < 0.95 and not analysis.no_tumor_detected else "not_required"),
        "second_opinion_status": second_opinion.status if second_opinion else None,
        "second_opinion_request_id": second_opinion.id if second_opinion else None,
    }


def _serialize_message(db: Session, message: models.NeuroMessage, current_user_id: int) -> dict[str, Any]:
    sender = db.query(models.User).filter(models.User.id == message.sender_id).first()
    case_payload = None
    second_opinion = None
    if message.case_image_id:
        image = db.query(models.Image).filter(models.Image.id == message.case_image_id).first()
        analysis = db.query(models.AnalysisResult).filter(models.AnalysisResult.image_id == message.case_image_id).first()
        if image:
            case_payload = _case_payload(db, image, analysis)
    if message.second_opinion_request_id:
        request = (
            db.query(models.NeuroSecondOpinionRequest)
            .filter(models.NeuroSecondOpinionRequest.id == message.second_opinion_request_id)
            .first()
        )
        if request:
            second_opinion = {
                "id": request.id,
                "status": request.status,
                "request_message": request.request_message,
            }
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "sender": _user_display(sender),
        "is_mine": message.sender_id == current_user_id,
        "reply_to_id": message.reply_to_id,
        "message_type": message.message_type,
        "content": message.content,
        "image_url": display_media_url(message.image_path),
        "image_original_name": message.image_original_name,
        "case": case_payload,
        "second_opinion": second_opinion,
        "created_at": message.created_at,
        "read_at": message.read_at,
    }


@router.get("/doctors")
def list_doctors(
    q: str = "",
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    current_user_id = _user_id(current_user)
    query = db.query(models.User).filter(models.User.is_active.is_(True), models.User.id != current_user_id)
    if q.strip():
        keyword = f"%{q.strip()}%"
        query = query.filter(models.User.username.ilike(keyword))
    users = query.order_by(models.User.username.asc()).all()
    return {"items": [_doctor_payload(db, user, current_user_id) for user in users]}


@router.get("/messenger/conversations/{doctor_id}")
def get_conversation_with_doctor(
    doctor_id: int,
    search: str = "",
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    current_user_id = _user_id(current_user)
    doctor = db.query(models.User).filter(models.User.id == doctor_id, models.User.is_active.is_(True)).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Khong tim thay bac si")
    conversation = _get_or_create_conversation(db, current_user_id, doctor_id)
    message_query = db.query(models.NeuroMessage).filter(models.NeuroMessage.conversation_id == conversation.id)
    if search.strip():
        message_query = message_query.filter(models.NeuroMessage.content.ilike(f"%{search.strip()}%"))
    messages = message_query.order_by(models.NeuroMessage.created_at.asc(), models.NeuroMessage.id.asc()).limit(200).all()
    serialized_messages = [_serialize_message(db, message, current_user_id) for message in messages]
    now = datetime.utcnow()
    db.query(models.NeuroMessage).filter(
        models.NeuroMessage.conversation_id == conversation.id,
        models.NeuroMessage.sender_id == doctor_id,
        models.NeuroMessage.read_at.is_(None),
    ).update({"read_at": now}, synchronize_session=False)
    db.commit()
    return {
        "conversation": {
            "id": conversation.id,
            "doctor": _doctor_payload(db, doctor, current_user_id),
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
        },
        "messages": serialized_messages,
    }


@router.post("/messenger/conversations/{doctor_id}/messages", status_code=status.HTTP_201_CREATED)
async def send_message_to_doctor(
    doctor_id: int,
    content: str = Form(""),
    case_image_id: Optional[int] = Form(None),
    reply_to_id: Optional[int] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    current_user_id = _user_id(current_user)
    doctor = db.query(models.User).filter(models.User.id == doctor_id, models.User.is_active.is_(True)).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Khong tim thay bac si")
    conversation = _get_or_create_conversation(db, current_user_id, doctor_id)
    normalized_content = content.strip()
    stored_image: dict[str, str] = {}
    if image is not None:
        stored_image = await store_message_image(conversation.id, image)
    if reply_to_id is not None:
        parent = (
            db.query(models.NeuroMessage)
            .filter(
                models.NeuroMessage.id == reply_to_id,
                models.NeuroMessage.conversation_id == conversation.id,
            )
            .first()
        )
        if not parent:
            raise HTTPException(status_code=422, detail="Tin nhan reply khong hop le")
    if case_image_id is not None and not crud.get_image_for_user(db, case_image_id, current_user):
        raise HTTPException(status_code=404, detail="Khong tim thay clinical case trong dataset cua ban")
    if not normalized_content and not stored_image and case_image_id is None:
        raise HTTPException(status_code=422, detail="Tin nhan can noi dung, anh hoac clinical case")

    message_type = "case" if case_image_id is not None else ("image" if stored_image else "text")
    message = models.NeuroMessage(
        conversation_id=conversation.id,
        sender_id=current_user_id,
        reply_to_id=reply_to_id,
        message_type=message_type,
        content=normalized_content or None,
        case_image_id=case_image_id,
        **stored_image,
    )
    db.add(message)
    db.flush()

    if case_image_id is not None:
        request = models.NeuroSecondOpinionRequest(
            case_image_id=case_image_id,
            requester_doctor_id=current_user_id,
            reviewer_doctor_id=doctor_id,
            conversation_id=conversation.id,
            message_id=message.id,
            request_message=normalized_content or None,
            status="Pending",
        )
        db.add(request)
        db.flush()
        message.second_opinion_request_id = request.id

    conversation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(message)
    return _serialize_message(db, message, current_user_id)


@router.post("/second-opinions/{request_id}/open")
def open_second_opinion(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    current_user_id = _user_id(current_user)
    request = (
        db.query(models.NeuroSecondOpinionRequest)
        .filter(models.NeuroSecondOpinionRequest.id == request_id)
        .first()
    )
    if not request or request.reviewer_doctor_id != current_user_id:
        raise HTTPException(status_code=404, detail="Khong tim thay second opinion request")
    if request.status == "Pending":
        request.status = "In Review"
        db.commit()
        db.refresh(request)
    return {"id": request.id, "status": request.status}


@router.get("/review-queue")
def get_review_queue(
    scope: str = "all",
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    current_user_id = _user_id(current_user)
    items: list[dict[str, Any]] = []

    review_rows = (
        db.query(models.Image, models.AnalysisResult, models.Patient)
        .join(models.AnalysisResult, models.AnalysisResult.image_id == models.Image.id)
        .join(models.Patient, models.Patient.id == models.Image.patient_id)
        .filter(
            models.Patient.owner_user_id == current_user_id,
            models.AnalysisResult.no_tumor_detected.is_(False),
            models.AnalysisResult.classification_confidence.isnot(None),
            models.AnalysisResult.classification_confidence < 0.95,
        )
        .order_by(models.AnalysisResult.created_at.desc())
        .all()
    )
    for image, analysis, patient in review_rows:
        completed = (
            db.query(models.ClassificationReview)
            .filter(models.ClassificationReview.image_id == image.id)
            .first()
            is not None
        )
        status_value = "Completed" if completed else "Need Review"
        if scope == "completed" and not completed:
            continue
        if scope in {"my_reviews", "all"} and completed:
            continue
        if scope == "second_opinions":
            continue
        case = _case_payload(db, image, analysis)
        items.append(
            {
                "id": f"review-{image.id}",
                "queue_type": "my_review",
                "status": status_value,
                "priority": "High" if analysis.classification_confidence and analysis.classification_confidence < 0.9 else "Medium",
                "deadline": None,
                "assigned_to": current_user_id,
                "request": None,
                "case": case,
            }
        )

    if scope in {"all", "second_opinions", "completed"}:
        request_query = db.query(models.NeuroSecondOpinionRequest).filter(
            models.NeuroSecondOpinionRequest.reviewer_doctor_id == current_user_id
        )
        if scope == "completed":
            request_query = request_query.filter(models.NeuroSecondOpinionRequest.status == "Completed")
        else:
            request_query = request_query.filter(models.NeuroSecondOpinionRequest.status != "Completed")
        requests = request_query.order_by(models.NeuroSecondOpinionRequest.created_at.desc()).all()
        for request in requests:
            image = db.query(models.Image).filter(models.Image.id == request.case_image_id).first()
            analysis = db.query(models.AnalysisResult).filter(models.AnalysisResult.image_id == request.case_image_id).first()
            requester = db.query(models.User).filter(models.User.id == request.requester_doctor_id).first()
            if not image:
                continue
            items.append(
                {
                    "id": f"second-opinion-{request.id}",
                    "queue_type": "second_opinion",
                    "status": request.status,
                    "priority": "Second Opinion",
                    "deadline": None,
                    "assigned_to": current_user_id,
                    "request": {
                        "id": request.id,
                        "from": _user_display(requester),
                        "message": request.request_message,
                        "created_at": request.created_at,
                    },
                    "case": _case_payload(db, image, analysis),
                }
            )

    return {"items": items}


@router.get("/my-cases")
def get_my_cases(
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    current_user_id = _user_id(current_user)
    rows = (
        db.query(models.Image, models.AnalysisResult)
        .join(models.Patient, models.Patient.id == models.Image.patient_id)
        .outerjoin(models.AnalysisResult, models.AnalysisResult.image_id == models.Image.id)
        .filter(models.Patient.owner_user_id == current_user_id)
        .order_by(models.Image.scan_date.desc(), models.Image.id.desc())
        .limit(100)
        .all()
    )
    return {"items": [_case_payload(db, image, analysis) for image, analysis in rows]}


@router.get("/case-options")
def get_case_options(
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    user_id = _user_id(current_user)
    rows = (
        db.query(models.AnalysisResult, models.Image, models.Patient)
        .join(models.Image, models.Image.id == models.AnalysisResult.image_id)
        .join(models.Patient, models.Patient.id == models.Image.patient_id)
        .filter(models.Patient.owner_user_id == user_id)
        .order_by(models.AnalysisResult.created_at.desc())
        .limit(100)
        .all()
    )
    return {
        "items": [
            {
                "image_id": analysis.image_id,
                "patient_id": patient.id,
                "patient_name": patient.name,
                "patient_external_id": patient.patient_external_id,
                "scan_date": image.scan_date,
                "analysis_created_at": analysis.created_at,
                "ai_label": analysis.tumor_label,
                "confidence": analysis.classification_confidence,
                "no_tumor_detected": bool(analysis.no_tumor_detected),
            }
            for analysis, image, patient in rows
        ]
    }
