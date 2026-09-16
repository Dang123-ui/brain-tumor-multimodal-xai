"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  BrainCircuit,
  FileImage,
  ImagePlus,
  Loader2,
  Stethoscope,
  X,
} from "lucide-react";
import { neuroboardApi } from "@/lib/neuroboardApi";
import type { NeuroCaseOption, NeuroPost, NeuroPostType } from "./types";

type Props = {
  onCreated: (post: NeuroPost) => void;
};

function errorMessage(error: unknown) {
  const candidate = error as { response?: { data?: { detail?: string } }; message?: string };
  return candidate.response?.data?.detail || candidate.message || "Không thể tạo bài đăng.";
}

function avatarText(username?: string) {
  return (username || "me").slice(0, 2).toUpperCase();
}

function formatCaseDate(value?: string | null) {
  if (!value) return "Chưa có thời gian";
  return new Intl.DateTimeFormat("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date(value));
}

function caseTumorLabel(item: NeuroCaseOption) {
  if (item.no_tumor_detected) return "Không phát hiện u";
  return item.ai_label || "Chưa có nhãn";
}

function caseConfidence(item: NeuroCaseOption) {
  return typeof item.confidence === "number"
    ? `${(item.confidence * 100).toFixed(2)}%`
    : "Chưa có confidence";
}

function caseSearchText(item: NeuroCaseOption) {
  return [
    item.patient_external_id,
    item.patient_name,
    item.image_id,
    caseTumorLabel(item),
    caseConfidence(item),
    formatCaseDate(item.analysis_created_at || item.scan_date),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

export function NeuroBoardComposer({ onCreated }: Props) {
  const [postType, setPostType] = useState<NeuroPostType>("normal");
  const [content, setContent] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [currentUsername, setCurrentUsername] = useState<string>();
  const [caseOptions, setCaseOptions] = useState<NeuroCaseOption[]>([]);
  const [selectedImageId, setSelectedImageId] = useState<number>();
  const [caseSearch, setCaseSearch] = useState("");
  const [loadingCases, setLoadingCases] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string>();
  const inputRef = useRef<HTMLInputElement>(null);

  const previews = useMemo(
    () => files.map((file) => ({ file, url: URL.createObjectURL(file) })),
    [files],
  );

  useEffect(() => {
    return () => previews.forEach((preview) => URL.revokeObjectURL(preview.url));
  }, [previews]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      neuroboardApi
        .getMe()
        .then((response) => setCurrentUsername(response.data.username))
        .catch(() => setCurrentUsername(undefined));
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, []);

  useEffect(() => {
    if (postType !== "clinical_case" || caseOptions.length) return;
    const timeoutId = window.setTimeout(() => {
      setLoadingCases(true);
      neuroboardApi
        .getCaseOptions()
        .then((response) => setCaseOptions(response.data.items || []))
        .catch((requestError) => setError(errorMessage(requestError)))
        .finally(() => setLoadingCases(false));
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [postType, caseOptions.length]);

  const selectedCase = caseOptions.find((item) => item.image_id === selectedImageId);
  const filteredCaseOptions = useMemo(() => {
    const query = caseSearch.trim().toLowerCase();
    if (!query) return caseOptions;
    return caseOptions.filter((item) => caseSearchText(item).includes(query));
  }, [caseOptions, caseSearch]);
  const canSubmit =
    !submitting &&
    (postType === "clinical_case"
      ? Boolean(selectedImageId)
      : Boolean(content.trim() || files.length));

  const addFiles = (incoming: FileList | null) => {
    if (!incoming) return;
    setError(undefined);
    const next = [...files, ...Array.from(incoming)].slice(0, 6);
    if (files.length + incoming.length > 6) {
      setError("Mỗi bài đăng chỉ được tối đa 6 ảnh.");
    }
    setFiles(next);
    if (inputRef.current) inputRef.current.value = "";
  };

  const submit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(undefined);
    try {
      const response = await neuroboardApi.createPost({
        postType,
        content,
        imageId: postType === "clinical_case" ? selectedImageId : undefined,
        files,
      });
      onCreated(response.data);
      setContent("");
      setFiles([]);
      setSelectedImageId(undefined);
      setCaseSearch("");
      setPostType("normal");
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="rounded-md border border-[#90CAF9] bg-white shadow-sm">
      <div className="flex items-center gap-3 border-b border-[#E3F2FD] p-4">
        <div
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#E3F2FD] text-sm font-bold text-[#0D47A1] ring-1 ring-[#90CAF9]"
          title={currentUsername || "Tài khoản hiện tại"}
        >
          {avatarText(currentUsername)}
        </div>
        <textarea
          value={content}
          onChange={(event) => setContent(event.target.value)}
          rows={2}
          placeholder={
            postType === "clinical_case"
              ? "Mô tả vấn đề cần cộng đồng trao đổi..."
              : "Chia sẻ thông tin hoặc trao đổi chuyên môn..."
          }
          className="min-h-12 flex-1 resize-none rounded-md border border-[#90CAF9] bg-white px-4 py-3 text-sm text-[#0F172A] outline-none placeholder:text-slate-500 focus:border-[#2196F3] focus:ring-2 focus:ring-[#90CAF9]/50"
        />
      </div>

      <div className="flex flex-wrap items-center gap-2 px-4 pt-3">
        <button
          type="button"
          onClick={() => setPostType("normal")}
          className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium ${
            postType === "normal"
              ? "bg-[#E3F2FD] text-[#0D47A1]"
              : "text-[#64748B] hover:bg-[#E3F2FD]"
          }`}
        >
          <FileImage className="h-4 w-4" />
          Bài đăng thường
        </button>
        <button
          type="button"
          onClick={() => setPostType("clinical_case")}
          className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium ${
            postType === "clinical_case"
              ? "bg-[#E3F2FD] text-[#0D47A1]"
              : "text-[#64748B] hover:bg-[#E3F2FD]"
          }`}
        >
          <Stethoscope className="h-4 w-4" />
          Clinical Case
        </button>
      </div>

      {postType === "clinical_case" && (
        <div className="mx-4 mt-3 rounded-md border border-[#90CAF9] bg-[#E3F2FD] p-3">
          <label className="mb-2 block text-xs font-semibold uppercase text-[#0D47A1]">
            MRI đã phân tích
          </label>
          <div className="rounded-md border border-[#90CAF9] bg-white p-2">
            <div className="relative">
              <input
                type="search"
                value={caseSearch}
                onChange={(event) => setCaseSearch(event.target.value)}
                disabled={loadingCases}
                placeholder={loadingCases ? "Đang tải MRI..." : "Tìm theo mã bệnh nhân, tên, nhãn u hoặc Image ID..."}
                className="w-full rounded-md border border-[#E2E8F0] bg-white px-3 py-2.5 pr-9 text-sm text-[#0F172A] outline-none placeholder:text-[#64748B] focus:border-[#2196F3] focus:ring-2 focus:ring-[#90CAF9]/50"
              />
              {loadingCases && (
                <Loader2 className="absolute right-3 top-3 h-4 w-4 animate-spin text-[#2196F3]" />
              )}
            </div>
            <div className="mt-2 max-h-72 space-y-2 overflow-y-auto pr-1">
              {!loadingCases && filteredCaseOptions.length === 0 && (
                <p className="rounded-md bg-[#F8FAFC] px-3 py-3 text-sm text-[#64748B]">
                  Không tìm thấy MRI phù hợp.
                </p>
              )}
              {filteredCaseOptions.map((item) => {
                const active = item.image_id === selectedImageId;
                const displayTime = formatCaseDate(item.analysis_created_at || item.scan_date);
                return (
                  <button
                    key={item.image_id}
                    type="button"
                    onClick={() => setSelectedImageId(item.image_id)}
                    className={`w-full rounded-md border px-3 py-3 text-left transition ${
                      active
                        ? "border-[#0D47A1] bg-[#E3F2FD] ring-2 ring-[#90CAF9]/70"
                        : "border-[#E2E8F0] bg-white hover:border-[#2196F3] hover:bg-[#F6FAFD]"
                    }`}
                  >
                    <div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-[#0F172A]">
                      <span>{item.patient_external_id || `BN ${item.patient_id}`}</span>
                      <span className="text-[#64748B]">--</span>
                      <span>{item.patient_name || "Chưa có tên"}</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2 text-xs">
                      <span className="rounded bg-[#E3F2FD] px-2 py-1 font-semibold text-[#0D47A1]">
                        Image {item.image_id}
                      </span>
                      <span className="rounded bg-[#F8FAFC] px-2 py-1 font-semibold text-[#0F172A]">
                        {caseTumorLabel(item)}
                      </span>
                      <span className="rounded bg-[#F8FAFC] px-2 py-1 text-[#0F172A]">
                        Confidence {caseConfidence(item)}
                      </span>
                      <span className="rounded bg-[#F8FAFC] px-2 py-1 text-[#64748B]">
                        {displayTime}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
          {selectedCase && (
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-[#0F172A]">
              <span className="rounded bg-white px-2 py-1 font-semibold">
                {selectedCase.patient_external_id || `BN ${selectedCase.patient_id}`} -- {selectedCase.patient_name || "Chưa có tên"}
              </span>
              <span className="rounded bg-white px-2 py-1 font-semibold">
                Image {selectedCase.image_id}
              </span>
              <span className="rounded bg-white px-2 py-1">
                {selectedCase.no_tumor_detected ? "Không phát hiện khối u" : selectedCase.ai_label || "Chưa có nhãn"}
              </span>
              {typeof selectedCase.confidence === "number" && (
                <span className="rounded bg-white px-2 py-1">
                  {(selectedCase.confidence * 100).toFixed(2)}%
                </span>
              )}
              <span className="flex items-center gap-1 text-[#0D47A1]">
                <BrainCircuit className="h-3.5 w-3.5" />
                Danh tính chỉ hiển thị với người tạo bài
              </span>
            </div>
          )}
        </div>
      )}

      {previews.length > 0 && (
        <div className="grid grid-cols-3 gap-2 px-4 pt-3 sm:grid-cols-6">
          {previews.map((preview, index) => (
            <div key={`${preview.file.name}-${index}`} className="relative aspect-square overflow-hidden rounded-md bg-[#E3F2FD]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={preview.url} alt={preview.file.name} className="h-full w-full object-cover" />
              <button
                type="button"
                onClick={() => setFiles((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                className="absolute right-1 top-1 rounded-full bg-[#0F172A]/75 p-1 text-white"
                title="Bỏ ảnh"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      {error && <p className="px-4 pt-3 text-sm text-red-600">{error}</p>}

      <div className="mt-3 flex items-center justify-between border-t border-[#E3F2FD] px-4 py-3">
        <div>
          <input
            ref={inputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            multiple
            className="hidden"
            onChange={(event) => addFiles(event.target.files)}
          />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-[#0D47A1] hover:bg-[#E3F2FD]"
          >
            <ImagePlus className="h-5 w-5" />
            Thêm ảnh
          </button>
        </div>
        <button
          type="button"
          disabled={!canSubmit}
          onClick={() => void submit()}
          className="neuro-post-button"
        >
          {submitting ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : (
            <div className="svg-wrapper-1">
              <div className="svg-wrapper">
                <svg height="24" width="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                  <path d="M0 0h24v24H0z" fill="none" />
                  <path
                    d="M1.946 9.315c-.522-.174-.527-.455.01-.634l19.087-6.362c.529-.176.832.12.684.638l-5.454 19.086c-.15.529-.455.547-.679.045L12 14l6-8-8 6-8.054-2.685z"
                    fill="currentColor"
                  />
                </svg>
              </div>
            </div>
          )}
          <span>Post</span>
        </button>
      </div>
    </section>
  );
}
