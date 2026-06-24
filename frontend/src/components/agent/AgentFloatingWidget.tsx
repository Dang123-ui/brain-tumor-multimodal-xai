"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Lottie from "lottie-react";
import {
  ChevronDown,
  FileImage,
  Loader2,
  Maximize2,
  MessageSquareText,
  Minimize2,
  Paperclip,
  Search,
  Send,
  Trash2,
  X,
} from "lucide-react";
import { apiService } from "@/lib/api";
import {
  agentApi,
  AgentMessageRole,
  AgentPatient,
} from "@/lib/agentApi";
import { useAgentWidget } from "@/contexts/AgentWidgetContext";
import robotAnimation from "./robot.json";

type ChatMessage = {
  id: string;
  role: AgentMessageRole;
  content: string;
};

function newMessage(role: AgentMessageRole, content: string): ChatMessage {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
  };
}

function patientCode(patient: AgentPatient) {
  return patient.patient_external_id || String(patient.id);
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
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  const panelOpen = mode === "panel" || mode === "expanded";
  const isExpanded = mode === "expanded";

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

  const runQuickMri = async (file: File, patientId?: string) => {
    if (!patientId?.trim()) {
      setShowPatientSearch(true);
      append(
        newMessage(
          "assistant",
          "Cần chọn mã bệnh nhân trước khi lưu ảnh MRI và chạy pipeline. Hãy nhập tên hoặc mã bệnh nhân ở ô bên dưới.",
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
      await runQuickMri(file, selectedPatientId || patientQuery);
      return;
    }

    setBusy(true);
    try {
      const response = await agentApi.chat({
        message: content,
        thread_id: activeThreadId,
        patient_id: selectedPatientId,
      });
      setActiveThreadId(response.data.thread_id);
      append(newMessage("assistant", response.data.message));
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
        <header className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-teal-50">
              <Lottie animationData={robotAnimation} loop className="h-9 w-9" />
            </div>
            <div className="min-w-0">
              <h2 className="truncate text-sm font-bold text-slate-950">
                NeuroDiagnosis Agent
              </h2>
              <p className="truncate text-xs text-slate-500">
                {selectedPatientId ? `Context: ${selectedPatientId}` : "Chưa chọn bệnh nhân"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setMode(isExpanded ? "panel" : "expanded")}
              className="rounded-lg p-2 text-slate-500 hover:bg-slate-200 hover:text-slate-950"
              title={isExpanded ? "Thu gọn" : "Mở rộng"}
            >
              {isExpanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            </button>
            <button
              type="button"
              onClick={() => setMode("bubble")}
              className="rounded-lg p-2 text-slate-500 hover:bg-slate-200 hover:text-slate-950"
              title="Dong"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </header>

        <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto bg-white p-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={[
                  "max-w-[86%] whitespace-pre-line rounded-2xl px-4 py-3 text-sm leading-6",
                  message.role === "user"
                    ? "bg-teal-600 text-white"
                    : message.role === "tool"
                      ? "border border-slate-200 bg-slate-50 text-slate-600"
                      : message.role === "error"
                        ? "border border-red-200 bg-red-50 text-red-700"
                        : "bg-slate-100 text-slate-800",
                ].join(" ")}
              >
                {message.content}
              </div>
            </div>
          ))}
          {busy && (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin text-teal-600" />
              Agent dang xu ly...
            </div>
          )}
        </div>

        {showPatientSearch && (
          <div className="border-t border-slate-200 bg-slate-50 px-4 py-3">
            <label className="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-500">
              Chọn bệnh nhân
            </label>
            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <input
                value={patientQuery}
                onChange={(event) => setPatientQuery(event.target.value)}
                placeholder="Nhập tên hoặc mã bệnh nhân..."
                className="w-full rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm text-[#0f172a] caret-teal-600 outline-none placeholder:text-slate-500 focus:border-teal-400"
              />
            </div>
            <div className="mt-2 max-h-32 overflow-y-auto rounded-xl border border-slate-200 bg-white">
              {patientResults.map((patient) => (
                <button
                  key={patient.id}
                  type="button"
                  onClick={() => choosePatient(patient)}
                  className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-teal-50"
                >
                  <span className="font-medium text-slate-800">
                    {patient.name || "Bệnh nhân không tên"}
                  </span>
                  <span className="text-xs text-slate-500">{patientCode(patient)}</span>
                </button>
              ))}
              {!patientResults.length && (
                <div className="px-3 py-3 text-sm text-slate-500">Không có kết quả.</div>
              )}
            </div>
          </div>
        )}

        <form onSubmit={handleSend} className="border-t border-slate-200 bg-slate-50 p-3">
          {attachedFile && (
            <div className="mb-2 flex items-center justify-between rounded-xl border border-teal-200 bg-teal-50 px-3 py-2 text-sm text-teal-800">
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
              className="rounded-xl border border-slate-200 bg-white p-3 text-slate-500 hover:border-teal-300 hover:text-teal-600"
              title="Attach MRI"
            >
              <Paperclip className="h-4 w-4" />
            </button>
            <textarea
              value={draftMessage}
              onChange={(event) => setDraftMessage(event.target.value)}
              placeholder="Hỏi Agent hoặc attach MRI để chạy chẩn đoán nhanh..."
              rows={2}
              className="max-h-28 min-h-11 flex-1 resize-none rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-[#0f172a] caret-teal-600 outline-none placeholder:text-slate-500 focus:border-teal-400"
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
              className="rounded-xl bg-teal-600 p-3 text-white shadow-lg shadow-teal-600/20 transition hover:bg-teal-500 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none"
              title="Gửi"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </button>
          </div>
          <button
            type="button"
            onClick={() => setShowPatientSearch((value) => !value)}
            className="mt-2 flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-teal-600"
          >
            <MessageSquareText className="h-3.5 w-3.5" />
            {selectedPatientId ? `Đang chọn ${selectedPatientId}` : "Chọn bệnh nhân"}
            <ChevronDown className="h-3.5 w-3.5" />
          </button>
        </form>
      </div>
    </section>
  );
}
