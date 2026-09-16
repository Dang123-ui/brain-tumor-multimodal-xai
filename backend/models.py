from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Text, JSON, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base
import datetime


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    name = Column(String, nullable=True)
    patient_external_id = Column(String, unique=True, index=True, nullable=True)
    age = Column(Integer, nullable=True)
    gender = Column(String, nullable=True)

    owner_user = relationship("User", back_populates="patients")
    images = relationship("Image", back_populates="owner")
    rna_data = relationship("RnaData", back_populates="patient")
    clinical_data = relationship("ClinicalData", back_populates="patient", uselist=False)


class Image(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    scan_date = Column(DateTime, default=datetime.datetime.utcnow)
    modality = Column(String)  # MRI, CT, WSI
    file_path = Column(String)  # Đường dẫn tới bucket MinIO (hoặc folder nếu là series)
    
    # Mở rộng cho chuỗi ảnh (Series)
    is_series = Column(Boolean, default=False)
    num_slices = Column(Integer, default=1)
    key_slice_index = Column(Integer, default=0) # Index của lát cắt quan trọng nhất

    owner = relationship("Patient", back_populates="images")
    diagnoses = relationship("Diagnosis", back_populates="image")
    analysis_result = relationship("AnalysisResult", back_populates="image", uselist=False)


class Diagnosis(Base):
    __tablename__ = "diagnoses"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey("images.id"))
    result = Column(JSON)
    access_log = Column(Text)

    image = relationship("Image", back_populates="diagnoses")


# --- NHÓM MÔ THỨC MỚI ---

class RnaData(Base):
    """Lưu trữ metadata và đường dẫn tệp RNA-seq đã được tải lên MinIO."""
    __tablename__ = "rna_data"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    upload_date = Column(DateTime, default=datetime.datetime.utcnow)
    file_path = Column(String)           # Đường dẫn object trong bucket MinIO `rna-data`
    file_format = Column(String)         # "csv" hoặc "tsv"
    num_genes = Column(Integer)          # Số lượng gen (số cột dữ liệu)
    expression_unit = Column(String)     # Đơn vị đo: TPM, FPKM, counts, ...

    patient = relationship("Patient", back_populates="rna_data")


class ClinicalData(Base):
    """Lưu trữ thông tin lâm sàng bổ sung cho mô hình tiên lượng."""
    __tablename__ = "clinical_data"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), unique=True, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Chỉ số KI-67 — cột riêng biệt để truy xuất nhanh trên Dashboard
    ki67_index = Column(Float, nullable=True)

    # Các marker sinh hóa khác (WBC, RBC, ...) lưu dạng JSON linh hoạt
    biochemistry_markers = Column(JSON, nullable=True)

    # Trạng thái lâm sàng ban đầu: newly_diagnosed, recurrent, progressive
    initial_status = Column(String, nullable=True)
    
    # Thông tin tiên lượng bổ sung
    grade = Column(String, nullable=True)             # WHO Grade (2, 3, 4)
    prior_treatment = Column(String, nullable=True)    # 0 | 1
    idh_mutation = Column(String, nullable=True)       # 0 | 1
    mgmt_methylation = Column(String, nullable=True)   # 0 | 1

    patient = relationship("Patient", back_populates="clinical_data")


# --- NHÓM AI INFERENCE ---

class InferenceTask(Base):
    """Theo dõi trạng thái tác vụ Celery bất đồng bộ."""
    __tablename__ = "inference_tasks"

    id = Column(Integer, primary_key=True, index=True)
    celery_task_id = Column(String, unique=True, index=True)
    task_type = Column(String)      # "mri_pipeline" hoặc "prognosis"
    target_id = Column(Integer)     # image_id hoặc patient_id tùy task_type
    status = Column(String, default="pending")  # pending | processing | done | failed
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)


class AnalysisResult(Base):
    """Lưu kết quả chẩn đoán và hiệu suất mô hình AI sau khi pipeline hoàn thành."""
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey("images.id"), unique=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # --- Phân loại u (YOLOv5 + DenseNet169-ViT) ---
    no_tumor_detected = Column(Boolean, default=False)
    tumor_label = Column(String, nullable=True)        # VD: "Glioblastoma", "Meningioma"
    classification_confidence = Column(Float, nullable=True)

    # --- Chỉ số hiệu suất phân đoạn (U-Net) — riêng biệt để viết báo cáo ---
    dice_score = Column(Float, nullable=True)
    iou_score = Column(Float, nullable=True)
    accuracy = Column(Float, nullable=True)

    # --- Chỉ số tiên lượng sống còn (Fusion Model) ---
    c_index = Column(Float, nullable=True)             # Harrell's C-index
    risk_score = Column(Float, nullable=True)          # Điểm nguy cơ thô từ Attention-Fusion
    risk_group = Column(String, nullable=True)         # "high" | "low"

    # --- Đường dẫn file XAI trên MinIO (để tạo Presigned URL) ---
    gradcam_path = Column(String, nullable=True)       # File Grad-CAM heatmap
    mask_path = Column(String, nullable=True)          # File phân đoạn mask

    # --- Dữ liệu survival curve dạng JSON: [{time, survival_prob}] ---
    finer_cam_path = Column(String, nullable=True)
    seg_eigen_cam_path = Column(String, nullable=True)
    odam_path = Column(String, nullable=True)
    xai_3_panel_path = Column(String, nullable=True)
    survival_curve_data = Column(JSON, nullable=True)

    image = relationship("Image", back_populates="analysis_result")


class AIExplanation(Base):
    """Stores generated text explanations for XAI outputs."""
    __tablename__ = "ai_explanations"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey("images.id"), index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True, nullable=True)
    explanation_type = Column(String, index=True)  # classification_xai | risk_score
    model_name = Column(String, nullable=True)
    content = Column(Text)
    rag_context = Column(JSON, nullable=True)
    xai_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    image = relationship("Image")
    patient = relationship("Patient")


class PatientHistoryReport(Base):
    """Cached narrative text for a patient's longitudinal diagnosis report."""
    __tablename__ = "patient_history_reports"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    report_type = Column(String, default="diagnosis_history", index=True)
    status = Column(String, default="not_created")  # not_created | generating | ready | stale | failed
    data_hash = Column(String, index=True, nullable=True)

    summary_text = Column(Text, nullable=True)
    classification_trend_text = Column(Text, nullable=True)
    risk_trend_text = Column(Text, nullable=True)
    conclusion_text = Column(Text, nullable=True)

    llm_model = Column(String, nullable=True)
    prompt_version = Column(String, nullable=True)
    source_metadata = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    patient = relationship("Patient")


class ExpertValidation(Base):
    """Lưu trữ điểm đánh giá tính hợp lý lâm sàng (Sanity Check) từ chuyên gia/bác sĩ."""
    __tablename__ = "expert_validations"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey("images.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)  # Bác sĩ đánh giá
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # 1 đến 5 sao
    rating = Column(Integer, nullable=False)
    # Phương pháp XAI được đánh giá (gradcam, gradcam++, layercam)
    heatmap_method = Column(String, nullable=True)
    # Bình luận thêm nếu có
    comments = Column(Text, nullable=True)

    image = relationship("Image")
    user = relationship("User")


class ClassificationReview(Base):
    """Stores expert confirmation/correction for low-confidence classification results."""
    __tablename__ = "classification_reviews"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey("images.id"), index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    ai_tumor_label = Column(String, nullable=True)
    ai_confidence = Column(Float, nullable=True)
    expert_tumor_label = Column(String, nullable=False)
    expert_comment = Column(Text, nullable=True)
    review_action = Column(String, nullable=False)  # confirmed | corrected

    image = relationship("Image")
    patient = relationship("Patient")
    user = relationship("User")


# --- NHÓM AUTH & ADMIN ---

class User(Base):
    """Người dùng hệ thống với phân quyền theo vai trò."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String)          # "doctor" | "researcher"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    access_logs = relationship("AccessLog", back_populates="user")
    patients = relationship("Patient", back_populates="owner_user")


class AccessLog(Base):
    """Nhật ký truy cập API để đảm bảo tính minh bạch trong NCKH."""
    __tablename__ = "access_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    method = Column(String)        # GET, POST, PATCH, DELETE
    endpoint = Column(String)
    client_ip = Column(String)
    status_code = Column(Integer)

    user = relationship("User", back_populates="access_logs")


class AgentConversation(Base):
    """Chat thread metadata for the NeuroDiagnosis Agent."""
    __tablename__ = "agent_conversations"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True, index=True)
    image_id = Column(Integer, ForeignKey("images.id"), nullable=True, index=True)
    title = Column(Text, nullable=True)
    status = Column(String, default="active", index=True)
    summary = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)


class AgentMessage(Base):
    """Persisted chat messages for short-term memory and auditability."""
    __tablename__ = "agent_messages"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(String, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    message_type = Column(String, default="text")
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    deleted_at = Column(DateTime, nullable=True)


class AgentAuditLog(Base):
    """Audit trail for sensitive Agent actions."""
    __tablename__ = "agent_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True, index=True)
    image_id = Column(Integer, ForeignKey("images.id"), nullable=True, index=True)
    thread_id = Column(String, nullable=True, index=True)
    action = Column(String, nullable=False, index=True)
    tool_name = Column(String, nullable=True)
    before_value = Column(JSON, nullable=True)
    after_value = Column(JSON, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


# --- NEUROBOARD ---

class NeuroPost(Base):
    """A normal social post or an anonymized clinical case post."""
    __tablename__ = "neuro_posts"

    id = Column(Integer, primary_key=True, index=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    post_type = Column(String, nullable=False, index=True)  # normal | clinical_case
    content = Column(Text, nullable=True)
    image_id = Column(Integer, ForeignKey("images.id"), nullable=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True, index=True)
    anonymous_case_code = Column(String, unique=True, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )
    deleted_at = Column(DateTime, nullable=True, index=True)

    author = relationship("User")
    image = relationship("Image")
    patient = relationship("Patient")
    attachments = relationship(
        "NeuroPostAttachment",
        back_populates="post",
        cascade="all, delete-orphan",
        order_by="NeuroPostAttachment.sort_order",
    )


class NeuroPostAttachment(Base):
    __tablename__ = "neuro_post_attachments"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("neuro_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    object_path = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    original_name = Column(String, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    post = relationship("NeuroPost", back_populates="attachments")


class NeuroPostReaction(Base):
    __tablename__ = "neuro_post_reactions"
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_neuro_reaction_post_user"),)

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("neuro_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reaction_type = Column(String, default="like", nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)


class NeuroPostComment(Base):
    __tablename__ = "neuro_post_comments"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("neuro_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("neuro_post_comments.id", ondelete="CASCADE"), nullable=True, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )
    deleted_at = Column(DateTime, nullable=True, index=True)

    author = relationship("User")


class NeuroPostSave(Base):
    __tablename__ = "neuro_post_saves"
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_neuro_save_post_user"),)

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("neuro_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)


class NeuroRoiComment(Base):
    __tablename__ = "neuro_roi_comments"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("neuro_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    reply_to_id = Column(Integer, ForeignKey("neuro_roi_comments.id", ondelete="CASCADE"), nullable=True, index=True)
    visual_label = Column(String, nullable=False)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)
    content = Column(Text, nullable=False)
    is_ai = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True, index=True)

    author = relationship("User")


class NeuroConversation(Base):
    __tablename__ = "neuro_conversations"
    __table_args__ = (UniqueConstraint("user_1_id", "user_2_id", name="uq_neuro_conversation_pair"),)

    id = Column(Integer, primary_key=True, index=True)
    user_1_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    user_2_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )


class NeuroMessage(Base):
    __tablename__ = "neuro_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("neuro_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reply_to_id = Column(Integer, ForeignKey("neuro_messages.id", ondelete="SET NULL"), nullable=True, index=True)
    message_type = Column(String, default="text", nullable=False, index=True)
    content = Column(Text, nullable=True)
    image_path = Column(String, nullable=True)
    image_content_type = Column(String, nullable=True)
    image_original_name = Column(String, nullable=True)
    case_image_id = Column(Integer, ForeignKey("images.id"), nullable=True, index=True)
    second_opinion_request_id = Column(Integer, ForeignKey("neuro_second_opinion_requests.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    read_at = Column(DateTime, nullable=True, index=True)

    sender = relationship("User")


class NeuroSecondOpinionRequest(Base):
    __tablename__ = "neuro_second_opinion_requests"

    id = Column(Integer, primary_key=True, index=True)
    case_image_id = Column(Integer, ForeignKey("images.id"), nullable=False, index=True)
    requester_doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reviewer_doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("neuro_conversations.id"), nullable=False, index=True)
    message_id = Column(Integer, ForeignKey("neuro_messages.id"), nullable=True, index=True)
    request_message = Column(Text, nullable=True)
    status = Column(String, default="Pending", nullable=False, index=True)
    opinion = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True, index=True)
