from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


# ============================================================
# PATIENT SCHEMAS (hiện có)
# ============================================================

class PatientCreate(BaseModel):
    name: str
    external_id: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None


class PatientUpdate(BaseModel):
    age: Optional[int] = None
    gender: Optional[str] = None


# ============================================================
# CLINICAL DATA SCHEMAS
# ============================================================

class ClinicalDataUpdate(BaseModel):
    """Schema cập nhật dữ liệu lâm sàng bổ sung — tất cả trường đều tùy chọn."""
    ki67_index: Optional[float] = None
    biochemistry_markers: Optional[dict] = None
    initial_status: Optional[str] = None  # newly_diagnosed | recurrent | progressive
    grade: Optional[str] = None
    prior_treatment: Optional[str] = None
    idh_mutation: Optional[str] = None
    mgmt_methylation: Optional[str] = None


class ClinicalDataResponse(BaseModel):
    patient_id: int
    ki67_index: Optional[float]
    biochemistry_markers: Optional[dict]
    initial_status: Optional[str]
    grade: Optional[str]
    prior_treatment: Optional[str]
    idh_mutation: Optional[str]
    mgmt_methylation: Optional[str]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# ============================================================
# RNA DATA SCHEMAS
# ============================================================

class RnaDataResponse(BaseModel):
    id: int
    patient_id: int
    file_path: str
    file_format: str
    num_genes: Optional[int]
    expression_unit: Optional[str]
    upload_date: datetime

    class Config:
        from_attributes = True


# ============================================================
# INFERENCE TASK SCHEMAS
# ============================================================

class InferenceTaskResponse(BaseModel):
    """Phản hồi khi kích hoạt tác vụ AI — trả về task_id để client polling."""
    task_id: int
    celery_task_id: str
    status: str
    message: str


class InferenceTaskStatus(BaseModel):
    """Trạng thái hiện tại của một tác vụ AI đang chờ hoặc đã xong."""
    task_id: int
    celery_task_id: str
    task_type: str
    status: str                        # pending | processing | done | failed
    progress_percent: Optional[int] = None
    progress_status: Optional[str] = None
    result: Optional[Any] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================
# ANALYSIS & XAI SCHEMAS
# ============================================================

class AnalysisResultResponse(BaseModel):
    """Kết quả chẩn đoán tổng hợp bao gồm đầy đủ chỉ số hiệu suất."""
    id: int
    image_id: int
    patient_id: int

    # Phân loại u
    no_tumor_detected: Optional[bool] = None
    tumor_label: Optional[str]
    classification_confidence: Optional[float]
    review_action: Optional[str] = None
    reviewed_at: Optional[datetime] = None

    # Hiệu suất phân đoạn (U-Net)
    dice_score: Optional[float]
    iou_score: Optional[float]
    accuracy: Optional[float]

    # Tiên lượng sống còn
    c_index: Optional[float]
    risk_score: Optional[float]
    risk_group: Optional[str]
    survival_curve_data: Optional[List[dict]] = None

    created_at: datetime

    class Config:
        from_attributes = True


class ImageAIResultResponse(BaseModel):
    image_id: int
    patient_id: Optional[int] = None
    task_id: Optional[int] = None
    status: str
    no_tumor_detected: Optional[bool] = None
    error_message: Optional[str] = None
    bbox: Optional[List[int]] = None
    bbox_confidence: Optional[float] = None
    tumor_label: Optional[str] = None
    classification_confidence: Optional[float] = None
    ai_tumor_label: Optional[str] = None
    ai_confidence: Optional[float] = None
    final_tumor_label: Optional[str] = None
    expert_tumor_label: Optional[str] = None
    expert_comment: Optional[str] = None
    review_required: bool = False
    review_status: str = "not_available"
    review_action: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    class_probabilities: Optional[List[float]] = None
    bbox_overlay_data_url: Optional[str] = None
    mask_data_url: Optional[str] = None
    mask_overlay_data_url: Optional[str] = None
    contour_overlay_data_url: Optional[str] = None
    # Multimodal prognosis fields
    risk_score: Optional[float] = None
    risk_group: Optional[str] = None
    survival_curve_data: Optional[List[dict]] = None
    multimodal_risk_xai_data_url: Optional[str] = None
    multimodal_gradcam_heatmap_data_url: Optional[str] = None
    multimodal_gradcam_plus_heatmap_data_url: Optional[str] = None
    multimodal_layercam_heatmap_data_url: Optional[str] = None
    gradcam_heatmap_data_url: Optional[str] = None
    gradcam_plus_heatmap_data_url: Optional[str] = None
    layercam_heatmap_data_url: Optional[str] = None
    detection_xai_data_url: Optional[str] = None
    segmentation_xai_data_url: Optional[str] = None
    classification_xai_data_url: Optional[str] = None
    xai_methods: Optional[dict] = None
    xai_warnings: Optional[dict] = None
    xai_metadata: Optional[dict] = None
    xai_explanation: Optional[str] = None
    classification_xai_explanation: Optional[str] = None
    multimodal_xai_explanation: Optional[str] = None
    fusion_attention: Optional[List[Optional[float]]] = None
    rna_xai: Optional[List[dict]] = None
    # Series metadata
    is_series: bool = False
    num_slices: int = 1
    key_slice_index: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ClassificationXAIExplanationResponse(BaseModel):
    image_id: int
    patient_id: Optional[int] = None
    explanation_type: str
    model_name: Optional[str] = None
    content: str
    rag_context: Optional[dict] = None
    xai_metadata: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class XAIOverlayResponse(BaseModel):
    """URL tạm thời để Frontend tải ảnh Grad-CAM và Mask."""
    image_id: int
    gradcam_url: Optional[str]
    mask_url: Optional[str]


class SurvivalPoint(BaseModel):
    """Một điểm dữ liệu trên đường cong Kaplan-Meier."""
    time: float
    survival_probability: float


class SurvivalCurveResponse(BaseModel):
    patient_id: int
    risk_group: Optional[str]
    curve: List[SurvivalPoint]


class ExpertValidationCreate(BaseModel):
    rating: int
    heatmap_method: str
    comments: Optional[str] = None


class ExpertValidationResponse(ExpertValidationCreate):
    id: int
    image_id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class ClassificationReviewCreate(BaseModel):
    expert_tumor_label: str
    expert_comment: Optional[str] = None


class ClassificationReviewResponse(BaseModel):
    id: int
    image_id: int
    patient_id: int
    user_id: Optional[int] = None
    ai_tumor_label: Optional[str] = None
    ai_confidence: Optional[float] = None
    expert_tumor_label: str
    expert_comment: Optional[str] = None
    final_tumor_label: str
    review_action: str
    review_status: str
    review_required: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class DiagnosisHistoryPatientItem(BaseModel):
    patient_id: int
    patient_external_id: Optional[str] = None
    patient_name: Optional[str] = None
    last_diagnosis_time: Optional[datetime] = None
    latest_no_tumor_detected: bool = False
    latest_tumor_label: Optional[str] = None
    latest_classification_confidence: Optional[float] = None
    latest_ai_tumor_label: Optional[str] = None
    latest_final_tumor_label: Optional[str] = None
    latest_review_status: str = "not_available"
    latest_review_required: bool = False
    review_required_count: int = 0
    review_corrected_count: int = 0
    review_confirmed_count: int = 0
    latest_risk_score: Optional[float] = None
    latest_risk_group: Optional[str] = None
    diagnosis_count: int = 0
    history_report_status: str = "not_created"


class DiagnosisHistoryListResponse(BaseModel):
    items: List[DiagnosisHistoryPatientItem]
    page: int
    page_size: int
    total: int


class PatientHistoryTimelineItem(BaseModel):
    diagnosis_index: int
    image_id: int
    modality: Optional[str] = None
    scan_date: Optional[datetime] = None
    image_url: Optional[str] = None
    ai_status: str = "ready"
    no_tumor_detected: bool = False
    tumor_label: Optional[str] = None
    classification_confidence: Optional[float] = None
    ai_tumor_label: Optional[str] = None
    final_tumor_label: Optional[str] = None
    expert_tumor_label: Optional[str] = None
    review_status: str = "not_available"
    review_required: bool = False
    expert_comment: Optional[str] = None
    ai_tumor_label: Optional[str] = None
    ai_confidence: Optional[float] = None
    final_tumor_label: Optional[str] = None
    expert_tumor_label: Optional[str] = None
    expert_comment: Optional[str] = None
    review_required: bool = False
    review_status: str = "not_available"
    review_action: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    risk_score: Optional[float] = None
    risk_group: Optional[str] = None
    is_series: bool = False
    num_slices: int = 1
    key_slice_index: int = 0


class PatientHistoryReportTexts(BaseModel):
    summary_text: Optional[str] = None
    classification_trend_text: Optional[str] = None
    risk_trend_text: Optional[str] = None
    conclusion_text: Optional[str] = None


class PatientHistoryReportResponse(BaseModel):
    patient: dict
    summary: dict
    timeline: List[PatientHistoryTimelineItem]
    risk_trend: List[dict]
    no_tumor_risk_notes: List[dict] = Field(default_factory=list)
    multimodal_data: dict
    expert_validations: List[dict]
    report_status: str
    data_hash: Optional[str] = None
    texts: PatientHistoryReportTexts
    error_message: Optional[str] = None


# ============================================================
# AUTH SCHEMAS
# ============================================================

class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    user_id: int


class TokenData(BaseModel):
    user_id: Optional[int] = None
    role: Optional[str] = None


# ============================================================
# ADMIN SCHEMAS
# ============================================================

class AccessLogResponse(BaseModel):
    id: int
    user_id: Optional[int]
    timestamp: datetime
    method: str
    endpoint: str
    client_ip: str
    status_code: int

    class Config:
        from_attributes = True
