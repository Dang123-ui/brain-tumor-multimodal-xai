"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent } from "react";
import {
  ArrowLeft,
  Bot,
  BrainCircuit,
  Loader2,
  MessageSquarePlus,
  MousePointer2,
  Send,
  ShieldCheck,
  Sparkles,
  Trash2,
  ZoomIn,
} from "lucide-react";
import { ImagePreviewModal, type ImagePreviewState } from "@/components/ui/ImagePreviewModal";
import { resolveMediaUrl } from "@/lib/api";
import { neuroboardApi } from "@/lib/neuroboardApi";
import type { NeuroCaseDetail, NeuroPost, NeuroRoi, NeuroRoiComment } from "./types";

type Props = {
  postId: number;
};

type VisualItem = {
  label: string;
  url: string;
};

const CLASS_LABELS = ["Glioma", "Meningioma", "Pituitary tumor"];

function percent(value?: number | null) {
  return typeof value === "number" ? `${(value * 100).toFixed(2)}%` : "--";
}

function riskColor(group?: string | null) {
  const normalized = group?.toLowerCase();
  if (normalized === "very high" || normalized === "high") return "bg-red-50 text-red-700";
  if (normalized === "medium") return "bg-amber-50 text-amber-700";
  return "bg-emerald-50 text-emerald-700";
}

function authorInitials(username: string) {
  return username.slice(0, 2).toUpperCase();
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function roiStyle(roi: NeuroRoi) {
  return {
    left: `${roi.x * 100}%`,
    top: `${roi.y * 100}%`,
    width: `${roi.width * 100}%`,
    height: `${roi.height * 100}%`,
  };
}

function clinicalLabel(post: NeuroPost) {
  if (!post.clinical_summary) return "Chưa có dữ liệu";
  if (post.clinical_summary.no_tumor_detected) return "Không phát hiện u";
  return post.clinical_summary.ai_label || "Chưa có nhãn";
}

function buildAiPrompt(text: string) {
  return `@AI ${text}`;
}

export function NeuroBoardCaseDetail({ postId }: Props) {
  const [detail, setDetail] = useState<NeuroCaseDetail>();
  const [selectedVisualLabel, setSelectedVisualLabel] = useState<string>();
  const [draftRoi, setDraftRoi] = useState<NeuroRoi>();
  const [activeCommentId, setActiveCommentId] = useState<number>();
  const [content, setContent] = useState("");
  const [replyTo, setReplyTo] = useState<NeuroRoiComment>();
  const [currentUserId, setCurrentUserId] = useState<number>();
  const [currentUserRole, setCurrentUserRole] = useState<string>();
  const [recallingId, setRecallingId] = useState<number>();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string>();
  const [preview, setPreview] = useState<ImagePreviewState | null>(null);
  const dragStartRef = useRef<{ x: number; y: number } | null>(null);
  const imagePanelRef = useRef<HTMLDivElement>(null);

  const loadDetail = async () => {
    setLoading(true);
    setError(undefined);
    try {
      const [response, meResponse] = await Promise.all([
        neuroboardApi.getCaseDetail(postId),
        neuroboardApi.getMe().catch(() => undefined),
      ]);
      setDetail(response.data);
      setCurrentUserId(meResponse?.data.id);
      setCurrentUserRole(meResponse?.data.role);
      const firstVisual = response.data.post.clinical_media?.visuals?.[0]?.label;
      setSelectedVisualLabel((current) => current || firstVisual);
    } catch {
      setError("Không thể tải chi tiết Clinical Case.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void loadDetail(), 0);
    return () => window.clearTimeout(timeoutId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [postId]);

  const post = detail?.post;
  const visuals = useMemo<VisualItem[]>(
    () =>
      (post?.clinical_media?.visuals || []).map((visual) => ({
        ...visual,
        url: resolveMediaUrl(visual.url),
      })),
    [post],
  );
  const selectedVisual = visuals.find((item) => item.label === selectedVisualLabel) || visuals[0];
  const activeComment = detail?.roi_comments.find((comment) => comment.id === activeCommentId);
  const displayRoi = draftRoi || activeComment?.roi || undefined;
  const conversationComments = useMemo(() => detail?.roi_comments || [], [detail?.roi_comments]);
  const commentById = useMemo(() => {
    return new Map(conversationComments.map((comment) => [comment.id, comment]));
  }, [conversationComments]);

  const startRoi = (event: MouseEvent<HTMLDivElement>) => {
    if (!selectedVisual) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    const y = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height));
    dragStartRef.current = { x, y };
    setDraftRoi({ x, y, width: 0.01, height: 0.01 });
    setActiveCommentId(undefined);
  };

  const updateRoi = (event: MouseEvent<HTMLDivElement>) => {
    if (!dragStartRef.current) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const currentX = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    const currentY = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height));
    const x = Math.min(dragStartRef.current.x, currentX);
    const y = Math.min(dragStartRef.current.y, currentY);
    setDraftRoi({
      x,
      y,
      width: Math.max(0.01, Math.abs(currentX - dragStartRef.current.x)),
      height: Math.max(0.01, Math.abs(currentY - dragStartRef.current.y)),
    });
  };

  const finishRoi = () => {
    dragStartRef.current = null;
  };

  const submitRoiComment = async () => {
    if (!post || !selectedVisual || !content.trim()) return;
    const roi = draftRoi || replyTo?.roi || activeComment?.roi;
    const visualLabel = replyTo?.visual_label || activeComment?.visual_label || selectedVisual.label;
    if (!roi) {
      setError("Hãy kéo chọn một vùng ROI trên ảnh trước khi bình luận.");
      return;
    }
    setSubmitting(true);
    setError(undefined);
    try {
      const response = await neuroboardApi.createRoiComment(post.id, {
        visualLabel,
        roi,
        content,
        replyToId: replyTo?.id,
      });
      setDetail((current) =>
        current
          ? {
              ...current,
              roi_comments: [...current.roi_comments, ...response.data.items],
            }
          : current,
      );
      setContent("");
      setReplyTo(undefined);
      setDraftRoi(undefined);
      const last = response.data.items[response.data.items.length - 1];
      setActiveCommentId(last?.id);
    } catch {
      setError("Không thể gửi ROI comment.");
    } finally {
      setSubmitting(false);
    }
  };

  const focusComment = (comment: NeuroRoiComment) => {
    if (comment.is_deleted || !comment.roi) {
      setActiveCommentId(comment.id);
      setDraftRoi(undefined);
      return;
    }
    setSelectedVisualLabel(comment.visual_label || selectedVisual?.label);
    setActiveCommentId(comment.id);
    setDraftRoi(undefined);
    imagePanelRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const recallComment = async (comment: NeuroRoiComment) => {
    if (!post || comment.is_deleted) return;
    setRecallingId(comment.id);
    setError(undefined);
    try {
      const response = await neuroboardApi.recallRoiComment(post.id, comment.id);
      setDetail((current) =>
        current
          ? {
              ...current,
              roi_comments: current.roi_comments.map((item) =>
                item.id === comment.id ? response.data : item,
              ),
            }
          : current,
      );
      if (activeCommentId === comment.id) {
        setDraftRoi(undefined);
      }
      if (replyTo?.id === comment.id) {
        setReplyTo(undefined);
      }
    } catch {
      setError("Không thể thu hồi ROI comment.");
    } finally {
      setRecallingId(undefined);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center gap-2 text-[#64748B]">
        <Loader2 className="h-5 w-5 animate-spin text-[#2196F3]" />
        Đang tải chi tiết case...
      </div>
    );
  }

  if (error && !detail) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        {error}
      </div>
    );
  }

  if (!post) return null;

  return (
    <div className="-m-3 min-h-[calc(100vh-4rem)] bg-[#E3F2FD] text-[#0F172A] md:-m-6">
      <div className="sticky top-0 z-20 border-b border-[#90CAF9] bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1480px] items-center justify-between gap-4 px-5 py-3">
          <div className="flex items-center gap-3">
            <Link
              href="/neuroboard"
              className="rounded-md border border-[#90CAF9] bg-white p-2 text-[#0D47A1] hover:bg-[#E3F2FD]"
              title="Quay lại NeuroBoard"
            >
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-[#0D47A1] text-white">
              <BrainCircuit className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-[#0D47A1]">{post.anonymous_case_code}</h1>
              <p className="flex items-center gap-1 text-xs text-[#64748B]">
                <ShieldCheck className="h-3.5 w-3.5 text-[#2196F3]" />
                Clinical Case đã ẩn danh với người không phải creator
              </p>
            </div>
          </div>
          {post.is_owner && (
            <div className="rounded-md bg-[#E3F2FD] px-3 py-2 text-xs font-semibold text-[#0D47A1]">
              Hồ sơ: {post.patient_name || "Chưa có tên"} ({post.patient_external_id || post.patient_id})
            </div>
          )}
        </div>
      </div>

      <main className="mx-auto grid max-w-[1480px] gap-5 px-4 py-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <section className="min-w-0 space-y-4">
          <div className="grid grid-cols-2 gap-2 rounded-md border border-[#90CAF9] bg-white p-3 md:grid-cols-4">
            <Metric label="AI label" value={clinicalLabel(post)} />
            <Metric label="Confidence" value={percent(post.clinical_summary?.confidence)} />
            <Metric label="BBox confidence" value={percent(post.clinical_summary?.bbox_confidence)} />
            <Metric
              label="Risk score"
              value={
                typeof post.clinical_summary?.risk_score === "number"
                  ? post.clinical_summary.risk_score.toFixed(3)
                  : "--"
              }
              badgeClass={riskColor(post.clinical_summary?.risk_group)}
              badge={post.clinical_summary?.risk_group || undefined}
            />
          </div>

          {post.clinical_summary?.class_probabilities?.length ? (
            <div className="rounded-md border border-[#90CAF9] bg-white p-4">
              <h2 className="text-sm font-bold text-[#0F172A]">Class probabilities</h2>
              <div className="mt-3 space-y-2">
                {post.clinical_summary.class_probabilities.map((value, index) => (
                  <div key={`${index}-${value}`} className="grid grid-cols-[120px_minmax(0,1fr)_64px] items-center gap-3 text-xs">
                    <span className="font-semibold text-[#0F172A]">{CLASS_LABELS[index] || `Class ${index + 1}`}</span>
                    <div className="h-2 overflow-hidden rounded bg-[#E3F2FD]">
                      <div className="h-full bg-[#2196F3]" style={{ width: `${Math.max(0, Math.min(100, value * 100))}%` }} />
                    </div>
                    <span className="text-right font-semibold text-[#0D47A1]">{percent(value)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div ref={imagePanelRef} className="rounded-md border border-[#90CAF9] bg-white p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-base font-bold text-[#0F172A]">MRI / Mask / XAI Viewer</h2>
                <p className="text-xs text-[#64748B]">Kéo trực tiếp trên ảnh để chọn ROI rồi nhập comment.</p>
              </div>
              {selectedVisual && (
                <button
                  type="button"
                  onClick={() => setPreview({ title: selectedVisual.label, src: selectedVisual.url })}
                  className="inline-flex items-center gap-2 rounded-md border border-[#90CAF9] px-3 py-2 text-sm font-semibold text-[#0D47A1] hover:bg-[#E3F2FD]"
                >
                  <ZoomIn className="h-4 w-4" />
                  Phóng to ảnh
                </button>
              )}
            </div>

            <div className="mb-3 flex gap-2 overflow-x-auto pb-1">
              {visuals.map((visual) => (
                <button
                  key={visual.label}
                  type="button"
                  onClick={() => {
                    setSelectedVisualLabel(visual.label);
                    setDraftRoi(undefined);
                  }}
                  className={`shrink-0 rounded-md border px-3 py-2 text-xs font-semibold ${
                    selectedVisual?.label === visual.label
                      ? "border-[#0D47A1] bg-[#E3F2FD] text-[#0D47A1]"
                      : "border-[#E2E8F0] bg-white text-[#64748B] hover:border-[#2196F3]"
                  }`}
                >
                  {visual.label}
                </button>
              ))}
            </div>

            {selectedVisual ? (
              <div
                className="relative aspect-square max-h-[760px] overflow-hidden rounded-md bg-[#0F172A]"
                onMouseDown={startRoi}
                onMouseMove={updateRoi}
                onMouseUp={finishRoi}
                onMouseLeave={finishRoi}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={selectedVisual.url} alt={selectedVisual.label} draggable={false} className="h-full w-full select-none object-contain" />
                {displayRoi && (
                  <div
                    className={`absolute border-2 ${draftRoi ? "border-[#2196F3]" : "border-[#F59E0B]"} bg-[#2196F3]/10 shadow-[0_0_0_9999px_rgba(15,23,42,0.18)]`}
                    style={roiStyle(displayRoi)}
                  />
                )}
                <div className="absolute bottom-3 left-3 rounded bg-[#0F172A]/80 px-3 py-2 text-xs font-semibold text-white">
                  <MousePointer2 className="mr-1 inline h-3.5 w-3.5" />
                  {selectedVisual.label}
                </div>
              </div>
            ) : (
              <div className="rounded-md border border-dashed border-[#90CAF9] p-8 text-center text-sm text-[#64748B]">
                Chưa có ảnh MRI/XAI cho case này.
              </div>
            )}
          </div>
        </section>

        <aside className="space-y-4">
          <div className="rounded-md border border-[#90CAF9] bg-white p-4">
            <h2 className="text-sm font-bold text-[#0F172A]">ROI comment</h2>
            {replyTo && (
              <div className="mt-3 rounded-md border border-[#90CAF9] bg-[#E3F2FD] px-3 py-2 text-xs text-[#0D47A1]">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-bold">Đang trả lời @{replyTo.author.username}</p>
                    <p className="mt-1 line-clamp-2 text-[#334155]">{replyTo.content}</p>
                    {replyTo.roi && (
                      <p className="mt-1 text-[11px] text-[#64748B]">
                        {replyTo.visual_label} - ROI x {(replyTo.roi.x * 100).toFixed(1)}%, y{" "}
                        {(replyTo.roi.y * 100).toFixed(1)}%
                      </p>
                    )}
                  </div>
                  <button type="button" onClick={() => setReplyTo(undefined)} className="shrink-0 font-bold hover:underline">
                    Hủy
                  </button>
                </div>
              </div>
            )}
            {!replyTo && !draftRoi && !activeComment && (
              <p className="mt-3 rounded-md bg-[#F6FAFD] px-3 py-2 text-xs text-[#64748B]">
                Kéo chọn ROI trên ảnh để tạo comment mới, hoặc bấm Reply dưới một comment để trả lời đúng thread đó.
              </p>
            )}
            <textarea
              value={content}
              onChange={(event) => setContent(event.target.value)}
              rows={4}
              placeholder="Nhập comment ROI, hoặc dùng @AI để hỏi agent trong case..."
              className="mt-3 w-full resize-none rounded-md border border-[#90CAF9] bg-white px-3 py-2 text-sm text-[#0F172A] outline-none placeholder:text-[#64748B] focus:border-[#2196F3] focus:ring-2 focus:ring-[#90CAF9]/50"
            />
            <div className="mt-3 flex flex-wrap gap-2">
              {[
                "tóm tắt case",
                "giải thích confidence",
                "so sánh mask với heatmap",
                "phân tích timeline liên quan",
              ].map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => setContent(buildAiPrompt(prompt))}
                  className="rounded border border-[#E2E8F0] px-2 py-1 text-xs font-semibold text-[#0D47A1] hover:bg-[#E3F2FD]"
                >
                  <Sparkles className="mr-1 inline h-3 w-3" />
                  {prompt}
                </button>
              ))}
            </div>
            {error && <p className="mt-3 text-xs text-red-600">{error}</p>}
            <button
              type="button"
              disabled={submitting || !content.trim()}
              onClick={() => void submitRoiComment()}
              className="mt-3 flex w-full items-center justify-center gap-2 rounded-md bg-[#2196F3] px-4 py-2 text-sm font-semibold text-white hover:bg-[#0D47A1] disabled:cursor-not-allowed disabled:bg-[#CBD5E1]"
            >
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              Gửi ROI comment
            </button>
          </div>

          <div className="rounded-md border border-[#90CAF9] bg-white">
            <div className="border-b border-[#E3F2FD] px-4 py-3">
              <h2 className="flex items-center gap-2 text-sm font-bold text-[#0F172A]">
                <MessageSquarePlus className="h-4 w-4 text-[#2196F3]" />
                Trao đổi ROI trong case
              </h2>
            </div>
            <div className="max-h-[720px] space-y-3 overflow-y-auto bg-[#EEF6FF] p-4">
              {conversationComments.length === 0 && (
                <p className="rounded-md bg-[#F6FAFD] px-3 py-4 text-sm text-[#64748B]">
                  Chưa có ROI comment. Kéo chọn vùng trên ảnh để bắt đầu.
                </p>
              )}
              {conversationComments.map((comment) => {
                const parent = comment.reply_to_id ? commentById.get(comment.reply_to_id) : undefined;
                const canManageThread = post.is_owner || currentUserRole === "admin";
                const canRecall =
                  !comment.is_deleted &&
                  (canManageThread ||
                    comment.author.id === currentUserId ||
                    (comment.is_ai && parent?.author.id === currentUserId));
                return (
                  <RoiCommentBubble
                    key={comment.id}
                    comment={comment}
                    parent={parent}
                    active={activeCommentId === comment.id}
                    isMine={currentUserId !== undefined && comment.author.id === currentUserId}
                    canRecall={canRecall}
                    recalling={recallingId === comment.id}
                    onFocus={() => focusComment(comment)}
                    onReply={() => {
                      focusComment(comment);
                      setReplyTo(comment);
                    }}
                    onRecall={() => void recallComment(comment)}
                  />
                );
              })}
            </div>
          </div>
        </aside>
      </main>

      {preview && <ImagePreviewModal preview={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}

function Metric({
  label,
  value,
  badge,
  badgeClass,
}: {
  label: string;
  value: string;
  badge?: string;
  badgeClass?: string;
}) {
  return (
    <div className="rounded-md bg-[#F6FAFD] p-3">
      <p className="text-[10px] font-semibold uppercase text-[#64748B]">{label}</p>
      <p className="mt-1 text-sm font-bold text-[#0F172A]">{value}</p>
      {badge && <span className={`mt-2 inline-block rounded px-2 py-0.5 text-xs font-bold ${badgeClass}`}>{badge}</span>}
    </div>
  );
}

function RoiCommentBubble({
  comment,
  active,
  parent,
  isMine,
  canRecall,
  recalling,
  onFocus,
  onReply,
  onRecall,
}: {
  comment: NeuroRoiComment;
  active: boolean;
  parent?: NeuroRoiComment;
  isMine: boolean;
  canRecall: boolean;
  recalling: boolean;
  onFocus: () => void;
  onReply: () => void;
  onRecall: () => void;
}) {
  const hasRoi = Boolean(comment.roi && !comment.is_deleted);
  const canReply = !comment.is_ai && !comment.is_deleted && hasRoi;
  const bubbleClass = comment.is_deleted
    ? "border-[#CBD5E1] bg-white text-[#0F172A]"
    : isMine
      ? "border-[#90CAF9] bg-[#DBEAFF] text-[#0F172A]"
      : "border-[#E2E8F0] bg-white text-[#0F172A]";

  return (
    <div className={"flex items-end gap-2 " + (isMine ? "justify-end" : "justify-start")}>
      {!isMine && (
        <div className={"flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold " + (comment.is_ai ? "bg-[#0D47A1] text-white" : "bg-white text-[#0D47A1] ring-1 ring-[#90CAF9]")}>
          {comment.is_ai ? <Bot className="h-4 w-4" /> : authorInitials(comment.author.username)}
        </div>
      )}
      <div className={"group flex max-w-[88%] flex-col " + (isMine ? "items-end" : "items-start")}>
        <div className="mb-1 flex items-center gap-2 px-1 text-[11px] text-[#64748B]">
          <span className="font-semibold text-[#0F172A]">{comment.author.username}</span>
          <span>{formatTime(comment.created_at)}</span>
        </div>
        <button
          type="button"
          onClick={hasRoi ? onFocus : undefined}
          className={
            "w-full rounded-2xl border px-3 py-2 text-left shadow-sm transition " +
            (active && hasRoi ? "ring-2 ring-[#F59E0B] " : "") +
            bubbleClass +
            (hasRoi ? " hover:border-[#2196F3]" : " cursor-default")
          }
        >
          {parent && (
            <div className={"mb-2 rounded-md border-l-4 px-3 py-2 text-xs " + (parent.is_deleted ? "border-[#94A3B8] bg-white/70 text-[#0F172A]" : "border-[#2196F3] bg-white/70 text-[#64748B]")}>
              <p className="font-bold text-[#0D47A1]">Trả lời @{parent.author.username}</p>
              <p className={"mt-1 line-clamp-2 " + (parent.is_deleted ? "font-semibold text-[#0F172A]" : "")}>
                {parent.is_deleted ? "Đã thu hồi" : parent.content}
              </p>
            </div>
          )}
          {comment.is_deleted ? (
            <p className="text-sm font-semibold text-[#0F172A]">Đã thu hồi</p>
          ) : (
            <>
              {comment.visual_label && (
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-[#0D47A1]">
                  {comment.visual_label}
                </p>
              )}
              <p className="whitespace-pre-wrap text-sm leading-5">{comment.content}</p>
              {comment.roi && (
                <p className="mt-2 text-[11px] text-[#64748B]">
                  ROI x {(comment.roi.x * 100).toFixed(1)}%, y {(comment.roi.y * 100).toFixed(1)}%
                </p>
              )}
            </>
          )}
        </button>
        {(canReply || canRecall) && (
          <div className={"mt-1 flex items-center gap-3 px-1 text-[11px] font-semibold " + (isMine ? "justify-end" : "justify-start")}>
            {canReply && (
              <button type="button" onClick={onReply} className="text-[#0D47A1] hover:underline">
                Reply
              </button>
            )}
            {canRecall && (
              <button
                type="button"
                onClick={onRecall}
                disabled={recalling}
                className="inline-flex items-center gap-1 text-[#64748B] hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Trash2 className="h-3 w-3" />
                Thu hồi
              </button>
            )}
          </div>
        )}
      </div>
      {isMine && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#0D47A1] text-xs font-bold text-white">
          {authorInitials(comment.author.username)}
        </div>
      )}
    </div>
  );
}
