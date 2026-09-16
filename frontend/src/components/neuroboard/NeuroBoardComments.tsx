"use client";

import { useCallback, useEffect, useState } from "react";
import { CornerDownRight, Loader2, Send, X } from "lucide-react";
import { neuroboardApi } from "@/lib/neuroboardApi";
import type { NeuroComment } from "./types";

type Props = {
  postId: number;
  postAuthor: string;
  onClose: () => void;
  onCountChanged: (delta: number) => void;
};

function formatTime(value: string) {
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function avatarText(username: string) {
  return username.slice(0, 2).toUpperCase();
}

export function NeuroBoardComments({ postId, postAuthor, onClose, onCountChanged }: Props) {
  const [comments, setComments] = useState<NeuroComment[]>([]);
  const [content, setContent] = useState("");
  const [replyTo, setReplyTo] = useState<NeuroComment>();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string>();

  const loadComments = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const response = await neuroboardApi.getComments(postId);
      setComments(response.data.items || []);
    } catch {
      setError("Không thể tải bình luận.");
    } finally {
      setLoading(false);
    }
  }, [postId]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void loadComments(), 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadComments]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const submit = async () => {
    if (!content.trim() || submitting) return;
    setSubmitting(true);
    setError(undefined);
    try {
      await neuroboardApi.createComment(postId, {
        content,
        parentId: replyTo?.id,
      });
      setContent("");
      setReplyTo(undefined);
      onCountChanged(1);
      await loadComments();
    } catch {
      setError("Không thể gửi bình luận.");
    } finally {
      setSubmitting(false);
    }
  };

  const renderComment = (comment: NeuroComment, nested = false) => (
    <div key={comment.id} className={nested ? "ml-10 mt-2" : "mt-4"}>
      <div className="flex items-start gap-2">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#E3F2FD] text-[11px] font-bold text-[#0D47A1] ring-1 ring-[#90CAF9]">
          {avatarText(comment.author.username)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="inline-block max-w-full rounded-2xl bg-[#F1F5F9] px-3 py-2">
            <p className="text-xs font-semibold text-[#0F172A]">{comment.author.username}</p>
            <p className="mt-0.5 whitespace-pre-wrap break-words text-sm text-[#0F172A]">
              {comment.content}
            </p>
          </div>
          <div className="mt-1 flex items-center gap-3 px-2 text-[11px] text-[#64748B]">
            <span>{formatTime(comment.created_at)}</span>
            {!nested && (
              <button
                type="button"
                onClick={() => setReplyTo(comment)}
                className="font-semibold hover:text-[#0D47A1]"
              >
                Trả lời
              </button>
            )}
          </div>
        </div>
      </div>
      {comment.replies?.map((reply) => renderComment(reply, true))}
    </div>
  );

  return (
    <div
      className="fixed inset-0 z-[75] flex items-center justify-center bg-[#0F172A]/35 p-3 backdrop-blur-[2px]"
      onMouseDown={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-md bg-white shadow-2xl"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="relative border-b border-[#E2E8F0] px-14 py-4 text-center">
          <h3 className="truncate text-xl font-bold text-[#0F172A]">
            {postAuthor}&apos;s Post
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="absolute right-4 top-3 flex h-10 w-10 items-center justify-center rounded-full bg-[#F1F5F9] text-[#0F172A] hover:bg-[#E2E8F0]"
            title="Đóng bình luận"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="min-h-[360px] flex-1 overflow-y-auto px-4 pb-4">
          {loading ? (
            <div className="flex items-center gap-2 py-8 text-sm text-[#64748B]">
              <Loader2 className="h-4 w-4 animate-spin" />
              Đang tải bình luận...
            </div>
          ) : comments.length > 0 ? (
            comments.map((comment) => renderComment(comment))
          ) : (
            <div className="py-12 text-center text-sm text-[#64748B]">
              Chưa có bình luận nào.
            </div>
          )}
        </div>

        <footer className="border-t border-[#E2E8F0] bg-white p-4">
          {replyTo && (
            <div className="mb-3 flex items-center justify-between rounded-md bg-[#E3F2FD] px-3 py-2 text-xs text-[#0D47A1]">
              <span className="flex items-center gap-2">
                <CornerDownRight className="h-3.5 w-3.5" />
                Trả lời {replyTo.author.username}
              </span>
              <button type="button" onClick={() => setReplyTo(undefined)} className="font-semibold">
                Hủy
              </button>
            </div>
          )}

          <div className="flex items-end gap-2 rounded-2xl bg-[#F1F5F9] px-3 py-2">
            <textarea
              value={content}
              onChange={(event) => setContent(event.target.value)}
              rows={1}
              placeholder={replyTo ? "Viết câu trả lời..." : "Viết bình luận..."}
              className="min-h-10 flex-1 resize-none border-0 bg-transparent py-2 text-sm text-[#0F172A] outline-none placeholder:text-[#64748B]"
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void submit();
                }
              }}
            />
            <button
              type="button"
              onClick={() => void submit()}
              disabled={!content.trim() || submitting}
              className="mb-1 rounded-full p-2 text-[#2196F3] hover:bg-[#E3F2FD] disabled:text-[#94A3B8]"
              title="Gửi bình luận"
            >
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </button>
          </div>
          {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
        </footer>
      </div>
    </div>
  );
}
