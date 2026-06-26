"use client";

import {
  FormEvent,
  type ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import Lottie from "lottie-react";
import {
  Check,
  Clock3,
  Copy,
  FileImage,
  History,
  Loader2,
  Maximize2,
  Minimize2,
  Paperclip,
  Plus,
  Search,
  Send,
  Trash2,
  X,
} from "lucide-react";
import { apiService } from "@/lib/api";
import {
  ImagePreviewModal,
  ImagePreviewState,
} from "@/components/ui/ImagePreviewModal";
import {
  agentApi,
  AgentConversation,
  AgentMessageRole,
  AgentPatient,
} from "@/lib/agentApi";
import { useAgentWidget } from "@/contexts/AgentWidgetContext";
import robotAnimation from "./robot.json";

type ChatMessage = {
  id: string;
  role: AgentMessageRole;
  content: string;
  createdAt: string;
  responseMs?: number;
  visuals?: ChatVisual[];
};

type ChatVisual = {
  label: string;
  url: string;
  imageId?: number;
};

function newMessage(
  role: AgentMessageRole,
  content: string,
  options?: { createdAt?: string; responseMs?: number; visuals?: ChatVisual[] },
): ChatMessage {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
    createdAt: options?.createdAt || new Date().toISOString(),
    responseMs: options?.responseMs,
    visuals: options?.visuals,
  };
}

function isVisual(value: unknown): value is ChatVisual {
  if (typeof value !== "object" || value === null) return false;
  const item = value as { label?: unknown; url?: unknown };
  return typeof item.label === "string" && typeof item.url === "string";
}

function collectVisualsFromToolResults(toolResults?: Record<string, unknown>) {
  const visuals: ChatVisual[] = [];
  const seen = new Set<string>();

  const visit = (value: unknown, imageId?: number) => {
    if (!value) return;
    if (Array.isArray(value)) {
      value.forEach((item) => visit(item, imageId));
      return;
    }
    if (typeof value !== "object") return;
    const record = value as Record<string, unknown>;
    const resolvedImageId =
      typeof record.image_id === "number" ? record.image_id : imageId;

    if (Array.isArray(record.visuals)) {
      record.visuals.filter(isVisual).forEach((visual) => {
        const key = `${resolvedImageId || ""}:${visual.label}:${visual.url.slice(0, 80)}`;
        if (!seen.has(key)) {
          seen.add(key);
          visuals.push({ ...visual, imageId: resolvedImageId });
        }
      });
    }

    Object.entries(record).forEach(([key, item]) => {
      if (key === "visuals") return;
      visit(item, resolvedImageId);
    });
  };

  visit(toolResults);
  return visuals.slice(0, 12);
}

function formatChatTime(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatResponseMs(value?: number) {
  if (!value) return "";
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}

function conversationTitle(item: AgentConversation) {
  return item.summary || item.title || `Hội thoại ${item.thread_id.slice(0, 8)}`;
}

function renderInlineMarkdown(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={`${part}-${index}`} className="font-semibold">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code
          key={`${part}-${index}`}
          className="rounded bg-slate-100 px-1 py-0.5 text-[0.85em] text-[#0F172A]"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return <span key={`${part}-${index}`}>{part}</span>;
  });
}

function MarkdownMessage({ content }: { content: string }) {
  const lines = content.split(/\r?\n/);
  const blocks: ReactNode[] = [];
  let bullets: string[] = [];

  const flushBullets = () => {
    if (!bullets.length) return;
    blocks.push(
      <ul key={`ul-${blocks.length}`} className="my-1 list-disc space-y-1 pl-5">
        {bullets.map((line, index) => (
          <li key={`${line}-${index}`}>{renderInlineMarkdown(line)}</li>
        ))}
      </ul>,
    );
    bullets = [];
  };

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushBullets();
      blocks.push(<div key={`space-${index}`} className="h-2" />);
      return;
    }

    const bullet = trimmed.match(/^[-*]\s+(.+)/);
    if (bullet) {
      bullets.push(bullet[1]);
      return;
    }

    flushBullets();
    const heading = trimmed.match(/^#{1,3}\s+(.+)/);
    if (heading) {
      blocks.push(
        <p key={`h-${index}`} className="mt-1 font-semibold text-[#0F172A]">
          {renderInlineMarkdown(heading[1])}
        </p>,
      );
      return;
    }

    blocks.push(
      <p key={`p-${index}`} className="my-1">
        {renderInlineMarkdown(trimmed)}
      </p>,
    );
  });
  flushBullets();

  return <div className="agent-markdown">{blocks}</div>;
}

function patientCode(patient: AgentPatient) {
  return patient.patient_external_id || String(patient.id);
}

function getRoutePatientId(pathname: string, searchParams: URLSearchParams) {
  const queryPatientId = searchParams.get("patientId");
  if (queryPatientId) return queryPatientId;

  const parts = pathname.split("/").filter(Boolean);
  const contextualRoutes = new Set(["patients", "results", "history"]);
  if (parts.length >= 2 && contextualRoutes.has(parts[0])) {
    return decodeURIComponent(parts[1]);
  }

  return undefined;
}

function getErrorDetail(error: unknown) {
  if (typeof error === "object" && error !== null) {
    const maybeAxios = error as {
      message?: string;
      response?: { status?: number; data?: { detail?: unknown } };
    };
    return {
      status: maybeAxios.response?.status,
      detail: maybeAxios.response?.data?.detail,
      message: maybeAxios.message,
    };
  }
  return { status: undefined, detail: undefined, message: undefined };
}

export function AgentFloatingWidget() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const {
    mode,
    setMode,
    activeThreadId,
    setActiveThreadId,
    draftMessage,
    setDraftMessage,
    selectedPatientId,
    setSelectedPatientId,
  } = useAgentWidget();
  const [messages, setMessages] = useState<ChatMessage[]>([
    newMessage(
      "assistant",
      "Xin chào. Tôi có thể hỗ trợ hỏi đáp hồ sơ, giải thích XAI, chạy MRI pipeline nhanh qua chatbox và mở form xác nhận/chỉnh nhãn.",
    ),
  ]);
  const [busy, setBusy] = useState(false);
  const [attachedFile, setAttachedFile] = useState<File | null>(null);
  const [patientQuery, setPatientQuery] = useState("");
  const [patientResults, setPatientResults] = useState<AgentPatient[]>([]);
  const [showPatientSearch, setShowPatientSearch] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [historyItems, setHistoryItems] = useState<AgentConversation[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [conversationToDelete, setConversationToDelete] =
    useState<AgentConversation | null>(null);
  const [previewImage, setPreviewImage] = useState<ImagePreviewState | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  const panelOpen = mode === "panel" || mode === "expanded";
  const isExpanded = mode === "expanded";
  const routePatientId = useMemo(
    () => getRoutePatientId(pathname, searchParams),
    [pathname, searchParams],
  );
  const activePatientId = routePatientId || selectedPatientId;

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, busy, panelOpen]);

  useEffect(() => {
    const timer = setTimeout(async () => {
      if (!showPatientSearch) return;
      try {
        const response = await agentApi.searchPatients(patientQuery);
        setPatientResults(response.data.items);
      } catch {
        setPatientResults([]);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [patientQuery, showPatientSearch]);

  const canSend = useMemo(
    () => Boolean(draftMessage.trim() || attachedFile) && !busy,
    [draftMessage, attachedFile, busy],
  );

  const append = (message: ChatMessage) => {
    setMessages((current) => [...current, message]);
  };

  const copyMessage = async (message: ChatMessage) => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopiedMessageId(message.id);
      window.setTimeout(() => setCopiedMessageId(null), 1200);
    } catch {
      setCopiedMessageId(null);
    }
  };

  const refreshHistory = async () => {
    setHistoryLoading(true);
    try {
      const response = await agentApi.conversations();
      setHistoryItems(response.data.items || []);
    } catch {
      setHistoryItems([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  const loadHistory = async () => {
    setShowHistory((current) => !current);
    if (!historyItems.length) {
      await refreshHistory();
    }
  };

  const loadConversation = async (threadId: string) => {
    setHistoryLoading(true);
    try {
      const response = await agentApi.conversationMessages(threadId);
      setActiveThreadId(threadId);
      setMessages(
        response.data.messages
          .filter((message) => message.role === "user" || message.role === "assistant" || message.role === "tool" || message.role === "error")
          .map((message) =>
            newMessage(message.role, message.content || "", {
              createdAt: message.created_at || undefined,
              visuals: collectVisualsFromToolResults(
                message.metadata?.tool_results as Record<string, unknown> | undefined,
              ),
            }),
          ),
      );
      setShowHistory(false);
    } catch {
      append(newMessage("error", "Không thể tải lại lịch sử hội thoại."));
    } finally {
      setHistoryLoading(false);
    }
  };

  function startNewChat() {
    setActiveThreadId(undefined);
    setMessages([
      newMessage(
        "assistant",
        "Xin chào. Tôi có thể hỗ trợ hỏi đáp hồ sơ, giải thích XAI, chạy MRI pipeline nhanh qua chatbox và mở form xác nhận/chỉnh nhãn.",
      ),
    ]);
    setShowHistory(false);
  }

  const confirmDeleteConversation = async () => {
    if (!conversationToDelete) return;
    const threadId = conversationToDelete.thread_id;
    setHistoryLoading(true);
    try {
      await agentApi.deleteConversation(threadId);
      setHistoryItems((items) =>
        items.filter((item) => item.thread_id !== threadId),
      );
      if (activeThreadId === threadId) {
        startNewChat();
      }
      setConversationToDelete(null);
    } catch {
      append(newMessage("error", "Không thể xóa hội thoại này."));
    } finally {
      setHistoryLoading(false);
    }
  };

  const runQuickMri = async (file: File, patientId?: string) => {
    if (!patientId?.trim()) {
      setShowPatientSearch(true);
      append(
        newMessage(
          "assistant",
          "Cần chọn bệnh nhân để lưu ảnh MRI và chạy pipeline. Hãy nhập tên hoặc mã bệnh nhân ở form bên dưới để tôi tiếp tục.",
        ),
      );
      return;
    }

    setBusy(true);
    try {
      append(newMessage("tool", "Đang upload MRI qua chatbox và tạo task MRI pipeline..."));
      const quick = await agentApi.quickMri({ patientId, file });
      const { task_id, image_id, patient } = quick.data;
      const routePatientId = patient.patient_external_id || String(patient.id);

      append(newMessage("assistant", quick.data.summary));
      await apiService.inference.waitForTask(
        task_id,
        2000,
        1200000,
        (percent, status) => {
          setMessages((current) => [
            ...current.filter((item) => item.id !== "agent-task-progress"),
            {
              id: "agent-task-progress",
              role: "tool",
              content: `${status} ${percent ? `(${percent}%)` : ""}`,
              createdAt: new Date().toISOString(),
            },
          ]);
        },
      );

      setMessages((current) =>
        current.filter((item) => item.id !== "agent-task-progress"),
      );

      const summary = await agentApi.quickMriSummary(image_id);
      append(newMessage("assistant", summary.data.summary));
      append(newMessage("tool", "Đang mở trang kết quả chi tiết..."));
      router.push(`/results/${encodeURIComponent(routePatientId)}?imageId=${image_id}`);
    } catch (error: unknown) {
      const { status, detail, message } = getErrorDetail(error);
      const interruptDetail =
        typeof detail === "object" && detail !== null
          ? (detail as { type?: string; reason?: string })
          : undefined;
      if (status === 409 && interruptDetail?.type === "select_patient") {
        setShowPatientSearch(true);
        append(newMessage("assistant", interruptDetail.reason || "Cần chọn bệnh nhân trước khi chạy MRI pipeline."));
      } else {
        append(
          newMessage(
            "error",
            (typeof detail === "string" ? detail : undefined) ||
              message ||
              "Không thể chạy MRI pipeline qua chatbox.",
          ),
        );
      }
    } finally {
      setBusy(false);
    }
  };

  const handleSend = async (event?: FormEvent) => {
    event?.preventDefault();
    if (!canSend) return;

    const content = draftMessage.trim();
    const file = attachedFile;
    setDraftMessage("");
    setAttachedFile(null);

    append(
      newMessage(
        "user",
        [content, file ? `File MRI: ${file.name}` : ""].filter(Boolean).join("\n"),
      ),
    );

    if (file) {
      await runQuickMri(file, activePatientId || patientQuery);
      return;
    }

    setBusy(true);
    try {
      const startedAt = performance.now();
      const response = await agentApi.chat({
        message: content,
        thread_id: activeThreadId,
        patient_id: activePatientId,
      });
      setActiveThreadId(response.data.thread_id);
      append(
        newMessage("assistant", response.data.message, {
          responseMs: performance.now() - startedAt,
          visuals: collectVisualsFromToolResults(response.data.tool_results),
        }),
      );
    } catch (error: unknown) {
      const { detail, message } = getErrorDetail(error);
      append(
        newMessage(
          "error",
          (typeof detail === "string" ? detail : undefined) ||
            message ||
            "Agent không phản hồi được.",
        ),
      );
    } finally {
      setBusy(false);
    }
  };

  const choosePatient = (patient: AgentPatient) => {
    const code = patientCode(patient);
    setSelectedPatientId(code);
    setPatientQuery(code);
    setShowPatientSearch(false);
    append(newMessage("tool", `Đã chọn bệnh nhân ${patient.name || "không tên"} (${code}).`));
  };

  if (!panelOpen) {
    return (
      <button
        type="button"
        onClick={() => setMode("panel")}
        className="fixed bottom-6 right-6 z-[70] flex h-20 w-20 items-center justify-center rounded-full border border-teal-300/70 bg-white shadow-2xl shadow-teal-900/30 transition hover:scale-105"
        aria-label="Mở NeuroDiagnosis Agent"
      >
        <span className="absolute inset-0 rounded-full bg-teal-400/20 blur-xl" />
        <Lottie animationData={robotAnimation} loop className="relative h-16 w-16" />
      </button>
    );
  }

  return (
    <section
      className={`agent-shell ${isExpanded ? "agent-shell-expanded" : ""}`}
      aria-label="NeuroDiagnosis Agent"
    >
      <div className="agent-content flex flex-col">
        <header className="flex items-center justify-between border-b border-[#E2E8F0] bg-[#F6FAF9] px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-teal-50">
              <Lottie animationData={robotAnimation} loop className="h-9 w-9" />
            </div>
            <div className="min-w-0">
              <h2 className="truncate text-sm font-bold text-slate-950">
                NeuroDiagnosis Agent
              </h2>
              <p className="truncate text-xs text-[#64748B]">
                Trợ lý AI lâm sàng
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={startNewChat}
              className="rounded-lg p-2 text-[#64748B] hover:bg-white hover:text-[#0F172A]"
              title="Cuộc trò chuyện mới"
            >
              <Plus className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => void loadHistory()}
              className="rounded-lg p-2 text-[#64748B] hover:bg-white hover:text-[#0F172A]"
              title="Lịch sử chat"
            >
              <History className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setMode(isExpanded ? "panel" : "expanded")}
              className="rounded-lg p-2 text-[#64748B] hover:bg-white hover:text-[#0F172A]"
              title={isExpanded ? "Thu gọn" : "Mở rộng"}
            >
              {isExpanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            </button>
            <button
              type="button"
              onClick={() => setMode("bubble")}
              className="rounded-lg p-2 text-[#64748B] hover:bg-white hover:text-[#0F172A]"
              title="Đóng"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </header>

        <div className="flex min-h-0 flex-1 bg-[#F6FAF9]">
          {showHistory && (
            <aside className="flex w-72 shrink-0 flex-col border-r border-[#E2E8F0] bg-white">
              <div className="border-b border-[#E2E8F0] px-4 py-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-[#0F172A]">Lịch sử chat</h3>
                  <button
                    type="button"
                    onClick={() => void refreshHistory()}
                    className="text-xs font-medium text-[#0F9F8F] hover:underline"
                  >
                    Tải lại
                  </button>
                </div>
                <button
                  type="button"
                  onClick={startNewChat}
                  className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-[#E2E8F0] bg-[#F6FAF9] px-3 py-2 text-sm font-medium text-[#0F172A] transition hover:border-[#0F9F8F] hover:bg-white"
                >
                  <Plus className="h-4 w-4" />
                  Chat mới
                </button>
              </div>
              <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
                {historyLoading && (
                  <div className="flex items-center gap-2 text-sm text-[#64748B]">
                    <Loader2 className="h-4 w-4 animate-spin text-[#0F9F8F]" />
                    Đang tải lịch sử...
                  </div>
                )}
                {!historyLoading && !historyItems.length && (
                  <div className="rounded-xl border border-[#E2E8F0] bg-[#F6FAF9] px-3 py-3 text-sm text-[#64748B]">
                    Chưa có hội thoại đã lưu.
                  </div>
                )}
                {historyItems.map((item) => {
                  const active = activeThreadId === item.thread_id;
                  return (
                    <div
                      key={item.thread_id}
                      className={[
                        "group rounded-xl border bg-[#F6FAF9] transition",
                        active
                          ? "border-[#0F9F8F] bg-white"
                          : "border-[#E2E8F0] hover:border-[#0F9F8F] hover:bg-white",
                      ].join(" ")}
                    >
                      <button
                        type="button"
                        onClick={() => void loadConversation(item.thread_id)}
                        className="block w-full px-3 pb-2 pt-3 text-left"
                      >
                        <div className="truncate text-sm font-medium text-[#0F172A]">
                          {conversationTitle(item)}
                        </div>
                        <div className="mt-1 flex items-center gap-2 text-xs text-[#64748B]">
                          <Clock3 className="h-3.5 w-3.5" />
                          {formatChatTime(item.updated_at || item.created_at || undefined)}
                        </div>
                      </button>
                      <div className="flex justify-end px-2 pb-2">
                        <button
                          type="button"
                          onClick={() => setConversationToDelete(item)}
                          className="rounded-lg p-1.5 text-[#64748B] opacity-0 transition hover:bg-red-50 hover:text-[#DC2626] group-hover:opacity-100"
                          title="Xóa hội thoại"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </aside>
          )}

          <div className="flex min-w-0 flex-1 flex-col">
            <div ref={listRef} className="flex-1 space-y-4 overflow-y-auto bg-[#F6FAF9] p-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div className="group max-w-[86%]">
                <div
                  className={[
                    "rounded-2xl px-4 py-3 text-sm leading-6 shadow-sm",
                    message.role === "user"
                      ? "bg-[#0F9F8F] text-white"
                      : message.role === "tool"
                        ? "border border-[#E2E8F0] bg-white text-[#64748B]"
                        : message.role === "error"
                          ? "border border-red-200 bg-red-50 text-[#DC2626]"
                          : "border border-[#E2E8F0] bg-white text-[#0F172A]",
                  ].join(" ")}
                >
                  <MarkdownMessage content={message.content} />
                  {message.visuals?.length ? (
                    <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                      {message.visuals.map((visual, index) => (
                        <figure
                          key={`${visual.label}-${visual.imageId || "img"}-${index}`}
                          className="overflow-hidden rounded-xl border border-[#E2E8F0] bg-[#F6FAF9]"
                        >
                          <div className="flex items-center justify-between px-3 py-2">
                            <figcaption className="truncate text-xs font-semibold uppercase tracking-wide text-[#64748B]">
                              {visual.imageId ? `ID ${visual.imageId} - ` : ""}
                              {visual.label}
                            </figcaption>
                          </div>
                          <button
                            type="button"
                            onClick={() =>
                              setPreviewImage({
                                title: `${visual.imageId ? `ID ${visual.imageId} - ` : ""}${visual.label}`,
                                src: visual.url,
                              })
                            }
                            className="block w-full cursor-zoom-in bg-black"
                            title="Nhấp để phóng to ảnh"
                          >
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                              src={visual.url}
                              alt={visual.label}
                              className="h-44 w-full object-contain transition hover:opacity-90"
                            />
                          </button>
                        </figure>
                      ))}
                    </div>
                  ) : null}
                </div>
                <div
                  className={`mt-1 flex items-center gap-2 text-[11px] text-[#64748B] ${
                    message.role === "user" ? "justify-end" : "justify-start"
                  }`}
                >
                  <span>{formatChatTime(message.createdAt)}</span>
                  {message.role === "assistant" && message.responseMs ? (
                    <span>Phản hồi {formatResponseMs(message.responseMs)}</span>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => void copyMessage(message)}
                    className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[#64748B] opacity-0 transition hover:bg-white hover:text-[#0F172A] group-hover:opacity-100"
                    title="Copy đoạn chat"
                  >
                    {copiedMessageId === message.id ? (
                      <Check className="h-3.5 w-3.5 text-[#16A34A]" />
                    ) : (
                      <Copy className="h-3.5 w-3.5" />
                    )}
                    {copiedMessageId === message.id ? "Đã copy" : "Copy"}
                  </button>
                </div>
              </div>
            </div>
          ))}
          {busy && (
            <div className="flex items-center gap-2 text-sm text-[#64748B]">
              <Loader2 className="h-4 w-4 animate-spin text-[#0F9F8F]" />
              Agent đang xử lý...
            </div>
          )}
            </div>

        {showPatientSearch && (
          <div className="border-t border-[#E2E8F0] bg-[#F6FAF9] px-4 py-3">
            <label className="mb-2 block text-xs font-semibold uppercase tracking-wide text-[#64748B]">
              Interrupt: Chọn bệnh nhân để tiếp tục
            </label>
            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-[#64748B]" />
              <input
                value={patientQuery}
                onChange={(event) => setPatientQuery(event.target.value)}
                placeholder="Nhập tên hoặc mã bệnh nhân..."
                className="w-full rounded-xl border border-[#E2E8F0] bg-white py-2 pl-9 pr-3 text-sm text-[#0F172A] caret-[#0F9F8F] outline-none placeholder:text-[#64748B] focus:border-[#0F9F8F]"
              />
            </div>
            <div className="mt-2 max-h-32 overflow-y-auto rounded-xl border border-[#E2E8F0] bg-white">
              {patientResults.map((patient) => (
                <button
                  key={patient.id}
                  type="button"
                  onClick={() => choosePatient(patient)}
                  className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-[#F6FAF9]"
                >
                  <span className="font-medium text-[#0F172A]">
                    {patient.name || "Bệnh nhân không tên"}
                  </span>
                  <span className="text-xs text-[#64748B]">{patientCode(patient)}</span>
                </button>
              ))}
              {!patientResults.length && (
                <div className="px-3 py-3 text-sm text-[#64748B]">Không có kết quả.</div>
              )}
            </div>
          </div>
        )}

        <form onSubmit={handleSend} className="border-t border-[#E2E8F0] bg-[#F6FAF9] p-3">
          {attachedFile && (
            <div className="mb-2 flex items-center justify-between rounded-xl border border-[#0F9F8F]/30 bg-white px-3 py-2 text-sm text-[#0F9F8F]">
              <span className="flex min-w-0 items-center gap-2">
                <FileImage className="h-4 w-4 shrink-0" />
                <span className="truncate">{attachedFile.name}</span>
              </span>
              <button type="button" onClick={() => setAttachedFile(null)}>
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          )}
          <div className="flex items-end gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept=".dcm,.dicom,.png,.jpg,.jpeg,.bmp,.tif,.tiff"
              className="hidden"
              onChange={(event) => setAttachedFile(event.target.files?.[0] || null)}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="rounded-xl border border-[#E2E8F0] bg-white p-3 text-[#64748B] hover:border-[#0F9F8F] hover:text-[#0F9F8F]"
              title="Attach MRI"
            >
              <Paperclip className="h-4 w-4" />
            </button>
            <textarea
              value={draftMessage}
              onChange={(event) => setDraftMessage(event.target.value)}
              placeholder="Hỏi Agent hoặc attach MRI để chạy chẩn đoán nhanh..."
              rows={2}
              className="max-h-28 min-h-11 flex-1 resize-none rounded-xl border border-[#E2E8F0] bg-white px-3 py-2 text-sm text-[#0F172A] caret-[#0F9F8F] outline-none placeholder:text-[#64748B] focus:border-[#0F9F8F]"
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void handleSend();
                }
              }}
            />
            <button
              type="submit"
              disabled={!canSend}
              className="rounded-xl bg-[#0F9F8F] p-3 text-white shadow-lg shadow-[#0F9F8F]/20 transition hover:bg-[#0c8f81] disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none"
              title="Gửi"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </button>
          </div>
        </form>
          </div>
        </div>
      </div>

      {conversationToDelete && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-[#0F172A]/30 px-4">
          <div className="w-full max-w-sm rounded-2xl border border-[#E2E8F0] bg-white p-5 shadow-2xl">
            <h3 className="text-base font-semibold text-[#0F172A]">
              Xóa lịch sử chat?
            </h3>
            <p className="mt-2 text-sm leading-6 text-[#64748B]">
              Hội thoại này sẽ được ẩn khỏi lịch sử chat. Bạn cần xác nhận trước
              khi xóa.
            </p>
            <div className="mt-4 rounded-xl bg-[#F6FAF9] px-3 py-2 text-sm text-[#0F172A]">
              {conversationTitle(conversationToDelete)}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setConversationToDelete(null)}
                className="rounded-xl border border-[#E2E8F0] px-4 py-2 text-sm font-medium text-[#0F172A] hover:bg-[#F6FAF9]"
              >
                Hủy
              </button>
              <button
                type="button"
                onClick={() => void confirmDeleteConversation()}
                className="rounded-xl bg-[#DC2626] px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:bg-slate-300"
                disabled={historyLoading}
              >
                {historyLoading ? "Đang xóa..." : "Xóa"}
              </button>
            </div>
          </div>
        </div>
      )}
      {previewImage && (
        <ImagePreviewModal
          preview={previewImage}
          onClose={() => setPreviewImage(null)}
        />
      )}
    </section>
  );
}
