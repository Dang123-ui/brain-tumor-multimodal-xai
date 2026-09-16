"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  Bookmark,
  BrainCircuit,
  CheckCircle2,
  ExternalLink,
  Loader2,
  MoreHorizontal,
  ShieldCheck,
  Stethoscope,
  Trash2,
} from "lucide-react";
import {
  ImagePreviewModal,
  type ImagePreviewState,
} from "@/components/ui/ImagePreviewModal";
import { neuroboardApi } from "@/lib/neuroboardApi";
import { NeuroBoardComments } from "./NeuroBoardComments";
import type { NeuroPost } from "./types";

type Props = {
  post: NeuroPost;
  onUpdated: (post: NeuroPost) => void;
  onDeleted: (postId: number) => void;
};

const CONTENT_PREVIEW_LENGTH = 420;
const MAX_VISIBLE_GALLERY_ITEMS = 5;

function formatDate(value: string) {
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function avatarText(username: string) {
  return username.slice(0, 2).toUpperCase();
}

function riskColor(group?: string | null) {
  const normalized = group?.toLowerCase();
  if (normalized === "very high" || normalized === "high") return "text-red-700 bg-red-50";
  if (normalized === "medium") return "text-amber-700 bg-amber-50";
  return "text-emerald-700 bg-emerald-50";
}

function cleanMarkdown(value: string) {
  return value
    .replace(/\[\*\*(.*?)\*\*\]\((.*?)\)/g, "$2")
    .replace(/\[(.*?)\]\((.*?)\)/g, "$2")
    .replace(/\*\*/g, "");
}

function renderLinkedText(value: string) {
  return cleanMarkdown(value).split(/(https?:\/\/[^\s]+)/g).map((part, index) => {
    if (/^https?:\/\//.test(part)) {
      return (
        <a
          key={`${part}-${index}`}
          href={part}
          target="_blank"
          rel="noreferrer"
          className="font-semibold text-[#0D47A1] underline decoration-[#90CAF9] underline-offset-2"
        >
          {part}
        </a>
      );
    }
    return <span key={`${part}-${index}`}>{part}</span>;
  });
}

function galleryTileClass(count: number, index: number) {
  if (count >= 5) {
    return index < 2 ? "col-span-3 aspect-[4/3]" : "col-span-2 aspect-[4/3]";
  }
  if (count === 4) return "col-span-3 aspect-video";
  if (count === 3) return index === 0 ? "col-span-6 aspect-video" : "col-span-3 aspect-video";
  return "col-span-3 aspect-video";
}

export function NeuroBoardPost({ post, onUpdated, onDeleted }: Props) {
  const [commentsOpen, setCommentsOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [galleryOpen, setGalleryOpen] = useState(false);
  const [busyAction, setBusyAction] = useState<string>();
  const [preview, setPreview] = useState<ImagePreviewState | null>(null);
  const [error, setError] = useState<string>();
  const [failedMedia, setFailedMedia] = useState<Set<string>>(() => new Set());
  const [expanded, setExpanded] = useState(false);

  const cleanedContent = post.content ? cleanMarkdown(post.content) : "";
  const shouldClampContent = cleanedContent.length > CONTENT_PREVIEW_LENGTH;
  const displayedContent =
    shouldClampContent && !expanded
      ? `${cleanedContent.slice(0, CONTENT_PREVIEW_LENGTH).trimEnd()}...`
      : cleanedContent;

  const clinicalVisuals = useMemo(() => {
    const media = post.clinical_media;
    if (!media) return [];
    if (media.visuals?.length) return media.visuals;
    return media.mri_url ? [{ label: "MRI", url: media.mri_url }] : [];
  }, [post.clinical_media]);

  const visibleAttachments = post.attachments.filter(
    (attachment) => attachment.url && !failedMedia.has(attachment.url),
  );
  const visibleClinicalVisuals = clinicalVisuals.filter(
    (visual) => visual.url && !failedMedia.has(visual.url),
  );
  const galleryItems = [
    ...visibleAttachments.map((attachment) => ({
      key: `attachment-${attachment.id}`,
      title: attachment.original_name || "Ảnh bài đăng",
      url: attachment.url!,
      label: attachment.original_name || undefined,
    })),
    ...visibleClinicalVisuals.map((visual) => ({
      key: `clinical-${visual.label}-${visual.url}`,
      title: `${post.anonymous_case_code} - ${visual.label}`,
      url: visual.url,
      label: visual.label,
    })),
  ];
  const visibleGalleryItems = galleryItems.slice(0, MAX_VISIBLE_GALLERY_ITEMS);
  const hiddenGalleryCount = Math.max(0, galleryItems.length - visibleGalleryItems.length);

  const hideUnavailableMedia = (url: string) => {
    setFailedMedia((current) => {
      if (current.has(url)) return current;
      const next = new Set(current);
      next.add(url);
      return next;
    });
  };

  const updateReaction = async () => {
    setBusyAction("reaction");
    setError(undefined);
    try {
      const response = post.viewer_reaction
        ? await neuroboardApi.removeReaction(post.id)
        : await neuroboardApi.setReaction(post.id, "support");
      onUpdated(response.data);
    } catch {
      setError("Không thể cập nhật cảm xúc.");
    } finally {
      setBusyAction(undefined);
    }
  };

  const updateSaved = async () => {
    setBusyAction("save");
    setError(undefined);
    try {
      const response = post.viewer_saved
        ? await neuroboardApi.unsavePost(post.id)
        : await neuroboardApi.savePost(post.id);
      onUpdated(response.data);
    } catch {
      setError("Không thể cập nhật bài đã lưu.");
    } finally {
      setBusyAction(undefined);
    }
  };

  const deletePost = async () => {
    setBusyAction("delete");
    try {
      await neuroboardApi.deletePost(post.id);
      onDeleted(post.id);
    } catch {
      setError("Không thể xóa bài đăng.");
      setDeleteOpen(false);
    } finally {
      setBusyAction(undefined);
    }
  };

  return (
    <article className="overflow-hidden rounded-md border border-[#90CAF9] bg-white shadow-sm">
      <header className="flex items-start justify-between gap-3 p-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#E3F2FD] text-xs font-bold text-[#0D47A1] ring-1 ring-[#90CAF9]">
            {avatarText(post.author.username)}
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="truncate text-sm font-semibold text-[#0F172A]">
                {post.author.username}
              </h2>
              {post.post_type === "clinical_case" && (
                <span className="inline-flex items-center gap-1 rounded bg-[#E3F2FD] px-2 py-0.5 text-[11px] font-semibold text-[#0D47A1]">
                  <Stethoscope className="h-3 w-3" />
                  Clinical Case
                </span>
              )}
            </div>
            <div className="mt-0.5 flex items-center gap-2 text-xs text-[#64748B]">
              <span>{formatDate(post.created_at)}</span>
              {post.post_type === "clinical_case" && (
                <span className="inline-flex items-center gap-1 text-[#2196F3]">
                  <ShieldCheck className="h-3.5 w-3.5" />
                  Đã ẩn danh
                </span>
              )}
            </div>
          </div>
        </div>

        {post.is_owner && (
          <div className="relative">
            <button
              type="button"
              onClick={() => setMenuOpen((current) => !current)}
              className="rounded-full p-2 text-[#64748B] hover:bg-[#E3F2FD]"
              title="Tùy chọn bài đăng"
            >
              <MoreHorizontal className="h-5 w-5" />
            </button>
            {menuOpen && (
              <div className="absolute right-0 top-10 z-10 w-40 rounded-md border border-[#90CAF9] bg-white p-1 shadow-lg">
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    setDeleteOpen(true);
                  }}
                  className="flex w-full items-center gap-2 rounded px-3 py-2 text-sm text-red-600 hover:bg-red-50"
                >
                  <Trash2 className="h-4 w-4" />
                  Xóa bài đăng
                </button>
              </div>
            )}
          </div>
        )}
      </header>

      {post.post_type === "clinical_case" && (
        <div className="mx-4 mb-3 flex flex-wrap items-center justify-between gap-2 rounded-md border border-[#90CAF9] bg-[#E3F2FD] px-3 py-2">
          <div className="flex items-center gap-2 text-sm font-semibold text-[#0D47A1]">
            <BrainCircuit className="h-4 w-4 text-[#2196F3]" />
            {post.anonymous_case_code}
          </div>
          {post.is_owner && (
            <span className="text-xs text-[#0D47A1]">
              Hồ sơ: {post.patient_name || "Chưa có tên"} ({post.patient_external_id || post.patient_id})
            </span>
          )}
          <Link
            href={`/neuroboard/${post.id}`}
            className="inline-flex items-center gap-1 rounded border border-[#90CAF9] bg-white px-2.5 py-1 text-xs font-semibold text-[#0D47A1] hover:bg-[#F6FAFD]"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Mở chi tiết case
          </Link>
        </div>
      )}

      {cleanedContent && (
        <div className="px-4 pb-4">
          <p className="whitespace-pre-wrap text-[15px] leading-6 text-[#0F172A]">
            {renderLinkedText(displayedContent)}
          </p>
          {shouldClampContent && (
            <button
              type="button"
              onClick={() => setExpanded((current) => !current)}
              className="mt-2 text-sm font-semibold text-[#0D47A1] hover:underline"
            >
              {expanded ? "See less" : "See more"}
            </button>
          )}
        </div>
      )}

      {post.clinical_summary && (
        <div className="grid grid-cols-2 border-y border-[#E3F2FD] bg-[#F6FAFD] sm:grid-cols-4">
          <div className="border-r border-[#E3F2FD] p-3">
            <p className="text-[10px] font-semibold uppercase text-[#64748B]">AI label</p>
            <p className="mt-1 text-sm font-bold text-[#0F172A]">
              {post.clinical_summary.no_tumor_detected
                ? "Không phát hiện u"
                : post.clinical_summary.ai_label || "Chưa có dữ liệu"}
            </p>
          </div>
          <div className="p-3 sm:border-r sm:border-[#E3F2FD]">
            <p className="text-[10px] font-semibold uppercase text-[#64748B]">Confidence</p>
            <p className="mt-1 text-sm font-bold text-[#0F172A]">
              {typeof post.clinical_summary.confidence === "number"
                ? `${(post.clinical_summary.confidence * 100).toFixed(2)}%`
                : "--"}
            </p>
          </div>
          <div className="border-r border-t border-[#E3F2FD] p-3 sm:border-t-0">
            <p className="text-[10px] font-semibold uppercase text-[#64748B]">Risk score</p>
            <p className="mt-1 text-sm font-bold text-[#0F172A]">
              {typeof post.clinical_summary.risk_score === "number"
                ? post.clinical_summary.risk_score.toFixed(3)
                : "--"}
            </p>
          </div>
          <div className="border-t border-[#E3F2FD] p-3 sm:border-t-0">
            <p className="text-[10px] font-semibold uppercase text-[#64748B]">Risk group</p>
            {post.clinical_summary.risk_group ? (
              <span className={`mt-1 inline-block rounded px-2 py-0.5 text-xs font-bold ${riskColor(post.clinical_summary.risk_group)}`}>
                {post.clinical_summary.risk_group}
              </span>
            ) : (
              <p className="mt-1 text-sm font-bold text-[#0F172A]">--</p>
            )}
          </div>
        </div>
      )}

      {galleryItems.length > 0 && (
        <div
          className={
            galleryItems.length === 1
              ? "bg-[#E3F2FD]"
              : "grid grid-cols-6 gap-1 bg-[#E3F2FD] p-1"
          }
        >
          {visibleGalleryItems.map((item, index) => {
            const showMoreOverlay = hiddenGalleryCount > 0 && index === visibleGalleryItems.length - 1;
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => {
                  if (showMoreOverlay) {
                    setGalleryOpen(true);
                    return;
                  }
                  setPreview({ title: item.title, src: item.url });
                }}
                className={
                  galleryItems.length === 1
                    ? "group relative block w-full overflow-hidden bg-[#0F172A]"
                    : `group relative ${galleryTileClass(visibleGalleryItems.length, index)} overflow-hidden bg-[#0F172A]`
                }
                title={showMoreOverlay ? "Xem tất cả ảnh" : "Nhấp để phóng to"}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={item.url}
                  alt={item.title}
                  className={
                    galleryItems.length === 1
                      ? "mx-auto max-h-[760px] w-full object-contain transition group-hover:opacity-90"
                      : "h-full w-full object-contain transition group-hover:opacity-90"
                  }
                  onError={() => hideUnavailableMedia(item.url)}
                />
                {item.label && galleryItems.length > 1 && (
                  <span className="absolute bottom-2 left-2 rounded bg-[#0F172A]/80 px-2 py-1 text-[10px] font-semibold uppercase text-white">
                    {item.label}
                  </span>
                )}
                {showMoreOverlay && (
                  <span className="absolute inset-0 flex items-center justify-center bg-[#0F172A]/60 text-4xl font-bold text-white">
                    +{hiddenGalleryCount}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      <div className="flex items-center justify-between px-4 py-2 text-xs text-[#64748B]">
        <span>{post.reaction_count > 0 ? `${post.reaction_count} lượt đồng thuận` : "Chưa có cảm xúc"}</span>
        <button type="button" onClick={() => setCommentsOpen(true)} className="hover:underline">
          {post.comment_count} bình luận
        </button>
      </div>

      <div className="grid grid-cols-3 border-t border-[#E3F2FD] px-2 py-1">
        <label className="flex cursor-pointer items-center justify-center gap-2 rounded-md py-2 text-sm font-semibold text-[#64748B] hover:bg-[#E3F2FD] has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-70">
          {busyAction === "reaction" ? (
            <Loader2 className="h-4 w-4 animate-spin text-[#ff5b89]" />
          ) : (
            <span className="heart-container" title="Like">
              <input
                type="checkbox"
                className="checkbox"
                checked={Boolean(post.viewer_reaction)}
                disabled={busyAction === "reaction"}
                onChange={() => void updateReaction()}
                aria-label="Hữu ích"
              />
              <span className="svg-container">
                <svg viewBox="0 0 24 24" className="svg-outline" xmlns="http://www.w3.org/2000/svg">
                  <path d="M17.5,1.917a6.4,6.4,0,0,0-5.5,3.3,6.4,6.4,0,0,0-5.5-3.3A6.8,6.8,0,0,0,0,8.967c0,4.547,4.786,9.513,8.8,12.88a4.974,4.974,0,0,0,6.4,0C19.214,18.48,24,13.514,24,8.967A6.8,6.8,0,0,0,17.5,1.917Zm-3.585,18.4a2.973,2.973,0,0,1-3.83,0C4.947,16.006,2,11.87,2,8.967a4.8,4.8,0,0,1,4.5-5.05A4.8,4.8,0,0,1,11,8.967a1,1,0,0,0,2,0,4.8,4.8,0,0,1,4.5-5.05A4.8,4.8,0,0,1,22,8.967C22,11.87,19.053,16.006,13.915,20.313Z" />
                </svg>
                <svg viewBox="0 0 24 24" className="svg-filled" xmlns="http://www.w3.org/2000/svg">
                  <path d="M17.5,1.917a6.4,6.4,0,0,0-5.5,3.3,6.4,6.4,0,0,0-5.5-3.3A6.8,6.8,0,0,0,0,8.967c0,4.547,4.786,9.513,8.8,12.88a4.974,4.974,0,0,0,6.4,0C19.214,18.48,24,13.514,24,8.967A6.8,6.8,0,0,0,17.5,1.917Z" />
                </svg>
                <svg className="svg-celebrate" width="100" height="100" xmlns="http://www.w3.org/2000/svg">
                  <polygon points="10,10 20,20" />
                  <polygon points="10,50 20,50" />
                  <polygon points="20,80 30,70" />
                  <polygon points="90,10 80,20" />
                  <polygon points="90,50 80,50" />
                  <polygon points="80,80 70,70" />
                </svg>
              </span>
            </span>
          )}
          Hữu ích
        </label>
        <div className="group relative flex items-center justify-center rounded-md py-1 hover:bg-[#E3F2FD]">
          <button
            type="button"
            onClick={() => setCommentsOpen((current) => !current)}
            className="text-[#64748B]"
            aria-label="Bình luận"
          >
          <svg
            strokeLinejoin="round"
            strokeLinecap="round"
            stroke="currentColor"
            strokeWidth="2"
            viewBox="0 0 24 24"
            height="44"
            width="44"
            xmlns="http://www.w3.org/2000/svg"
            className="w-8 duration-200 hover:scale-125 hover:stroke-blue-500"
            fill="none"
          >
            <path fill="none" d="M0 0h24v24H0z" stroke="none" />
            <path d="M8 9h8" />
            <path d="M8 13h6" />
            <path d="M18 4a3 3 0 0 1 3 3v8a3 3 0 0 1 -3 3h-5l-5 3v-3h-2a3 3 0 0 1 -3 -3v-8a3 3 0 0 1 3 -3h12z" />
          </svg>
          </button>
          <span className="absolute -top-14 left-[50%] z-20 origin-left -translate-x-[50%] scale-0 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-bold text-[#0F172A] shadow-md transition-all duration-300 ease-in-out group-hover:scale-100">
            Comment
          </span>
        </div>
        <button
          type="button"
          onClick={() => void updateSaved()}
          disabled={busyAction === "save"}
          className={`flex items-center justify-center gap-2 rounded-md py-2 text-sm font-semibold hover:bg-[#E3F2FD] ${
            post.viewer_saved ? "text-[#0D47A1]" : "text-[#64748B]"
          }`}
        >
          {busyAction === "save" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Bookmark className={`h-4 w-4 ${post.viewer_saved ? "fill-current" : ""}`} />}
          Lưu
        </button>
      </div>

      {error && <p className="border-t border-red-100 bg-red-50 px-4 py-2 text-xs text-red-600">{error}</p>}
      {commentsOpen && (
        <NeuroBoardComments
          postId={post.id}
          postAuthor={post.author.username}
          onClose={() => setCommentsOpen(false)}
          onCountChanged={(delta) => onUpdated({ ...post, comment_count: post.comment_count + delta })}
        />
      )}

      {deleteOpen && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-[#0F172A]/45 p-4">
          <div className="w-full max-w-sm rounded-md bg-white p-5 shadow-2xl">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-50 text-red-600">
              <Trash2 className="h-5 w-5" />
            </div>
            <h3 className="mt-4 text-base font-bold text-[#0F172A]">Xóa bài đăng?</h3>
            <p className="mt-2 text-sm leading-6 text-[#64748B]">
              Bài đăng sẽ bị ẩn khỏi NeuroBoard cùng các tương tác liên quan.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setDeleteOpen(false)} className="rounded-md border border-[#E2E8F0] px-4 py-2 text-sm font-semibold text-[#0F172A]">
                Hủy
              </button>
              <button type="button" onClick={() => void deletePost()} className="flex items-center gap-2 rounded-md bg-red-600 px-4 py-2 text-sm font-semibold text-white">
                {busyAction === "delete" ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                Xác nhận xóa
              </button>
            </div>
          </div>
        </div>
      )}
      {galleryOpen && (
        <div
          className="fixed inset-0 z-[90] flex items-center justify-center bg-[#0F172A]/60 p-3"
          role="dialog"
          aria-modal="true"
          onMouseDown={() => setGalleryOpen(false)}
        >
          <div
            className="flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-md bg-white shadow-2xl"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-[#E2E8F0] px-4 py-3">
              <div>
                <h3 className="text-sm font-bold text-[#0F172A]">
                  {post.post_type === "clinical_case" ? post.anonymous_case_code : post.author.username} - Tất cả ảnh
                </h3>
                <p className="text-xs text-[#64748B]">{galleryItems.length} ảnh trong bài đăng</p>
              </div>
              <button
                type="button"
                onClick={() => setGalleryOpen(false)}
                className="rounded-full px-3 py-1.5 text-xl leading-none text-[#64748B] hover:bg-[#E3F2FD] hover:text-[#0F172A]"
                aria-label="Đóng danh sách ảnh"
              >
                ×
              </button>
            </div>
            <div className="max-h-[82vh] space-y-4 overflow-y-auto bg-[#F6FAFD] p-4">
              {galleryItems.map((item, index) => (
                <figure key={item.key} className="overflow-hidden rounded-md border border-[#E2E8F0] bg-white">
                  <figcaption className="flex items-center justify-between border-b border-[#E2E8F0] px-3 py-2">
                    <span className="text-xs font-bold uppercase tracking-wide text-[#0D47A1]">
                      {item.label || item.title}
                    </span>
                    <span className="text-xs text-[#64748B]">
                      {index + 1}/{galleryItems.length}
                    </span>
                  </figcaption>
                  <button
                    type="button"
                    onClick={() => setPreview({ title: item.title, src: item.url })}
                    className="block w-full bg-[#0F172A]"
                    title="Nhấp để phóng to"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={item.url}
                      alt={item.title}
                      className="mx-auto max-h-[78vh] w-full object-contain"
                      onError={() => hideUnavailableMedia(item.url)}
                    />
                  </button>
                </figure>
              ))}
            </div>
          </div>
        </div>
      )}
      {preview && <ImagePreviewModal preview={preview} onClose={() => setPreview(null)} />}
    </article>
  );
}
