"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ImagePlus,
  Loader2,
  MessageCircle,
  Minus,
  Paperclip,
  Reply,
  Search,
  Send,
  Stethoscope,
  X,
} from "lucide-react";
import { neuroboardApi } from "@/lib/neuroboardApi";
import type {
  NeuroDoctor,
  NeuroMessage,
  NeuroMessengerCase,
} from "./types";

type Props = {
  attachCase?: NeuroMessengerCase | null;
  onAttachCaseConsumed?: () => void;
};

function initials(name: string) {
  const parts = name.split(" ").filter(Boolean).slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase()).join("") || "DR";
}

function confidenceText(value?: number | null) {
  return typeof value === "number" ? `${(value * 100).toFixed(0)}%` : "--";
}

function caseTitle(item: NeuroMessengerCase) {
  return item.patient_external_id || `CASE-${String(item.image_id).padStart(4, "0")}`;
}

function resultHref(item: NeuroMessengerCase) {
  const params = new URLSearchParams({ imageId: String(item.image_id) });
  return `/results/${item.patient_id}?${params.toString()}`;
}

function timeText(value?: string | null) {
  if (!value) return "";
  return new Intl.DateTimeFormat("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit",
  }).format(new Date(value));
}

function messagePreview(message: NeuroMessage) {
  if (message.content) return message.content;
  if (message.case) return caseTitle(message.case);
  if (message.image_url) return message.image_original_name || "Image";
  return "Tin nhắn";
}

export function NeuroBoardRightRail({ attachCase, onAttachCaseConsumed }: Props) {
  const [doctors, setDoctors] = useState<NeuroDoctor[]>([]);
  const [doctorSearch, setDoctorSearch] = useState("");
  const [selectedDoctor, setSelectedDoctor] = useState<NeuroDoctor | null>(null);
  const [messages, setMessages] = useState<NeuroMessage[]>([]);
  const [messageSearch, setMessageSearch] = useState("");
  const [draft, setDraft] = useState("");
  const [caseOptions, setCaseOptions] = useState<NeuroMessengerCase[]>([]);
  const [pendingCase, setPendingCase] = useState<NeuroMessengerCase | null>(null);
  const [pendingImage, setPendingImage] = useState<File | null>(null);
  const [replyTo, setReplyTo] = useState<NeuroMessage | null>(null);
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string>();
  const [casePickerOpen, setCasePickerOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [error, setError] = useState<string>();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const filteredDoctors = useMemo(() => {
    const query = doctorSearch.trim().toLowerCase();
    if (!query) return doctors;
    return doctors.filter((doctor) =>
      `${doctor.display_name} ${doctor.username}`.toLowerCase().includes(query),
    );
  }, [doctors, doctorSearch]);

  const messageById = useMemo(() => new Map(messages.map((message) => [message.id, message])), [messages]);

  const pendingImageUrl = useMemo(
    () => (pendingImage ? URL.createObjectURL(pendingImage) : undefined),
    [pendingImage],
  );
  const selectedDoctorId = selectedDoctor?.id;

  const loadDoctors = useCallback(async (query = doctorSearch) => {
    const response = await neuroboardApi.getDoctors(query);
    setDoctors(response.data.items || []);
  }, [doctorSearch]);

  const loadConversation = useCallback(async (doctorId: number, search: string) => {
    setLoadingConversation(true);
    setError(undefined);
    try {
      const response = await neuroboardApi.getConversation(doctorId, search);
      setMessages(response.data.messages || []);
      setSelectedDoctor(response.data.conversation.doctor);
      await loadDoctors();
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    } catch {
      setError("Không thể tải hội thoại.");
    } finally {
      setLoadingConversation(false);
    }
  }, [loadDoctors]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadDoctors();
      neuroboardApi
        .getMyCases()
        .then((response) => setCaseOptions(response.data.items || []))
        .catch(() => setCaseOptions([]));
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadDoctors]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void loadDoctors(doctorSearch), 250);
    return () => window.clearTimeout(timeoutId);
  }, [doctorSearch, loadDoctors]);

  useEffect(() => {
    const intervalId = window.setInterval(() => void loadDoctors(doctorSearch), 12000);
    return () => window.clearInterval(intervalId);
  }, [doctorSearch, loadDoctors]);

  useEffect(() => {
    if (!selectedDoctorId) return;
    const timeoutId = window.setTimeout(() => void loadConversation(selectedDoctorId, messageSearch), 250);
    return () => window.clearTimeout(timeoutId);
  }, [messageSearch, selectedDoctorId, loadConversation]);

  useEffect(() => {
    if (!attachCase) return;
    const timeoutId = window.setTimeout(() => {
      setPendingCase(attachCase);
      onAttachCaseConsumed?.();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [attachCase, onAttachCaseConsumed]);

  useEffect(() => {
    if (!pendingImageUrl) return;
    return () => URL.revokeObjectURL(pendingImageUrl);
  }, [pendingImageUrl]);

  const openDoctor = (doctor: NeuroDoctor) => {
    setSelectedDoctor(doctor);
    setMessageSearch("");
    setDraft("");
    setReplyTo(null);
    setPendingImage(null);
    void loadConversation(doctor.id, "");
  };

  const send = async () => {
    if (!selectedDoctor || sending) return;
    if (!draft.trim() && !pendingCase && !pendingImage) return;
    setSending(true);
    setError(undefined);
    try {
      const response = await neuroboardApi.sendMessage(selectedDoctor.id, {
        content: draft.trim(),
        caseImageId: pendingCase?.image_id,
        image: pendingImage || undefined,
        replyToId: replyTo?.id,
      });
      setMessages((current) => [...current, response.data]);
      setDraft("");
      setPendingCase(null);
      setPendingImage(null);
      setReplyTo(null);
      await loadDoctors();
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    } catch {
      setError("Không thể gửi tin nhắn.");
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      <aside className="sticky top-24 hidden h-[calc(100vh-7rem)] min-h-0 flex-col rounded-md border border-[#90CAF9] bg-white shadow-sm lg:flex">
        <div className="border-b border-[#E3F2FD] p-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-bold uppercase tracking-wide text-[#0D47A1]">Bác sĩ</h2>
            <MessageCircle className="h-4 w-4 text-[#2196F3]" />
          </div>
          <div className="relative mt-3">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-[#64748B]" />
            <input
              value={doctorSearch}
              onChange={(event) => setDoctorSearch(event.target.value)}
              placeholder="Tìm bác sĩ..."
              className="w-full rounded-md border border-[#CBD5E1] bg-white py-2 pl-9 pr-3 text-sm outline-none focus:border-[#2196F3] focus:ring-2 focus:ring-[#90CAF9]/50"
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {pendingCase && (
            <div className="mb-2 rounded-md border border-[#90CAF9] bg-[#E3F2FD] px-3 py-2 text-xs text-[#0F172A]">
              <div className="font-bold text-[#0D47A1]">Chọn bác sĩ để gửi request</div>
              <div className="mt-1 truncate">{caseTitle(pendingCase)} · {confidenceText(pendingCase.confidence)}</div>
            </div>
          )}
          {filteredDoctors.map((doctor) => (
            <button
              key={doctor.id}
              type="button"
              onClick={() => openDoctor(doctor)}
              className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-left hover:bg-[#E3F2FD]"
            >
              <div className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#E3F2FD] text-xs font-bold text-[#0D47A1]">
                {initials(doctor.display_name)}
                {doctor.is_online && (
                  <span className="absolute bottom-0 right-0 h-3 w-3 rounded-full border-2 border-white bg-emerald-500" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold text-[#0F172A]">
                  {doctor.display_name}
                </div>
                <div className={`truncate text-xs ${doctor.unread_count > 0 ? "font-semibold text-red-600" : "text-[#64748B]"}`}>
                  {doctor.unread_count > 0
                    ? `${doctor.unread_count} chưa đọc`
                    : doctor.is_online
                      ? "Online"
                      : doctor.last_active_at
                        ? `Last active ${timeText(doctor.last_active_at)}`
                        : "Offline"}
                </div>
              </div>
              {doctor.unread_count > 0 && (
                <span className="min-w-5 rounded-full bg-red-500 px-2 py-0.5 text-center text-xs font-bold text-white shadow-sm">
                  {doctor.unread_count}
                </span>
              )}
            </button>
          ))}
          {filteredDoctors.length === 0 && (
            <p className="px-3 py-8 text-center text-sm text-[#64748B]">Không tìm thấy bác sĩ.</p>
          )}
        </div>
      </aside>

      {selectedDoctor && (
        <section className="fixed bottom-4 right-4 z-[80] flex h-[min(640px,calc(100vh-2rem))] w-[min(380px,calc(100vw-2rem))] flex-col overflow-hidden rounded-md border border-[#CBD5E1] bg-white shadow-2xl">
          <div className="flex items-center justify-between border-b border-[#E2E8F0] px-3 py-2">
            <button
              type="button"
              className="flex min-w-0 items-center gap-2 text-left"
              onClick={() => void loadConversation(selectedDoctor.id, messageSearch)}
            >
              <div className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#E3F2FD] text-xs font-bold text-[#0D47A1]">
                {initials(selectedDoctor.display_name)}
                {selectedDoctor.is_online && (
                  <span className="absolute bottom-0 right-0 h-3 w-3 rounded-full border-2 border-white bg-emerald-500" />
                )}
              </div>
              <div className="min-w-0">
                <div className="truncate text-sm font-bold text-[#0F172A]">
                  {selectedDoctor.display_name}
                </div>
                <div className="text-xs text-[#64748B]">
                  {selectedDoctor.is_online ? "Online" : "Offline"}
                </div>
              </div>
            </button>
            <div className="flex items-center gap-1 text-[#0D47A1]">
              <button type="button" className="rounded-full p-1.5 hover:bg-[#E3F2FD]" title="Thu gọn">
                <Minus className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => setSelectedDoctor(null)}
                className="rounded-full p-1.5 hover:bg-[#E3F2FD]"
                title="Đóng"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div className="border-b border-[#E2E8F0] p-2">
            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-[#64748B]" />
              <input
                value={messageSearch}
                onChange={(event) => setMessageSearch(event.target.value)}
                placeholder="Tìm trong hội thoại..."
                className="w-full rounded-md border border-[#E2E8F0] py-2 pl-9 pr-3 text-sm outline-none focus:border-[#2196F3]"
              />
            </div>
          </div>

          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto bg-[#F8FAFC] p-3">
            {loadingConversation && (
              <div className="flex justify-center py-6 text-[#64748B]">
                <Loader2 className="h-5 w-5 animate-spin" />
              </div>
            )}
            {messages.map((message) => {
              const repliedMessage = message.reply_to_id ? messageById.get(message.reply_to_id) : undefined;
              return (
              <div key={message.id} className={`flex ${message.is_mine ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[82%] rounded-2xl px-3 py-2 text-sm shadow-sm ${
                    message.is_mine
                      ? "rounded-br-sm bg-[#2563EB] text-white"
                      : "rounded-bl-sm bg-white text-[#0F172A]"
                  }`}
                >
                  {repliedMessage && (
                    <div className={`mb-2 rounded-md border-l-2 px-2 py-1 text-xs ${
                      message.is_mine ? "border-white/70 bg-white/10 text-white/90" : "border-[#2196F3] bg-[#E3F2FD] text-[#0F172A]"
                    }`}>
                      <div className="font-semibold">{repliedMessage.sender.display_name}</div>
                      <div className="line-clamp-2">{messagePreview(repliedMessage)}</div>
                    </div>
                  )}
                  {message.content && <p className="whitespace-pre-wrap">{message.content}</p>}
                  {message.image_url && (
                    <button
                      type="button"
                      onClick={() => setImagePreviewUrl(message.image_url || undefined)}
                      className="mt-2 block overflow-hidden rounded-md"
                      title="Xem ảnh"
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={message.image_url}
                        alt={message.image_original_name || "message image"}
                        className="max-h-52 object-cover"
                      />
                    </button>
                  )}
                  {message.case && (
                    <div className={`mt-2 rounded-md border p-2 ${message.is_mine ? "border-white/30 bg-white/10" : "border-[#90CAF9] bg-[#E3F2FD]"}`}>
                      <div className="text-xs font-bold">{caseTitle(message.case)}</div>
                      <div className="mt-1 text-xs">
                        {message.case.ai_label || "No label"} · {confidenceText(message.case.confidence)}
                      </div>
                      {message.case.thumbnail_url && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={message.case.thumbnail_url} alt={caseTitle(message.case)} className="mt-2 h-24 w-full rounded object-cover" />
                      )}
                      <a href={resultHref(message.case)} className="mt-2 inline-flex text-xs font-bold underline">
                        Open Case
                      </a>
                      {message.second_opinion && (
                        <div className="mt-2 text-[11px] font-semibold">
                          Second Opinion: {message.second_opinion.status}
                        </div>
                      )}
                    </div>
                  )}
                  <div className={`mt-1 flex items-center justify-between gap-3 text-[10px] ${message.is_mine ? "text-white/70" : "text-[#64748B]"}`}>
                    <span className="inline-flex items-center gap-1">
                      {timeText(message.created_at)}
                      {!message.is_mine && !message.read_at && (
                        <span className="font-bold text-red-500">Chưa đọc</span>
                      )}
                    </span>
                    <button
                      type="button"
                      onClick={() => setReplyTo(message)}
                      className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 font-semibold ${
                        message.is_mine ? "hover:bg-white/10" : "hover:bg-[#E3F2FD]"
                      }`}
                    >
                      <Reply className="h-3 w-3" />
                      Trả lời
                    </button>
                  </div>
                </div>
              </div>
              );
            })}
            <div ref={bottomRef} />
          </div>

          {error && <div className="px-3 py-1 text-xs text-red-600">{error}</div>}
          {replyTo && (
            <div className="flex items-center justify-between border-t border-[#E2E8F0] bg-white px-3 py-2 text-xs text-[#0F172A]">
              <div className="min-w-0">
                <div className="font-semibold text-[#0D47A1]">Trả lời {replyTo.sender.display_name}</div>
                <div className="truncate">{messagePreview(replyTo)}</div>
              </div>
              <button type="button" onClick={() => setReplyTo(null)} className="text-[#0D47A1]">
                <X className="h-4 w-4" />
              </button>
            </div>
          )}
          {pendingCase && (
            <div className="flex items-center justify-between border-t border-[#E2E8F0] bg-[#E3F2FD] px-3 py-2 text-xs text-[#0F172A]">
              <span className="font-semibold">Đính kèm {caseTitle(pendingCase)} · {confidenceText(pendingCase.confidence)}</span>
              <button type="button" onClick={() => setPendingCase(null)} className="text-[#0D47A1]">
                <X className="h-4 w-4" />
              </button>
            </div>
          )}
          {pendingImage && pendingImageUrl && (
            <div className="flex items-center gap-3 border-t border-[#E2E8F0] bg-white px-3 py-2 text-xs text-[#0F172A]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={pendingImageUrl} alt={pendingImage.name} className="h-12 w-12 rounded-md object-cover" />
              <div className="min-w-0 flex-1">
                <div className="font-semibold text-[#0D47A1]">Ảnh đã sẵn sàng</div>
                <div className="truncate">{pendingImage.name}</div>
              </div>
              <button type="button" onClick={() => setPendingImage(null)} className="text-[#0D47A1]">
                <X className="h-4 w-4" />
              </button>
            </div>
          )}
          {casePickerOpen && (
            <div className="max-h-48 overflow-y-auto border-t border-[#E2E8F0] bg-white p-2">
              {caseOptions.map((item) => (
                <button
                  key={item.image_id}
                  type="button"
                  onClick={() => {
                    setPendingCase(item);
                    setCasePickerOpen(false);
                  }}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm hover:bg-[#E3F2FD]"
                >
                  <Stethoscope className="h-4 w-4 text-[#0D47A1]" />
                  <span className="min-w-0 flex-1 truncate">{caseTitle(item)} · {item.ai_label || "No label"}</span>
                  <span className="text-xs text-[#64748B]">{confidenceText(item.confidence)}</span>
                </button>
              ))}
            </div>
          )}
          <div className="flex items-center gap-2 border-t border-[#E2E8F0] p-2">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) setPendingImage(file);
                if (fileInputRef.current) fileInputRef.current.value = "";
              }}
            />
            <button
              type="button"
              onClick={() => setCasePickerOpen((value) => !value)}
              className="rounded-full p-2 text-[#0D47A1] hover:bg-[#E3F2FD]"
              title="Đính kèm Clinical Case"
            >
              <Paperclip className="h-5 w-5" />
            </button>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="rounded-full p-2 text-[#0D47A1] hover:bg-[#E3F2FD]"
              title="Send image"
            >
              <ImagePlus className="h-5 w-5" />
            </button>
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
              placeholder="Aa..."
              className="min-w-0 flex-1 rounded-full bg-[#F1F5F9] px-4 py-2 text-sm outline-none focus:ring-2 focus:ring-[#90CAF9]"
            />
            <button
              type="button"
              disabled={sending}
              onClick={() => void send()}
              className="rounded-full p-2 text-[#0D47A1] hover:bg-[#E3F2FD] disabled:opacity-50"
              title="Gửi"
            >
              {sending ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
            </button>
          </div>
        </section>
      )}
      {imagePreviewUrl && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 p-4">
          <button
            type="button"
            onClick={() => setImagePreviewUrl(undefined)}
            className="absolute right-4 top-4 rounded-full bg-white p-2 text-[#0F172A] shadow-lg"
            title="Đóng"
          >
            <X className="h-5 w-5" />
          </button>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={imagePreviewUrl} alt="Preview" className="max-h-[88vh] max-w-[92vw] rounded-md object-contain shadow-2xl" />
        </div>
      )}
    </>
  );
}
