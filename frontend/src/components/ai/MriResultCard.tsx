"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  X,
} from "lucide-react";
import RnaXaiChart from "./RnaXaiChart";
import { ImagePreviewModal, ImagePreviewState } from "@/components/ui/ImagePreviewModal";

type MriResult = {
  image_id?: number | string;
  status?: string;
  no_tumor_detected?: boolean | null;
  error_message?: string | null;
  bbox?: number[] | null;
  bbox_confidence?: number | null;
  tumor_label?: string | null;
  classification_confidence?: number | null;
  ai_tumor_label?: string | null;
  ai_confidence?: number | null;
  final_tumor_label?: string | null;
  expert_tumor_label?: string | null;
  expert_comment?: string | null;
  review_required?: boolean;
  review_status?: "not_available" | "not_required" | "needs_review" | "confirmed" | "corrected" | string;
  review_action?: string | null;
  reviewed_at?: string | null;
  class_probabilities?: number[] | null;
  bbox_overlay_data_url?: string | null;
  mask_data_url?: string | null;
  mask_overlay_data_url?: string | null;
  contour_overlay_data_url?: string | null;
  // Multimodal prognosis fields
  risk_score?: number | null;
  risk_group?: string | null;
  survival_curve_data?: { time: number; survival_probability: number }[] | null;
  multimodal_risk_xai_data_url?: string | null;
  multimodal_gradcam_heatmap_data_url?: string | null;
  multimodal_gradcam_plus_heatmap_data_url?: string | null;
  multimodal_layercam_heatmap_data_url?: string | null;
  gradcam_heatmap_data_url?: string | null;
  gradcam_plus_heatmap_data_url?: string | null;
  layercam_heatmap_data_url?: string | null;
  detection_xai_data_url?: string | null;
  segmentation_xai_data_url?: string | null;
  classification_xai_data_url?: string | null;
  xai_methods?: Record<string, string> | null;
  xai_warnings?: Record<string, string> | null;
  xai_metadata?: Record<string, unknown> | null;
  xai_explanation?: string | null;
  classification_xai_explanation?: string | null;
  multimodal_xai_explanation?: string | null;
  fusion_attention?: number[] | null;
  // Series metadata
  is_series?: boolean;
  num_slices?: number;
  key_slice_index?: number;
  // RNA XAI
  rna_xai?: { gene: string; ensembl_id: string; importance: number; expression: number; impact: "High Risk" | "Protective" }[] | null;
};

type Props = {
  title?: string;
  result: MriResult | null;
  loading?: boolean;
  onClose?: () => void;
  onRetry?: () => void;
  onDelete?: () => void;
  onDownload?: () => void;
  onExtraAction?: () => void;
  extraActionLabel?: string;
  openReviewForm?: boolean;
  compact?: boolean;
};

function formatConfidence(value?: number | null) {
  if (value == null) return "--";
  return `${(value * 100).toFixed(2)}%`;
}

function formatList(values?: number[] | null) {
  if (!values || values.length === 0) return "--";
  return values.map((value) => `${(value * 100).toFixed(2)}%`).join(", ");
}

function reviewStatusText(status?: string | null) {
  if (status === "needs_review") return "Cần xem xét";
  if (status === "confirmed") return "Đã xác nhận";
  if (status === "corrected") return "Đã chỉnh";
  if (status === "not_required") return "Tin cậy cao";
  return "Chưa có review";
}

export default function MriResultCard({
  title = "Kết quả MRI AI",
  result,
  loading = false,
  onClose,
  onRetry,
  onDelete,
  onDownload,
  onExtraAction,
  extraActionLabel,
  openReviewForm = false,
  compact = false,
}: Props) {
  const [previewImage, setPreviewImage] = useState<ImagePreviewState | null>(null);
  const [activeHeatmap, setActiveHeatmap] = useState<"gradcam" | "gradcam++" | "layercam">("gradcam");
  const [rating, setRating] = useState<number | null>(null);
  const [submittingRating, setSubmittingRating] = useState(false);
  const [currentSlice, setCurrentSlice] = useState<number>(result?.key_slice_index ?? 0);
  const [aiExplanation, setAiExplanation] = useState<string | null>(result?.classification_xai_explanation ?? null);
  const [explainingXai, setExplainingXai] = useState(false);
  const [explanationError, setExplanationError] = useState<string | null>(null);
  const explanationRequestRef = useRef<string | number | null>(null);
  const [expertLabel, setExpertLabel] = useState(result?.final_tumor_label || result?.tumor_label || "Glioma");
  const [expertComment, setExpertComment] = useState(result?.expert_comment || "");
  const [reviewSaving, setReviewSaving] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [showReviewForm, setShowReviewForm] = useState(openReviewForm || result?.review_status === "needs_review");
  const [reviewState, setReviewState] = useState({
    final_tumor_label: result?.final_tumor_label,
    expert_tumor_label: result?.expert_tumor_label,
    expert_comment: result?.expert_comment,
    review_required: result?.review_required,
    review_status: result?.review_status,
    review_action: result?.review_action,
  });

  // suppress unused warning — activeHeatmap is used conceptually for UX state
  void activeHeatmap;

  const getSliceUrl = (index: number) => {
    if (!result?.image_id) return "";
    return `${api.defaults.baseURL}/records/analysis/image/${result.image_id}/slice/${index}`;
  };

  const handleRating = async (star: number) => {
    if (!result?.image_id || submittingRating) return;
    setSubmittingRating(true);
    try {
      await api.post(`/records/analysis/image/${result.image_id}/validate`, {
        rating: star,
        heatmap_method: activeHeatmap,
      });
      setRating(star);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } }; message?: string };
      console.error("Failed to submit rating:", err.response?.data || err.message);
      const detail = err.response?.data?.detail || "Lỗi khi lưu đánh giá. Vui lòng thử lại.";
      alert(detail);
    } finally {
      setSubmittingRating(false);
    }
  };

  useEffect(() => {
    const imageId = result?.image_id;
    if (!imageId || !result?.classification_xai_data_url || result?.classification_xai_explanation) {
      setAiExplanation(result?.classification_xai_explanation ?? null);
      return;
    }
    if (explanationRequestRef.current === imageId) return;

    explanationRequestRef.current = imageId;
    setExplainingXai(true);
    setExplanationError(null);

    api
      .post(`/records/analysis/image/${imageId}/explain/classification`)
      .then((response) => {
        setAiExplanation(response.data?.content || "");
      })
      .catch((error: unknown) => {
        const err = error as { response?: { data?: { detail?: string } }; message?: string };
        console.error("Failed to explain classification XAI:", err.response?.data || err.message);
        setExplanationError(err.response?.data?.detail || "Không thể sinh giải thích XAI. Kiểm tra backend/RAG/Gemini key.");
      })
      .finally(() => {
        setExplainingXai(false);
      });
  }, [result?.image_id, result?.classification_xai_data_url, result?.classification_xai_explanation]);

  useEffect(() => {
    setExpertLabel(result?.final_tumor_label || result?.tumor_label || "Glioma");
    setExpertComment(result?.expert_comment || "");
    setReviewState({
      final_tumor_label: result?.final_tumor_label,
      expert_tumor_label: result?.expert_tumor_label,
      expert_comment: result?.expert_comment,
      review_required: result?.review_required,
      review_status: result?.review_status,
      review_action: result?.review_action,
    });
    setShowReviewForm(openReviewForm || result?.review_status === "needs_review");
  }, [
    result?.image_id,
    result?.final_tumor_label,
    result?.expert_tumor_label,
    result?.expert_comment,
    result?.review_required,
    result?.review_status,
    result?.review_action,
    result?.tumor_label,
    openReviewForm,
  ]);

  const submitClassificationReview = async () => {
    if (!result?.image_id || reviewSaving) return;
    setReviewSaving(true);
    setReviewError(null);
    try {
      const response = await api.post(`/records/analysis/image/${result.image_id}/classification-review`, {
        expert_tumor_label: expertLabel,
        expert_comment: expertComment,
      });
      setReviewState({
        final_tumor_label: response.data.final_tumor_label,
        expert_tumor_label: response.data.expert_tumor_label,
        expert_comment: response.data.expert_comment,
        review_required: false,
        review_status: response.data.review_status,
        review_action: response.data.review_action,
      });
      setShowReviewForm(false);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } }; message?: string };
      setReviewError(err.response?.data?.detail || err.message || "Không thể lưu xác nhận chuyên gia.");
    } finally {
      setReviewSaving(false);
    }
  };

  const isFailed = result?.status === "failed";
  const isDone = result?.status === "done" || result?.status === "completed";
  const noTumorDetected = Boolean(result?.no_tumor_detected);
  const classificationConfidence = result?.ai_confidence ?? result?.classification_confidence ?? null;
  const hasCompletedClassificationReview =
    reviewState.review_status === "confirmed" || reviewState.review_status === "corrected";
  const isLowClassificationConfidence =
    classificationConfidence != null && classificationConfidence < 0.95;
  const shouldWarnClassificationReview =
    reviewState.review_status === "needs_review" || (isLowClassificationConfidence && !hasCompletedClassificationReview);
  const shouldShowClassificationReviewForm = showReviewForm || shouldWarnClassificationReview;
  const shouldShowMultimodalPrognosis = !noTumorDetected && result?.risk_score != null;
  const multimodalRiskXaiUrl = result?.multimodal_risk_xai_data_url || result?.gradcam_heatmap_data_url || null;
  const multimodalExplanation = result?.multimodal_xai_explanation || result?.xai_explanation || null;
  const imagePanels = [
    {
      key: "bbox",
      title: "Detection (BBox)",
      src: result?.bbox_overlay_data_url,
      alt: "MRI bbox overlay",
    },
    {
      key: "mask",
      title: "Segmentation (Mask)",
      src: result?.mask_overlay_data_url,
      alt: "MRI mask overlay",
    },
    {
      key: "contour",
      title: "Tumor Contour",
      src: result?.contour_overlay_data_url,
      alt: "MRI contour overlay",
    },
  ].filter((item): item is { key: string; title: string; src: string; alt: string } => Boolean(item.src));

  return (
    <>
      <div className="rounded-2xl border border-slate-800 bg-slate-900/95 shadow-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-white">{title}</h3>
            <p className="text-xs text-slate-400">
              {loading
                ? "Đang tải kết quả từ backend..."
                : isFailed
                  ? "Pipeline MRI đã trả về lỗi."
                  : isDone
                    ? "Pipeline MRI đã chạy xong và đã lưu kết quả."
                    : "Trạng thái hiện tại của ảnh MRI."}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {onClose && (
              <button
                onClick={onClose}
                className="p-2 rounded-lg border border-slate-700 text-slate-400 hover:text-white hover:bg-slate-800 transition-all"
                title="Đóng"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>

        <div className={`p-5 ${compact ? "space-y-4" : "space-y-5"}`}>
          {loading ? (
            <div className="rounded-xl border border-slate-800 bg-slate-950/50 px-4 py-8 text-center text-slate-400">
              Đang tải kết quả...
            </div>
          ) : isFailed ? (
            <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-5">
              <div className="flex items-center gap-3 text-red-300 mb-3">
                <AlertTriangle className="h-5 w-5" />
                <span className="font-semibold">Pipeline MRI thất bại</span>
              </div>
              <p className="text-sm text-red-200 whitespace-pre-wrap">
                {result?.error_message || "Không có thông điệp lỗi chi tiết."}
              </p>
            </div>
          ) : (
            <>
              {noTumorDetected && (
                <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-4 flex items-center gap-3 text-amber-200">
                  <Search className="h-5 w-5" />
                  <span className="text-sm font-medium">
                    Không phát hiện khối u. Cần tham khảo ý kiến chuyên gia.
                  </span>
                </div>
              )}

              {result?.is_series && (
                <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-5 space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="text-[11px] uppercase tracking-widest text-slate-500">
                      Chuỗi ảnh MRI (Series Viewer) - {result.num_slices} lát cắt
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-400">Lát cắt: {currentSlice + 1} / {result.num_slices}</span>
                      {currentSlice === result.key_slice_index && (
                        <span className="px-2 py-0.5 rounded bg-teal-500/20 text-teal-400 text-[10px] font-bold border border-teal-500/30 uppercase">Key Slice</span>
                      )}
                    </div>
                  </div>

                  <div
                    className="relative aspect-square max-w-[400px] mx-auto bg-black rounded-lg overflow-hidden group border border-slate-800"
                    onWheel={(e) => {
                      if (e.deltaY > 0 && currentSlice < (result.num_slices || 0) - 1) {
                        setCurrentSlice(s => s + 1);
                      } else if (e.deltaY < 0 && currentSlice > 0) {
                        setCurrentSlice(s => s - 1);
                      }
                    }}
                  >
                    <img
                      src={getSliceUrl(currentSlice)}
                      alt={`Slice ${currentSlice}`}
                      className="w-full h-full object-contain"
                    />
                    <div className="absolute inset-x-0 bottom-0 p-4 bg-gradient-to-t from-black/80 to-transparent opacity-0 group-hover:opacity-100 transition-opacity">
                      <input
                        type="range"
                        min={0}
                        max={(result.num_slices || 1) - 1}
                        value={currentSlice}
                        onChange={(e) => setCurrentSlice(parseInt(e.target.value))}
                        className="w-full accent-teal-500 h-1 rounded-lg cursor-pointer"
                      />
                    </div>
                  </div>

                  <div className="flex justify-center gap-3">
                    <button
                      disabled={currentSlice === result.key_slice_index}
                      onClick={() => setCurrentSlice(result.key_slice_index || 0)}
                      className="text-[11px] font-bold text-teal-500 hover:text-teal-400 disabled:opacity-30 flex items-center gap-1 uppercase"
                    >
                      <RefreshCw className="h-3 w-3" /> Về lát cắt chính (Key Slice)
                    </button>
                  </div>
                </div>
              )}

              {imagePanels.length > 0 ? (
                <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                  {imagePanels.map((panel) => (
                    <button
                      key={panel.key}
                      type="button"
                      onClick={() => setPreviewImage({ title: panel.title, src: panel.src })}
                      className="rounded-xl border border-slate-800 bg-slate-950/50 p-3 text-left hover:border-teal-500/40 hover:bg-slate-950 transition-all"
                    >
                      <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-3">
                        {panel.title}
                      </div>
                      <img
                        src={panel.src}
                        alt={panel.alt}
                        className="w-full max-h-[280px] object-contain rounded-lg bg-slate-950"
                      />
                      <div className="mt-3 text-xs text-teal-400">Nhấn để xem ảnh lớn hơn</div>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="rounded-xl border border-slate-800 bg-slate-950/50 px-4 py-8 text-center text-slate-500">
                  Chưa có ảnh kết quả overlay để hiển thị.
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                  <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-2">BBox</div>
                  <div className="text-sm font-semibold text-slate-100 break-all">
                    {result?.bbox ? `[${result.bbox.join(", ")}]` : "--"}
                  </div>
                </div>

                <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                  <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-2">
                    Detection confidence
                  </div>
                  <div className="text-sm font-semibold text-slate-100">
                    {formatConfidence(result?.bbox_confidence)}
                  </div>
                </div>

                <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                  <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-2">
                    Tumor label
                  </div>
                  <div className="text-sm font-semibold text-slate-100">{noTumorDetected ? "--" : result?.tumor_label || "--"}</div>
                </div>

                <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                  <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-2">
                    Classification confidence
                  </div>
                  <div className="text-sm font-semibold text-slate-100">
                    {noTumorDetected ? "--" : formatConfidence(result?.classification_confidence)}
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-2">
                  Class probabilities
                </div>
                <div className="text-sm font-semibold text-slate-100 break-all">
                  {noTumorDetected ? "--" : formatList(result?.class_probabilities)}
                </div>
              </div>

              {result?.tumor_label && !noTumorDetected && !shouldWarnClassificationReview && !hasCompletedClassificationReview && !showReviewForm && (
                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={() => setShowReviewForm(true)}
                    className="rounded-xl border border-teal-500/30 px-4 py-2 text-sm font-semibold text-teal-200 hover:bg-teal-500/10"
                  >
                    Xác nhận phân loại
                  </button>
                </div>
              )}

              {result?.tumor_label && !noTumorDetected && (shouldWarnClassificationReview || hasCompletedClassificationReview || showReviewForm) && (
                <div
                  className={`rounded-xl border p-5 !text-[#0F172A] shadow-sm ${
                    shouldWarnClassificationReview
                      ? "border-red-200 bg-red-50"
                      : hasCompletedClassificationReview
                        ? "border-emerald-200 bg-[#ECFDF5]"
                        : "border-slate-200 bg-white"
                  }`}
                >
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <div className="text-[11px] font-semibold uppercase tracking-widest !text-[#475569]">Review phân loại</div>
                      <div className="mt-2 text-sm !text-[#1E293B]">
                        AI ban đầu: <span className="font-semibold !text-[#020617]">{result.ai_tumor_label || result.tumor_label}</span>
                        {" "}({formatConfidence(classificationConfidence)})
                      </div>
                      <div className="mt-1 text-sm !text-[#1E293B]">
                        Kết quả cuối: <span className="font-semibold !text-[#020617]">{reviewState.final_tumor_label || result.final_tumor_label || result.tumor_label}</span>
                      </div>
                      {shouldWarnClassificationReview && (
                        <div className="mt-3 rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-medium !text-[#B91C1C]">
                          Kết quả của model không chắc chắn, cần chuyên gia xem xét lại.
                        </div>
                      )}
                      {hasCompletedClassificationReview && isLowClassificationConfidence && (
                        <div className="mt-3 rounded-lg border border-emerald-200 bg-white px-3 py-2 text-sm font-medium !text-[#065F46]">
                          Mặc dù độ tin cậy &lt; 0.95 nhưng đã được chuyên gia xác nhận.
                        </div>
                      )}
                      {reviewState.review_status === "corrected" && (
                        <div className="mt-2 text-sm !text-[#065F46]">
                          Chuyên gia đã chỉnh nhãn sang <span className="font-semibold">{reviewState.final_tumor_label}</span>.
                        </div>
                      )}
                      {reviewState.expert_comment && (
                        <div className="mt-2 text-sm !text-[#1E293B]">Ghi chú chuyên gia: {reviewState.expert_comment}</div>
                      )}
                    </div>
                    <div className="flex flex-col items-start gap-2 lg:items-end">
                      <span className="w-fit rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-semibold !text-[#1E293B]">
                        {reviewStatusText(reviewState.review_status)}
                      </span>
                      {!shouldShowClassificationReviewForm && (
                        <button
                          type="button"
                          onClick={() => setShowReviewForm(true)}
                          className="rounded-xl border border-teal-300 bg-white px-4 py-2 text-sm font-semibold text-teal-700 hover:bg-teal-50"
                        >
                          {hasCompletedClassificationReview ? "Xác nhận lại" : "Xác nhận phân loại"}
                        </button>
                      )}
                    </div>
                  </div>

                  {shouldShowClassificationReviewForm && (
                    <div className="mt-5 grid gap-3 md:grid-cols-[220px_1fr_auto]">
                      <select
                        value={expertLabel}
                        onChange={(event) => setExpertLabel(event.target.value)}
                        className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-950 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-100"
                      >
                        <option value="Glioma">Glioma</option>
                        <option value="Meningioma">Meningioma</option>
                        <option value="Pituitary tumor">Pituitary tumor</option>
                      </select>
                      <input
                        value={expertComment}
                        onChange={(event) => setExpertComment(event.target.value)}
                        placeholder="Ghi chú chuyên gia..."
                        className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 placeholder:text-slate-500 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-100"
                      />
                      <button
                        onClick={submitClassificationReview}
                        disabled={reviewSaving}
                        className="rounded-xl bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-500 disabled:opacity-50"
                      >
                        {reviewSaving ? "Đang lưu..." : "Xác nhận"}
                      </button>
                    </div>
                  )}
                  {reviewError && <div className="mt-3 text-sm font-medium text-red-700">{reviewError}</div>}
                </div>
              )}

              {(result?.detection_xai_data_url || result?.segmentation_xai_data_url || result?.classification_xai_data_url || explainingXai || explanationError || aiExplanation) && (
                <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-5 space-y-5">
                  <div className="text-[11px] uppercase tracking-widest text-slate-500 flex items-center gap-2">
                    <Search className="h-4 w-4 text-teal-500" />
                    MRI Core XAI
                  </div>

                  {(result?.detection_xai_data_url || result?.segmentation_xai_data_url || result?.classification_xai_data_url) && (
                    <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                      {result.detection_xai_data_url && (
                        <button
                          type="button"
                          onClick={() => setPreviewImage({ title: "Detection XAI - ODAM", src: result.detection_xai_data_url! })}
                          className="rounded-xl border border-slate-800 bg-slate-950/50 p-3 text-left hover:border-teal-500/40 hover:bg-slate-950 transition-all"
                        >
                          <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-3">Detection / ODAM</div>
                          <img src={result.detection_xai_data_url} alt="Detection XAI" className="w-full max-h-[280px] object-contain rounded-lg bg-slate-950" />
                        </button>
                      )}
                      {result.segmentation_xai_data_url && (
                        <button
                          type="button"
                          onClick={() => setPreviewImage({ title: "Segmentation XAI - Seg-Eigen-CAM", src: result.segmentation_xai_data_url! })}
                          className="rounded-xl border border-slate-800 bg-slate-950/50 p-3 text-left hover:border-teal-500/40 hover:bg-slate-950 transition-all"
                        >
                          <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-3">Segmentation / Seg-Eigen-CAM</div>
                          <img src={result.segmentation_xai_data_url} alt="Segmentation XAI" className="w-full max-h-[280px] object-contain rounded-lg bg-slate-950" />
                        </button>
                      )}
                      {result.classification_xai_data_url && (
                        <button
                          type="button"
                          onClick={() => setPreviewImage({ title: "Classification XAI - Finer-CAM", src: result.classification_xai_data_url! })}
                          className="rounded-xl border border-slate-800 bg-slate-950/50 p-3 text-left hover:border-teal-500/40 hover:bg-slate-950 transition-all"
                        >
                          <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-3">Classification / Finer-CAM</div>
                          <img src={result.classification_xai_data_url} alt="Classification XAI" className="w-full max-h-[280px] object-contain rounded-lg bg-slate-950" />
                        </button>
                      )}
                    </div>
                  )}

                  {(explainingXai || explanationError || aiExplanation) && (
                    <div className="p-4 bg-teal-500/10 rounded-lg border border-teal-500/20">
                      <div className="text-[11px] uppercase tracking-widest text-teal-500 font-bold mb-2">Giải thích</div>
                      {explainingXai ? (
                        <div className="flex items-center gap-2 text-sm text-slate-200">
                          <Loader2 className="h-4 w-4 animate-spin text-teal-400" />
                          Đang sinh giải thích từ heatmap Finer-CAM, metadata và RAG...
                        </div>
                      ) : explanationError ? (
                        <p className="text-sm text-amber-200 leading-relaxed whitespace-pre-wrap">{explanationError}</p>
                      ) : (
                        <p className="text-sm text-slate-200 leading-relaxed whitespace-pre-wrap">{aiExplanation}</p>
                      )}
                    </div>
                  )}
                </div>
              )}

              {shouldShowMultimodalPrognosis && (
                <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-5 space-y-5">
                  <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-4 flex items-center gap-2">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-teal-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
                    Multimodal Prognosis
                  </div>

                  {/* Risk Score + Risk Group */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">Risk Score</div>
                      <div className="text-2xl font-bold text-slate-100">{result.risk_score!.toFixed(4)}</div>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">Risk Group</div>
                      <span className={`inline-block px-3 py-1.5 rounded-lg text-sm font-bold border ${
                        result.risk_group === "High" || result.risk_group === "Very High"
                          ? "bg-red-500/15 text-red-400 border-red-500/25"
                          : result.risk_group === "Medium"
                            ? "bg-amber-500/15 text-amber-400 border-amber-500/25"
                            : "bg-emerald-500/15 text-emerald-400 border-emerald-500/25"
                      }`}>
                        {result.risk_group || "--"}
                      </span>
                    </div>
                  </div>

                  {/* Multimodal prognosis risk heatmap */}
                  {(result.multimodal_gradcam_heatmap_data_url || result.multimodal_gradcam_plus_heatmap_data_url || result.multimodal_layercam_heatmap_data_url || multimodalRiskXaiUrl) && (
                    <div className="mb-6">
                      <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-3">Multimodal Risk XAI (Heatmap)</div>
                      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                        {(result.multimodal_gradcam_heatmap_data_url || multimodalRiskXaiUrl) && (
                          <button
                            type="button"
                            onClick={() => setPreviewImage({ title: "Multimodal Prognosis - Grad-CAM", src: (result.multimodal_gradcam_heatmap_data_url || multimodalRiskXaiUrl)! })}
                            className="rounded-xl border border-slate-800 bg-slate-950/50 p-3 text-left hover:border-teal-500/40 hover:bg-slate-950 transition-all w-full"
                          >
                            <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-3">Grad-CAM</div>
                            <img src={result.multimodal_gradcam_heatmap_data_url || multimodalRiskXaiUrl || undefined} alt="Multimodal Grad-CAM" className="w-full max-h-[280px] object-contain rounded-lg bg-slate-950" />
                            <div className="mt-3 text-xs text-teal-400">Nhấn để xem ảnh lớn hơn</div>
                          </button>
                        )}
                        {result.multimodal_gradcam_plus_heatmap_data_url && (
                          <button
                            type="button"
                            onClick={() => setPreviewImage({ title: "Multimodal Prognosis - Grad-CAM++", src: result.multimodal_gradcam_plus_heatmap_data_url! })}
                            className="rounded-xl border border-slate-800 bg-slate-950/50 p-3 text-left hover:border-teal-500/40 hover:bg-slate-950 transition-all w-full"
                          >
                            <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-3">Grad-CAM++</div>
                            <img src={result.multimodal_gradcam_plus_heatmap_data_url} alt="Multimodal Grad-CAM++" className="w-full max-h-[280px] object-contain rounded-lg bg-slate-950" />
                            <div className="mt-3 text-xs text-teal-400">Nhấn để xem ảnh lớn hơn</div>
                          </button>
                        )}
                        {result.multimodal_layercam_heatmap_data_url && (
                          <button
                            type="button"
                            onClick={() => setPreviewImage({ title: "Multimodal Prognosis - Layer-CAM", src: result.multimodal_layercam_heatmap_data_url! })}
                            className="rounded-xl border border-slate-800 bg-slate-950/50 p-3 text-left hover:border-teal-500/40 hover:bg-slate-950 transition-all w-full"
                          >
                            <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-3">Layer-CAM</div>
                            <img src={result.multimodal_layercam_heatmap_data_url} alt="Multimodal Layer-CAM" className="w-full max-h-[280px] object-contain rounded-lg bg-slate-950" />
                            <div className="mt-3 text-xs text-teal-400">Nhấn để xem ảnh lớn hơn</div>
                          </button>
                        )}
                      </div>
                    </div>
                  )}

                  {multimodalExplanation && (
                    <div className="p-4 bg-teal-500/10 rounded-lg border border-teal-500/20 mb-6">
                      <div className="text-[11px] uppercase tracking-widest text-teal-500 font-bold mb-2">Giải thích lâm sàng từ Multimodal Prognosis</div>
                      <p className="text-sm text-slate-200 leading-relaxed whitespace-pre-wrap">{multimodalExplanation}</p>
                    </div>
                  )}

                  {/* XAI Heatmaps — hiển thị cả 3 loại CAM cho MRI Classification */}
                  {(result.gradcam_heatmap_data_url || result.gradcam_plus_heatmap_data_url || result.layercam_heatmap_data_url) && (
                    <div className="space-y-4">
                      <div>
                        <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-3">Bản đồ nhiệt XAI Phân loại (Heatmap)</div>
                        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                          {result.gradcam_heatmap_data_url && (
                            <button
                              type="button"
                              onClick={() => setPreviewImage({ title: "Classification Grad-CAM", src: result.gradcam_heatmap_data_url! })}
                              className="rounded-xl border border-slate-800 bg-slate-950/50 p-3 text-left hover:border-teal-500/40 hover:bg-slate-950 transition-all w-full"
                            >
                              <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-3">Grad-CAM</div>
                              <img src={result.gradcam_heatmap_data_url} alt="Grad-CAM" className="w-full max-h-[280px] object-contain rounded-lg bg-slate-950" />
                              <div className="mt-3 text-xs text-teal-400">Nhấn để xem ảnh lớn hơn</div>
                            </button>
                          )}
                          {result.gradcam_plus_heatmap_data_url && (
                            <button
                              type="button"
                              onClick={() => setPreviewImage({ title: "Classification Grad-CAM++", src: result.gradcam_plus_heatmap_data_url! })}
                              className="rounded-xl border border-slate-800 bg-slate-950/50 p-3 text-left hover:border-teal-500/40 hover:bg-slate-950 transition-all w-full"
                            >
                              <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-3">Grad-CAM++</div>
                              <img src={result.gradcam_plus_heatmap_data_url} alt="Grad-CAM++" className="w-full max-h-[280px] object-contain rounded-lg bg-slate-950" />
                              <div className="mt-3 text-xs text-teal-400">Nhấn để xem ảnh lớn hơn</div>
                            </button>
                          )}
                          {result.layercam_heatmap_data_url && (
                            <button
                              type="button"
                              onClick={() => setPreviewImage({ title: "Classification Layer-CAM", src: result.layercam_heatmap_data_url! })}
                              className="rounded-xl border border-slate-800 bg-slate-950/50 p-3 text-left hover:border-teal-500/40 hover:bg-slate-950 transition-all w-full"
                            >
                              <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-3">Layer-CAM</div>
                              <img src={result.layercam_heatmap_data_url} alt="Layer-CAM" className="w-full max-h-[280px] object-contain rounded-lg bg-slate-950" />
                              <div className="mt-3 text-xs text-teal-400">Nhấn để xem ảnh lớn hơn</div>
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Clinical Plausibility Score */}
                      <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700">
                        <div className="text-[11px] text-slate-400 mb-1">Đánh giá tính hợp lý lâm sàng (Sanity Check):</div>
                        <div className="flex gap-1 items-center">
                          {[1, 2, 3, 4, 5].map((star) => (
                            <button
                              key={star}
                              onClick={() => handleRating(star)}
                              disabled={submittingRating}
                              className={`w-6 h-6 flex items-center justify-center rounded-full text-xs font-bold transition-all ${
                                rating && rating >= star
                                  ? "bg-amber-500 text-amber-950"
                                  : "bg-slate-700 text-slate-400 hover:bg-slate-600"
                              }`}
                            >
                              ★
                            </button>
                          ))}
                          <span className="text-xs text-slate-500 ml-2">{rating ? "Đã ghi nhận" : "Chưa đánh giá"}</span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Survival Curve (inline SVG) */}
                  {result.survival_curve_data && result.survival_curve_data.length > 1 && (
                    <div>
                      <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-2">Đường cong sống sót (Kaplan-Meier)</div>
                      <div className="bg-slate-900/60 rounded-lg p-3 border border-slate-800">
                        <svg viewBox="0 0 320 180" className="w-full h-auto">
                          {/* Grid */}
                          {[0.25, 0.5, 0.75, 1.0].map((v) => (
                            <g key={v}>
                              <line x1="40" y1={160 - v * 140} x2="310" y2={160 - v * 140} stroke="#334155" strokeWidth="0.5" />
                              <text x="2" y={164 - v * 140} fill="#64748b" fontSize="8">{(v * 100).toFixed(0)}%</text>
                            </g>
                          ))}
                          {/* Axes */}
                          <line x1="40" y1="160" x2="310" y2="160" stroke="#475569" strokeWidth="1" />
                          <line x1="40" y1="20" x2="40" y2="160" stroke="#475569" strokeWidth="1" />
                          {/* Fill area */}
                          {(() => {
                            const pts = result.survival_curve_data!;
                            const maxT = Math.max(...pts.map(p => p.time)) || 1;
                            let pathD = "";
                            pts.forEach((p, i) => {
                              const x = 40 + (p.time / maxT) * 270;
                              const y = 160 - p.survival_probability * 140;
                              if (i === 0) pathD += `M${x},${y}`;
                              else {
                                const prevY = 160 - pts[i - 1].survival_probability * 140;
                                pathD += ` L${x},${prevY} L${x},${y}`;
                              }
                            });
                            const lastX = 40 + (pts[pts.length - 1].time / maxT) * 270;
                            const firstX = 40 + (pts[0].time / maxT) * 270;
                            const fillD = pathD + ` L${lastX},160 L${firstX},160 Z`;
                            return (
                              <>
                                <path d={fillD} fill="rgba(20,184,166,0.15)" />
                                <path d={pathD} fill="none" stroke="#14b8a6" strokeWidth="2" />
                                {pts.map((p, i) => {
                                  const x = 40 + (p.time / maxT) * 270;
                                  const y = 160 - p.survival_probability * 140;
                                  return <circle key={i} cx={x} cy={y} r="3" fill="#14b8a6" stroke="#0f172a" strokeWidth="1" />;
                                })}
                              </>
                            );
                          })()}
                          {/* X-axis labels */}
                          {result.survival_curve_data!.map((p) => {
                            const maxT = Math.max(...result.survival_curve_data!.map(d => d.time)) || 1;
                            const x = 40 + (p.time / maxT) * 270;
                            return <text key={p.time} x={x} y="174" fill="#64748b" fontSize="7" textAnchor="middle">{p.time}m</text>;
                          })}
                          <text x="175" y="12" fill="#94a3b8" fontSize="7" textAnchor="middle">Survival Probability vs Time</text>
                        </svg>
                      </div>
                    </div>
                  )}

                  {/* Fusion Attention Weights */}
                  {result.fusion_attention && result.fusion_attention.length >= 4 && (
                    <div>
                      <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-2">Fusion Attention Weights</div>
                      <div className="space-y-2">
                        {["MRI", "WSI", "RNA", "Clinical"].map((label, i) => {
                          const val = result.fusion_attention![i] || 0;
                          const pct = val * 100;
                          const colors = ["bg-teal-500", "bg-slate-500", "bg-amber-500", "bg-violet-500"];
                          return (
                            <div key={label} className="flex items-center gap-2">
                              <span className="text-[10px] text-slate-400 w-12 text-right">{label}</span>
                              <div className="flex-1 bg-slate-800 rounded-full h-2.5">
                                <div className={`${colors[i]} h-2.5 rounded-full transition-all`} style={{ width: `${pct}%` }} />
                              </div>
                              <span className="text-[10px] text-slate-400 w-12">{(val * 100).toFixed(1)}%</span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* RNA XAI Display */}
              {result?.rna_xai && result.rna_xai.length > 0 && (
                <div className="mt-4">
                  <RnaXaiChart data={result.rna_xai} />
                </div>
              )}

              {isDone && (
                <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-4 flex items-center gap-3 text-emerald-300">
                  <CheckCircle2 className="h-5 w-5" />
                  <span className="text-sm font-medium">
                    {shouldShowMultimodalPrognosis
                      ? "Kết quả MRI & Multimodal Prognosis đã sẵn sàng."
                      : "Kết quả MRI đã sẵn sàng để xem, tải báo cáo hoặc xóa."}
                  </span>
                </div>
              )}
            </>
          )}

          <div className="flex flex-wrap gap-3">
            {onRetry && (
              <button
                onClick={onRetry}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-teal-600 text-white text-sm font-semibold transition-all flex items-center gap-2"
              >
                <RefreshCw className="h-4 w-4" /> Chạy lại MRI
              </button>
            )}
            {onDownload && !isFailed && (
              <button
                onClick={onDownload}
                className="px-4 py-2 rounded-xl border border-slate-700 hover:bg-slate-800 text-slate-200 text-sm font-semibold transition-all flex items-center gap-2"
              >
                <Download className="h-4 w-4" /> Tải báo cáo PDF
              </button>
            )}
            {onExtraAction && extraActionLabel && (
              <button
                onClick={onExtraAction}
                className="px-4 py-2 rounded-xl border border-slate-700 hover:bg-slate-800 text-slate-200 text-sm font-semibold transition-all flex items-center gap-2"
              >
                {extraActionLabel}
              </button>
            )}
            {onDelete && (
              <button
                onClick={onDelete}
                className="px-4 py-2 rounded-xl border border-red-500/20 hover:bg-red-500/10 text-red-300 text-sm font-semibold transition-all flex items-center gap-2"
              >
                <Trash2 className="h-4 w-4" /> Xóa dòng kết quả
              </button>
            )}
          </div>
        </div>
      </div>

      {previewImage && <ImagePreviewModal preview={previewImage} onClose={() => setPreviewImage(null)} />}
    </>
  );
}
