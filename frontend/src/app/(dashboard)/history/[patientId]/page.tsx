"use client";

import { use, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { apiService, resolveMediaUrl } from "@/lib/api";
import { ArrowLeft, Download, Loader2, RefreshCw, Wand2 } from "lucide-react";
import { ImagePreviewModal, ImagePreviewState } from "@/components/ui/ImagePreviewModal";

function formatDate(value?: string | null) {
  if (!value) return "--";
  return new Date(value).toLocaleString("vi-VN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatPercent(value?: number | null) {
  if (value == null) return "--";
  return `${(value * 100).toFixed(2)}%`;
}

function formatScore(value?: number | null) {
  if (value == null) return "--";
  return value.toFixed(4);
}

function RiskTrendChart({ points }: { points: any[] }) {
  const valid = points.filter((point) => point.risk_score != null);
  const width = 760;
  const height = 260;
  const padding = 42;
  const maxScore = Math.max(1, ...valid.map((point) => Number(point.risk_score) || 0));
  const minScore = Math.min(0, ...valid.map((point) => Number(point.risk_score) || 0));
  const span = Math.max(0.1, maxScore - minScore);

  const coords = valid.map((point, index) => {
    const x = padding + (valid.length === 1 ? 0.5 : index / (valid.length - 1)) * (width - padding * 2);
    const y = height - padding - ((Number(point.risk_score) - minScore) / span) * (height - padding * 2);
    return { ...point, x, y };
  });

  const line = coords.map((point) => `${point.x},${point.y}`).join(" ");

  if (valid.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-2xl border border-slate-800 bg-slate-950/40 text-slate-500">
        Chưa có dữ liệu risk score để vẽ biểu đồ.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
      <svg viewBox={`0 0 ${width} ${height}`} className="min-w-[760px]">
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="var(--slate-400)" />
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} stroke="var(--slate-400)" />
        {[0, 1, 2, 3].map((tick) => {
          const y = padding + tick * ((height - padding * 2) / 3);
          const value = maxScore - tick * (span / 3);
          return (
            <g key={tick}>
              <line x1={padding} y1={y} x2={width - padding} y2={y} stroke="var(--slate-800)" />
              <text x={8} y={y + 4} fill="var(--slate-400)" fontSize="12">
                {value.toFixed(2)}
              </text>
            </g>
          );
        })}
        {coords.length > 1 && <polyline points={line} fill="none" stroke="#14b8a6" strokeWidth="3" />}
        {coords.map((point) => (
          <g key={point.diagnosis_index}>
            <circle
              cx={point.x}
              cy={point.y}
              r="6"
              fill={["high", "very high"].includes(String(point.risk_group).toLowerCase()) ? "#f97316" : "#10b981"}
              stroke="var(--slate-900)"
              strokeWidth="2"
            />
            <text x={point.x - 18} y={height - 16} fill="var(--slate-400)" fontSize="12">
              Lần {point.diagnosis_index}
            </text>
            <text x={point.x - 18} y={point.y - 12} fill="var(--slate-100)" fontSize="12" className="font-bold">
              {Number(point.risk_score).toFixed(2)}
            </text>
            <text x={point.x - 18} y={point.y + 20} fill="var(--slate-400)" fontSize="10">
              {point.risk_group || ""}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

export default function PatientHistoryReportPage({ params }: { params: Promise<{ patientId: string }> }) {
  const { patientId } = use(params);
  const router = useRouter();
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");
  const [previewImage, setPreviewImage] = useState<ImagePreviewState | null>(null);

  const loadReport = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await apiService.patients.getHistoryReport(patientId);
      setReport(res.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "Không thể tải báo cáo lịch sử.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReport();
  }, [patientId]);

  const timelineChronological = useMemo(() => {
    return [...(report?.timeline || [])].reverse();
  }, [report]);

  const handleGenerate = async () => {
    setGenerating(true);
    setError("");
    try {
      const res = await apiService.patients.regenerateHistoryReport(patientId);
      setReport(res.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "Không thể sinh nhận xét AI.");
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = async () => {
    setDownloading(true);
    setError("");
    try {
      const response = await apiService.patients.downloadHistoryReport(patientId);
      const blob = new Blob([response.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `patient_history_report_${patientId}.pdf`;
      link.click();
      setTimeout(() => window.URL.revokeObjectURL(url), 60000);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "Không thể xuất báo cáo PDF.");
    } finally {
      setDownloading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-[calc(100vh-6rem)] items-center justify-center">
        <Loader2 className="h-10 w-10 animate-spin text-teal-400" />
      </div>
    );
  }

  const patient = report?.patient || {};
  const texts = report?.texts || {};
  const ready = report?.report_status === "ready";

  return (
    <div className="flex flex-col space-y-6 pb-10">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <button
            onClick={() => router.push("/history")}
            className="mb-4 flex w-fit items-center gap-2 text-slate-400 transition-colors hover:text-teal-600 dark:hover:text-teal-400"
          >
            <ArrowLeft className="h-4 w-4" />
            Quay lại lịch sử
          </button>
          <h1 className="text-2xl font-bold text-slate-100">Báo cáo lịch sử chẩn đoán</h1>
          <p className="mt-1 text-sm text-slate-400">
            {patient.name || `Bệnh nhân ${patient.id}`} • Mã: {patient.external_id || patient.id}
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="inline-flex items-center gap-2 rounded-xl border border-teal-500/30 px-4 py-2.5 text-sm font-semibold text-teal-600 dark:text-teal-300 transition-colors hover:bg-teal-500/10 disabled:opacity-50"
          >
            {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
            {ready ? "Sinh lại nhận xét AI" : "Sinh nhận xét AI"}
          </button>
          <button
            onClick={loadReport}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-100 transition-colors hover:bg-slate-800"
          >
            <RefreshCw className="h-4 w-4" />
            Làm mới
          </button>
          <button
            onClick={handleDownload}
            disabled={!ready || downloading}
            className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
          >
            {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            Xuất PDF
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {!ready && (
        <div className="rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-200">
          Nhận xét LLM chưa sẵn sàng hoặc dữ liệu đã thay đổi. Hãy bấm "Sinh nhận xét AI" để hoàn tất báo cáo.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-4">
          <div className="text-xs uppercase text-slate-500">Số lần chẩn đoán</div>
          <div className="mt-2 text-2xl font-bold text-slate-100">{report?.summary?.diagnosis_count || 0}</div>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-4">
          <div className="text-xs uppercase text-slate-500">Kết quả gần nhất</div>
          <div className="mt-2 text-lg font-bold text-slate-100">{report?.summary?.latest_tumor_label || "--"}</div>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-4">
          <div className="text-xs uppercase text-slate-500">Risk score</div>
          <div className="mt-2 text-lg font-bold text-slate-100">{formatScore(report?.summary?.latest_risk_score)}</div>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-4">
          <div className="text-xs uppercase text-slate-500">Risk group</div>
          <div className="mt-2 text-lg font-bold text-slate-100">
            {report?.summary?.latest_no_tumor_detected ? "Không áp dụng" : report?.summary?.latest_risk_group || "N/A"}
          </div>
        </div>
      </div>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6">
        <h2 className="mb-3 text-lg font-bold text-slate-100">1. Tóm tắt lịch sử chẩn đoán</h2>
        <p className="leading-relaxed text-slate-300">{texts.summary_text || "Chưa có nhận xét AI."}</p>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6">
        <h2 className="mb-4 text-lg font-bold text-slate-100">2. Timeline các lần chẩn đoán</h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[920px] text-left text-sm">
            <thead className="border-b border-slate-800 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-3 py-3">Lần</th>
                <th className="px-3 py-3">Ngày</th>
                <th className="px-3 py-3">Ảnh MRI</th>
                <th className="px-3 py-3">Loại dữ liệu</th>
                <th className="px-3 py-3">Phân loại</th>
                <th className="px-3 py-3">Confidence</th>
                <th className="px-3 py-3">Risk</th>
                <th className="px-3 py-3">Trạng thái</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {timelineChronological.map((item: any, index: number) => (
                <tr key={item.image_id} className="text-slate-300">
                  <td className="px-3 py-4 font-semibold">Lần {index + 1}</td>
                  <td className="px-3 py-4 text-slate-400">{formatDate(item.scan_date)}</td>
                  <td className="px-3 py-4">
                    {item.image_url ? (
                      <button
                        type="button"
                        onClick={() =>
                          setPreviewImage({
                            title: `MRI lần ${index + 1} - ảnh #${item.image_id}`,
                            src: resolveMediaUrl(item.image_url),
                          })
                        }
                        className="group relative h-16 w-16 overflow-hidden rounded-lg border border-slate-700"
                        title="Phóng to ảnh MRI"
                      >
                        <img
                          src={resolveMediaUrl(item.image_url)}
                          alt={`MRI ${item.image_id}`}
                          className="h-full w-full object-cover transition-transform group-hover:scale-105"
                        />
                      </button>
                    ) : (
                      <div className="flex h-16 w-16 items-center justify-center rounded-lg border border-slate-700 text-xs text-slate-500">
                        N/A
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-4">
                    {item.modality}
                    {item.is_series ? <div className="text-xs text-slate-500">Slice {item.key_slice_index}</div> : null}
                  </td>
                  <td className="px-3 py-4">
                    {item.no_tumor_detected ? "Không phát hiện khối u" : item.tumor_label || "--"}
                  </td>
                  <td className="px-3 py-4">{formatPercent(item.classification_confidence)}</td>
                  <td className="px-3 py-4">
                    <div>{formatScore(item.risk_score)}</div>
                    <div className="text-xs uppercase text-slate-500">
                      {item.no_tumor_detected ? "Không áp dụng" : item.risk_group || "N/A"}
                    </div>
                  </td>
                  <td className="px-3 py-4 uppercase">{item.ai_status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6">
        <h2 className="mb-3 text-lg font-bold text-slate-100">3. Diễn tiến kết quả phân loại u</h2>
        <p className="leading-relaxed text-slate-300">{texts.classification_trend_text || "Chưa có nhận xét AI."}</p>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6">
        <h2 className="mb-4 text-lg font-bold text-slate-100">4. Biểu đồ diễn tiến tiên lượng theo thời gian</h2>
        <RiskTrendChart points={report?.risk_trend || []} />
        {(report?.no_tumor_risk_notes || []).length > 0 && (
          <div className="mt-4 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-4 text-sm text-emerald-600 dark:text-emerald-200">
            {(report.no_tumor_risk_notes || []).map((note: any) => (
              <div key={`${note.diagnosis_index}-${note.scan_date}`}>{note.message}</div>
            ))}
          </div>
        )}
        <p className="mt-4 leading-relaxed text-slate-300">{texts.risk_trend_text || "Chưa có nhận xét AI."}</p>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6">
        <h2 className="mb-4 text-lg font-bold text-slate-100">5. Dữ liệu đa mô thức đã sử dụng</h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            ["MRI", report?.multimodal_data?.has_mri],
            ["WSI", report?.multimodal_data?.has_wsi],
            ["RNA-seq", report?.multimodal_data?.has_rna],
            ["Clinical", report?.multimodal_data?.has_clinical],
          ].map(([label, active]) => (
            <div key={String(label)} className="rounded-xl border border-slate-800 bg-slate-950/40 p-4">
              <div className="text-xs uppercase text-slate-500">{label}</div>
              <div className={`mt-2 font-bold ${active ? "text-emerald-600 dark:text-emerald-300" : "text-slate-500"}`}>
                {active ? "Có dữ liệu" : "Chưa có"}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6">
        <h2 className="mb-4 text-lg font-bold text-slate-100">6. Đánh giá chuyên gia</h2>
        {(report?.expert_validations || []).length === 0 ? (
          <p className="text-slate-500">Chưa có đánh giá chuyên gia nào được ghi nhận cho bệnh nhân này.</p>
        ) : (
          <div className="space-y-3">
            {report.expert_validations.map((item: any, index: number) => (
              <div key={`${item.image_id}-${index}`} className="rounded-xl border border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-300">
                <div className="font-semibold text-slate-100">Lần ảnh #{item.image_id} • Rating {item.rating}/5</div>
                <div className="text-slate-500">{formatDate(item.created_at)}</div>
                <div className="mt-2">{item.comments || "Không có nhận xét."}</div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6">
        <h2 className="mb-3 text-lg font-bold text-slate-100">7. Kết luận tổng hợp</h2>
        <p className="leading-relaxed text-slate-300">{texts.conclusion_text || "Chưa có nhận xét AI."}</p>
      </section>

      {previewImage && <ImagePreviewModal preview={previewImage} onClose={() => setPreviewImage(null)} />}
    </div>
  );
}
