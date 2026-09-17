"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Loader2,
  RefreshCw,
  Search,
  Send,
  Share2,
  Stethoscope,
} from "lucide-react";
import { NeuroBoardComposer } from "@/components/neuroboard/NeuroBoardComposer";
import { NeuroBoardPost } from "@/components/neuroboard/NeuroBoardPost";
import { NeuroBoardRightRail } from "@/components/neuroboard/NeuroBoardRightRail";
import {
  NeuroBoardSidebar,
  type NeuroBoardView,
} from "@/components/neuroboard/NeuroBoardSidebar";
import type {
  NeuroFeedScope,
  NeuroMessengerCase,
  NeuroPost,
  NeuroPostType,
  NeuroReviewQueueItem,
} from "@/components/neuroboard/types";
import { resolveMediaUrl } from "@/lib/api";
import { neuroboardApi } from "@/lib/neuroboardApi";

type ReviewScope = "all" | "my_reviews" | "second_opinions" | "overdue" | "completed";

function confidenceText(value?: number | null) {
  return typeof value === "number" ? `${(value * 100).toFixed(0)}%` : "--";
}

function caseTitle(item: NeuroMessengerCase) {
  return item.patient_external_id || `CASE-${String(item.image_id).padStart(4, "0")}`;
}

function labelText(item: NeuroMessengerCase) {
  return item.ai_label || "No label";
}

function CaseThumb({ item }: { item: NeuroMessengerCase }) {
  return (
    <div className="h-24 w-24 shrink-0 overflow-hidden rounded-md bg-[#E3F2FD]">
      {item.thumbnail_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={resolveMediaUrl(item.thumbnail_url)} alt={caseTitle(item)} className="h-full w-full object-cover" />
      ) : (
        <div className="flex h-full w-full items-center justify-center text-xs font-bold text-[#0D47A1]">
          MRI
        </div>
      )}
    </div>
  );
}

function resultHref(item: NeuroMessengerCase, openReview = false) {
  const params = new URLSearchParams({ imageId: String(item.image_id) });
  if (openReview) params.set("review", "1");
  return `/results/${item.patient_id}?${params.toString()}`;
}

function actionErrorMessage(error: unknown, fallback: string) {
  const candidate = error as { response?: { data?: { detail?: string } }; message?: string };
  return candidate.response?.data?.detail || candidate.message || fallback;
}

function ReviewQueueView({
  items,
  loading,
  onRequestSecondOpinion,
  onOpenReview,
  onPostCase,
  openingReviewId,
}: {
  items: NeuroReviewQueueItem[];
  loading: boolean;
  onRequestSecondOpinion: (item: NeuroMessengerCase) => void;
  onOpenReview: (item: NeuroReviewQueueItem) => void;
  onPostCase: (item: NeuroMessengerCase) => void;
  openingReviewId?: string | null;
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-md border border-[#90CAF9] bg-white py-12 text-sm text-[#64748B]">
        <Loader2 className="h-5 w-5 animate-spin text-[#2196F3]" />
        Đang tải Review Queue...
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="rounded-md border border-[#90CAF9] bg-white px-6 py-12 text-center">
        <Stethoscope className="mx-auto h-8 w-8 text-[#64748B]" />
        <h2 className="mt-3 text-base font-semibold text-[#0F172A]">Không có case cần review</h2>
        <p className="mt-1 text-sm text-[#64748B]">Review Queue của tài khoản hiện tại đang trống.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {items.map((item) => (
        <article key={item.id} className="rounded-md border border-[#90CAF9] bg-white p-4 shadow-sm">
          <div className="flex gap-4">
            <CaseThumb item={item.case} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h2 className="text-base font-bold text-[#0F172A]">{caseTitle(item.case)}</h2>
                  <p className="text-sm text-[#64748B]">
                    {item.queue_type === "second_opinion"
                      ? `From: ${item.request?.from.display_name || "Doctor"}`
                      : "Assigned: current user"}
                  </p>
                </div>
                <span className="rounded bg-amber-100 px-2 py-1 text-xs font-bold text-amber-800">
                  {item.status}
                </span>
              </div>
              <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                <div>AI: <span className="font-semibold">{labelText(item.case)}</span></div>
                <div>Confidence: <span className="font-semibold">{confidenceText(item.case.confidence)}</span></div>
                <div>Priority: <span className="font-semibold">{item.priority || "Medium"}</span></div>
                <div>Review: <span className="font-semibold">{item.case.review_status || item.status}</span></div>
              </div>
              {item.request?.message && (
                <p className="mt-3 rounded-md bg-[#E3F2FD] px-3 py-2 text-sm text-[#0F172A]">
                  {item.request.message}
                </p>
              )}
              <div className="mt-4 flex flex-wrap gap-2">
                <a href={resultHref(item.case)} className="rounded-md border border-[#90CAF9] px-3 py-2 text-sm font-semibold text-[#0D47A1] hover:bg-[#E3F2FD]">
                  Open Result
                </a>
                <button
                  type="button"
                  onClick={() => onOpenReview(item)}
                  disabled={openingReviewId === item.id}
                  className="inline-flex items-center gap-2 rounded-md bg-[#0D47A1] px-3 py-2 text-sm font-semibold text-white hover:bg-[#2196F3] disabled:opacity-60"
                >
                  {openingReviewId === item.id && <Loader2 className="h-4 w-4 animate-spin" />}
                  Review
                </button>
                <button
                  type="button"
                  onClick={() => onPostCase(item.case)}
                  className="rounded-md border border-[#90CAF9] px-3 py-2 text-sm font-semibold text-[#0D47A1] hover:bg-[#E3F2FD]"
                >
                  Share to NeuroBoard
                </button>
                <button
                  type="button"
                  onClick={() => onRequestSecondOpinion(item.case)}
                  className="rounded-md border border-[#90CAF9] px-3 py-2 text-sm font-semibold text-[#0D47A1] hover:bg-[#E3F2FD]"
                >
                  Second Opinion
                </button>
              </div>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}

function MyCasesView({
  items,
  loading,
  onRequestSecondOpinion,
  onPostCase,
}: {
  items: NeuroMessengerCase[];
  loading: boolean;
  onRequestSecondOpinion: (item: NeuroMessengerCase) => void;
  onPostCase: (item: NeuroMessengerCase) => void;
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-md border border-[#90CAF9] bg-white py-12 text-sm text-[#64748B]">
        <Loader2 className="h-5 w-5 animate-spin text-[#2196F3]" />
        Đang tải My Cases...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {items.map((item) => (
        <article key={item.image_id} className="rounded-md border border-[#90CAF9] bg-white p-4 shadow-sm">
          <div className="flex gap-4">
            <CaseThumb item={item} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h2 className="text-base font-bold text-[#0F172A]">{caseTitle(item)}</h2>
                  <p className="text-sm text-[#64748B]">{item.patient_name || "Unnamed patient"}</p>
                </div>
                <span className="rounded bg-[#E3F2FD] px-2 py-1 text-xs font-bold text-[#0D47A1]">
                  {item.review_status || "not_required"}
                </span>
              </div>
              <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                <div>AI: <span className="font-semibold">{labelText(item)}</span></div>
                <div>Confidence: <span className="font-semibold">{confidenceText(item.confidence)}</span></div>
                <div>Risk: <span className="font-semibold">{item.risk_group || "--"}</span></div>
                <div>Second Opinion: <span className="font-semibold">{item.second_opinion_status || "--"}</span></div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <a href={resultHref(item)} className="rounded-md border border-[#90CAF9] px-3 py-2 text-sm font-semibold text-[#0D47A1] hover:bg-[#E3F2FD]">
                  Open Case
                </a>
                <button
                  type="button"
                  onClick={() => onRequestSecondOpinion(item)}
                  className="inline-flex items-center gap-2 rounded-md bg-[#0D47A1] px-3 py-2 text-sm font-semibold text-white hover:bg-[#2196F3]"
                >
                  <Send className="h-4 w-4" />
                  Request Second Opinion
                </button>
                <button
                  type="button"
                  onClick={() => onPostCase(item)}
                  className="inline-flex items-center gap-2 rounded-md border border-[#90CAF9] px-3 py-2 text-sm font-semibold text-[#0D47A1] hover:bg-[#E3F2FD]"
                >
                  <Share2 className="h-4 w-4" />
                  Đăng Clinical Post
                </button>
              </div>
            </div>
          </div>
        </article>
      ))}
      {!loading && items.length === 0 && (
        <div className="rounded-md border border-[#90CAF9] bg-white px-6 py-12 text-center text-sm text-[#64748B]">
          Chưa có clinical case trong dataset của tài khoản này.
        </div>
      )}
    </div>
  );
}

export default function NeuroBoardPage() {
  const router = useRouter();
  const [activeView, setActiveView] = useState<NeuroBoardView>("feed");
  const [posts, setPosts] = useState<NeuroPost[]>([]);
  const [scope, setScope] = useState<NeuroFeedScope>("all");
  const [postType, setPostType] = useState<NeuroPostType>();
  const [nextCursor, setNextCursor] = useState<number>();
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string>();
  const [queueItems, setQueueItems] = useState<NeuroReviewQueueItem[]>([]);
  const [cases, setCases] = useState<NeuroMessengerCase[]>([]);
  const [loadingQueue, setLoadingQueue] = useState(false);
  const [loadingCases, setLoadingCases] = useState(false);
  const [attachCase, setAttachCase] = useState<NeuroMessengerCase | null>(null);
  const [reviewScope, setReviewScope] = useState<ReviewScope>("all");
  const [openingReviewId, setOpeningReviewId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string>();

  const loadFeed = useCallback(
    async (cursor?: number) => {
      if (cursor) setLoadingMore(true);
      else setLoading(true);
      setError(undefined);
      try {
        const response = await neuroboardApi.getFeed({ scope, postType, cursor });
        setPosts((current) =>
          cursor ? [...current, ...response.data.items] : response.data.items,
        );
        setNextCursor(response.data.next_cursor || undefined);
      } catch {
        setError("Không thể tải NeuroBoard.");
        if (!cursor) setPosts([]);
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [scope, postType],
  );

  const loadQueue = useCallback(async () => {
    setLoadingQueue(true);
    try {
      const response = await neuroboardApi.getReviewQueue(reviewScope);
      setQueueItems(response.data.items || []);
    } finally {
      setLoadingQueue(false);
    }
  }, [reviewScope]);

  const loadCases = useCallback(async () => {
    setLoadingCases(true);
    try {
      const response = await neuroboardApi.getMyCases();
      setCases(response.data.items || []);
    } finally {
      setLoadingCases(false);
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      if (activeView === "feed") void loadFeed();
      if (activeView === "review_queue") void loadQueue();
      if (activeView === "my_cases") void loadCases();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [activeView, loadFeed, loadQueue, loadCases]);

  const updatePost = (updated: NeuroPost) => {
    setPosts((current) =>
      current.map((post) => (post.id === updated.id ? updated : post)),
    );
  };

  const postCase = async (item: NeuroMessengerCase) => {
    setActionError(undefined);
    try {
      const response = await neuroboardApi.createPost({
        postType: "clinical_case",
        content: "Clinical case shared from My Cases.",
        imageId: item.image_id,
        files: [],
      });
      setActiveView("feed");
      setScope("all");
      setPostType("clinical_case");
      setPosts((current) => [response.data, ...current.filter((post) => post.id !== response.data.id)]);
    } catch (error) {
      setActionError(actionErrorMessage(error, "Khong the chia se case len NeuroBoard."));
    }
  };

  const openReviewItem = async (item: NeuroReviewQueueItem) => {
    setOpeningReviewId(item.id);
    try {
      if (item.queue_type === "second_opinion" && item.request?.id && item.status === "Pending") {
        await neuroboardApi.openSecondOpinion(item.request.id);
      }
      await loadQueue();
      router.push(resultHref(item.case, true));
    } finally {
      setOpeningReviewId(null);
    }
  };

  return (
    <div className="-m-3 min-h-[calc(100vh-4rem)] bg-[#E3F2FD] text-[#0F172A] md:-m-6">
      <div className="sticky top-0 z-20 border-b border-[#90CAF9] bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1560px] items-center justify-between gap-4 px-5 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-[#0D47A1] text-white shadow-sm">
              <Stethoscope className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-[#0D47A1]">NeuroBoard</h1>
              <p className="text-xs text-[#64748B]">Clinical collaboration network</p>
            </div>
          </div>
          <div className="relative hidden w-full max-w-sm md:block">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-[#64748B]" />
            <input
              type="search"
              placeholder="Search NeuroBoard"
              className="w-full rounded-md border border-[#90CAF9] bg-white py-2 pl-9 pr-3 text-sm text-[#0F172A] outline-none placeholder:text-slate-500 focus:border-[#2196F3] focus:ring-2 focus:ring-[#90CAF9]/50"
            />
          </div>
          <button
            type="button"
            onClick={() => {
              if (activeView === "feed") void loadFeed();
              if (activeView === "review_queue") void loadQueue();
              if (activeView === "my_cases") void loadCases();
            }}
            className="rounded-md border border-[#90CAF9] bg-white p-2.5 text-[#0D47A1] hover:bg-[#E3F2FD]"
            title="Refresh"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="mx-auto grid max-w-[1560px] grid-cols-1 gap-5 px-4 py-5 lg:grid-cols-[minmax(0,1fr)_320px] xl:grid-cols-[220px_minmax(0,760px)_320px]">
        <NeuroBoardSidebar
          activeView={activeView}
          scope={scope}
          postType={postType}
          onViewChange={setActiveView}
          onScopeChange={setScope}
          onTypeChange={setPostType}
        />

        <main className="min-w-0 space-y-4">
          {actionError && (
            <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">
              {actionError}
            </div>
          )}

          <div className="flex gap-2 overflow-x-auto xl:hidden">
            {(["feed", "review_queue", "my_cases"] as const).map((view) => (
              <button
                key={view}
                type="button"
                onClick={() => setActiveView(view)}
                className={`shrink-0 rounded-md px-3 py-2 text-sm font-semibold ${
                  activeView === view ? "bg-[#0D47A1] text-white" : "bg-white text-[#0F172A]"
                }`}
              >
                {view === "feed" ? "Feed" : view === "review_queue" ? "Review Queue" : "My Cases"}
              </button>
            ))}
          </div>

          {activeView === "feed" && (
            <>
              <NeuroBoardComposer
                onCreated={(post) => {
                  setScope("all");
                  setPostType(undefined);
                  setPosts((current) => [post, ...current.filter((item) => item.id !== post.id)]);
                }}
              />

              {loading && (
                <div className="flex items-center justify-center gap-2 rounded-md border border-[#90CAF9] bg-white py-12 text-sm text-[#64748B]">
                  <Loader2 className="h-5 w-5 animate-spin text-[#2196F3]" />
                  Đang tải feed...
                </div>
              )}

              {!loading && error && (
                <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                  {error}
                </div>
              )}

              {!loading && !error && posts.length === 0 && (
                <div className="rounded-md border border-[#90CAF9] bg-white px-6 py-12 text-center">
                  <Stethoscope className="mx-auto h-8 w-8 text-[#64748B]" />
                  <h2 className="mt-3 text-base font-semibold text-[#0F172A]">Chưa có bài đăng</h2>
                  <p className="mt-1 text-sm text-[#64748B]">Hãy bắt đầu một trao đổi mới trên NeuroBoard.</p>
                </div>
              )}

              {posts.map((post) => (
                <NeuroBoardPost
                  key={post.id}
                  post={post}
                  onUpdated={updatePost}
                  onDeleted={(postId) => setPosts((current) => current.filter((item) => item.id !== postId))}
                />
              ))}

              {nextCursor && (
                <button
                  type="button"
                  onClick={() => void loadFeed(nextCursor)}
                  disabled={loadingMore}
                  className="flex w-full items-center justify-center gap-2 rounded-md border border-[#90CAF9] bg-white py-3 text-sm font-semibold text-[#0D47A1] hover:bg-[#E3F2FD]"
                >
                  {loadingMore && <Loader2 className="h-4 w-4 animate-spin" />}
                  Xem thêm
                </button>
              )}
            </>
          )}

          {activeView === "review_queue" && (
            <>
              <div className="flex gap-2 overflow-x-auto rounded-md border border-[#90CAF9] bg-white p-2">
                {([
                  ["all", "All"],
                  ["my_reviews", "My Reviews"],
                  ["second_opinions", "Second Opinion Requests"],
                  ["overdue", "Overdue"],
                  ["completed", "Completed"],
                ] as const).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setReviewScope(value)}
                    className={`shrink-0 rounded-md px-3 py-2 text-sm font-semibold ${
                      reviewScope === value ? "bg-[#0D47A1] text-white" : "text-[#0D47A1] hover:bg-[#E3F2FD]"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <ReviewQueueView
                items={queueItems}
                loading={loadingQueue}
                onRequestSecondOpinion={setAttachCase}
                onOpenReview={(item) => void openReviewItem(item)}
                onPostCase={(item) => void postCase(item)}
                openingReviewId={openingReviewId}
              />
            </>
          )}

          {activeView === "my_cases" && (
            <MyCasesView
              items={cases}
              loading={loadingCases}
              onRequestSecondOpinion={setAttachCase}
              onPostCase={(item) => void postCase(item)}
            />
          )}
        </main>

        <NeuroBoardRightRail
          attachCase={attachCase}
          onAttachCaseConsumed={() => setAttachCase(null)}
        />
      </div>
    </div>
  );
}
