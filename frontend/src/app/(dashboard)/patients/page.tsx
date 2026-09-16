"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { apiService, api } from "@/lib/api";
import { Search, UserPlus, FileSpreadsheet, AlertTriangle, BadgeCheck, ChevronLeft, ChevronRight, X, Loader2, Download } from "lucide-react";

const LABEL_MAP: Record<string, string> = {
  class_0: "Glioma",
  class_1: "Meningioma",
  class_2: "Pituitary tumor",
};

function displayDiagnosis(label?: string | null) {
  if (!label) return "Chưa có";
  return LABEL_MAP[label] || label;
}

function hasPatientTumorDiagnosis(patient: any) {
  if (!patient) return false;
  return Boolean(patient.diagnosis || patient.aiDiagnosis || patient.classificationConfidence != null);
}

// ---------------------------------------------------------------------------
// Create Patient Modal
// ---------------------------------------------------------------------------
function CreatePatientModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [name, setName] = useState("");
  const [externalId, setExternalId] = useState("");
  const [age, setAge] = useState("");
  const [gender, setGender] = useState("M");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();

  if (!open) return null;

  const handleCreate = async () => {
    if (!name.trim()) {
      setError("Vui lòng nhập họ tên bệnh nhân.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const res = await apiService.patients.create({
        name: name.trim(),
        external_id: externalId.trim() || undefined,
        age: age ? parseInt(age) : undefined,
        gender,
      });
      const newId = res.data?.id || res.data?.patient_id;
      onClose();
      if (newId) {
        router.push(`/patients/${newId}`);
      } else {
        router.refresh();
      }
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Không thể tạo bệnh nhân. Vui lòng thử lại.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-2xl border border-slate-700 bg-slate-900 p-8 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold text-slate-100">Thêm bệnh nhân mới</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-100 transition-colors">
            <X className="h-5 w-5" />
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-500/10 text-red-400 text-sm border border-red-500/20">{error}</div>
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-400 mb-1.5">Họ và tên *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Nguyễn Văn A"
              className="w-full px-4 py-2.5 bg-slate-800 border border-slate-700 rounded-xl text-slate-100 focus:border-teal-500 outline-none transition-colors"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-400 mb-1.5">Mã bệnh nhân (External ID)</label>
            <input
              type="text"
              value={externalId}
              onChange={(e) => setExternalId(e.target.value)}
              placeholder="VD: UCSF-001"
              className="w-full px-4 py-2.5 bg-slate-800 border border-slate-700 rounded-xl text-slate-100 focus:border-teal-500 outline-none transition-colors"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-1.5">Tuổi</label>
              <input
                type="number"
                value={age}
                onChange={(e) => setAge(e.target.value)}
                placeholder="45"
                className="w-full px-4 py-2.5 bg-slate-800 border border-slate-700 rounded-xl text-slate-100 focus:border-teal-500 outline-none transition-colors"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-1.5">Giới tính</label>
              <select
                value={gender}
                onChange={(e) => setGender(e.target.value)}
                className="w-full px-4 py-2.5 bg-slate-800 border border-slate-700 rounded-xl text-slate-100 focus:border-teal-500 outline-none transition-colors"
              >
                <option value="M">Nam</option>
                <option value="F">Nữ</option>
              </select>
            </div>
          </div>
        </div>

        <div className="flex gap-3 mt-8">
          <button onClick={onClose} className="flex-1 py-2.5 rounded-xl border border-slate-700 text-slate-300 font-medium hover:bg-slate-800 transition-colors">
            Hủy
          </button>
          <button
            onClick={handleCreate}
            disabled={saving}
            className="flex-1 py-2.5 rounded-xl bg-teal-600 hover:bg-teal-500 text-white font-bold shadow-lg shadow-teal-500/20 disabled:opacity-50 transition-all flex items-center justify-center gap-2"
          >
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            Tạo bệnh nhân
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Patients Page
// ---------------------------------------------------------------------------
export default function PatientsPage() {
  const router = useRouter();
  const [patients, setPatients] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [exporting, setExporting] = useState(false);

  const handleExportData = async () => {
    setExporting(true);
    try {
      const response = await api.get("/records/export/research-data", {
        responseType: "blob",
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", "research_clinical_validation_data.csv");
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (error) {
      console.error("Export failed:", error);
      alert("Xuất dữ liệu thất bại.");
    } finally {
      setExporting(false);
    }
  };

  // Pagination State
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize] = useState(10);

  useEffect(() => {
    apiService.patients.getAll().then(res => {
      setPatients(res.data);
      setLoading(false);
    }).catch(err => {
      console.error(err);
      setPatients([]);
      setLoading(false);
    });
  }, []);

  // Reset to page 1 whenever search query changes
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery]);

  // Search Logic
  const filteredPatients = patients.filter(p => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      (p.name && p.name.toLowerCase().includes(q)) ||
      (p.external_id && p.external_id.toLowerCase().includes(q)) ||
      (p.id && String(p.id).toLowerCase().includes(q))
    );
  });

  // Pagination Logic
  const totalItems = filteredPatients.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  
  const startIndex = (currentPage - 1) * pageSize;
  const endIndex = Math.min(startIndex + pageSize, totalItems);
  const currentPatients = filteredPatients.slice(startIndex, endIndex);

  const handlePageChange = (page: number) => {
    if (page >= 1 && page <= totalPages) {
      setCurrentPage(page);
    }
  };

  // Helper for rendering AI Risk Bar in table
  const renderRiskBar = (score: number) => {
    let colorClass = "bg-teal-500 shadow-[0_0_8px_rgba(20,184,166,0.5)]";
    if (score > 70) colorClass = "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]";
    else if (score > 30) colorClass = "bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]";

    return (
      <div className="flex items-center gap-3">
        <div className="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden">
          <div className={`h-full rounded-full ${colorClass}`} style={{ width: `${score}%` }}></div>
        </div>
        <span className="text-sm font-bold text-slate-300 w-6">{score}</span>
      </div>
    );
  };

  // Helper for Status Badge
  const renderStatusBadge = (diagnosis?: string) => {
    const label = displayDiagnosis(diagnosis);
    let bgClasses = "bg-slate-800 text-slate-400 border border-slate-700";
    if (label.includes("Không phát hiện")) {
      bgClasses = "bg-emerald-500/10 text-emerald-600 dark:text-emerald-300 border border-emerald-500/20";
    } else if (label.includes("Rủi ro cao") || label.includes("GBM") || label.includes("Glioma")) {
      bgClasses = "bg-red-500/10 text-red-600 dark:text-red-400 border border-red-500/20";
    } else if (label.includes("Meningioma") || label.includes("Aneurysm")) {
      bgClasses = "bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20";
    } else if (label.includes("Sclerosis")) {
      bgClasses = "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20";
    }
    
    return (
      <span className={`px-2.5 py-1 text-xs font-semibold rounded-md ${bgClasses}`}>
        {label}
      </span>
    );
  };

  const reviewText = (status?: string) => {
    if (status === "needs_review") return "Cần xem xét";
    if (status === "confirmed") return "Đã xác nhận";
    if (status === "corrected") return "Đã chỉnh";
    if (status === "not_required") return "Tin cậy cao";
    return "Chưa chẩn đoán";
  };

  return (
    <div className="flex h-full min-w-0 flex-col space-y-6">
      
      {/* Search and Action Bar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full max-w-xl">
          <Search className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            placeholder="Tìm kiếm ID, Tên, hoặc DOB (YYYY-MM-DD)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-xl border border-slate-800 bg-slate-900 py-3 pl-10 pr-4 text-sm text-slate-200 placeholder:text-slate-500 focus:border-teal-500 focus:outline-none focus:ring-1 focus:ring-teal-500 transition-all shadow-sm"
          />
        </div>
        
        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:gap-3">
          <button 
            onClick={handleExportData}
            disabled={exporting}
            className="flex items-center justify-center gap-2 rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm font-semibold text-slate-300 transition-all hover:bg-slate-700 active:scale-95 disabled:opacity-50"
          >
            {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            Xuất dữ liệu đánh giá (CSV)
          </button>
          
          <button 
            onClick={() => setShowCreateModal(true)}
            className="flex items-center justify-center gap-2 rounded-xl bg-teal-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-teal-500/20 transition-all hover:bg-teal-500 active:scale-95"
          >
            <UserPlus className="h-4 w-4" />
            Thêm bệnh nhân mới
          </button>
        </div>
      </div>

      {/* Main Table Area */}
      <div className="flex-1 rounded-2xl border border-slate-800 bg-slate-900 backdrop-blur-sm overflow-hidden flex flex-col shadow-xl">
        
        {/* Table Container */}
        <div className="flex-1 overflow-auto custom-scrollbar">
          <table className="w-full min-w-[920px] text-left text-sm text-slate-400">
            <thead className="bg-slate-950/40 text-xs uppercase font-semibold text-slate-500 sticky top-0 z-10 shadow-sm border-b border-slate-800">
              <tr>
                <th className="px-6 py-4">Mã BN</th>
                <th className="px-6 py-4">Họ và tên</th>
                <th className="px-6 py-4">Tuổi/Giới tính</th>
                <th className="px-6 py-4">Lần khám cuối</th>
                <th className="px-6 py-4">Chẩn đoán chính</th>
                <th className="px-6 py-4">Điểm rủi ro AI</th>
                <th className="px-6 py-4 text-center">Thao tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-slate-500">
                    <div className="inline-flex items-center gap-2">
                       <div className="h-4 w-4 rounded-full border-2 border-t-teal-500 border-slate-700 animate-spin" />
                       Đang tải dữ liệu...
                    </div>
                  </td>
                </tr>
              ) : currentPatients.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-slate-500">
                    {searchQuery ? `Không tìm thấy bệnh nhân nào khớp với "${searchQuery}"` : "Chưa có dữ liệu bệnh nhân."}
                  </td>
                </tr>
              ) : currentPatients.map((p, idx) => {
                const hasTumorDiagnosis = hasPatientTumorDiagnosis(p);
                return (
                <tr key={p.id || idx} className="hover:bg-slate-800/20 transition-colors group cursor-pointer">
                  <td className="px-6 py-4 font-mono text-slate-500">{p.external_id || p.id}</td>
                  <td className="px-6 py-4 font-medium text-slate-200">{p.name || `Bệnh nhân #${p.id}`}</td>
                  <td className="px-6 py-4 text-slate-300">{p.age ?? '—'} / {p.gender ?? '—'}</td>
                  <td className="px-6 py-4 text-slate-400">{p.lastVisit ? (() => { let d = p.lastVisit; if (d && !d.endsWith("Z") && !d.includes("+") && d.includes("T")) d += "Z"; return new Date(d).toLocaleDateString("vi-VN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }); })() : '—'}</td>
                  <td className="px-6 py-4">
                    <div className="flex flex-col items-start gap-1">
                      {renderStatusBadge(hasTumorDiagnosis ? p.diagnosis : undefined)}
                      <span
                        className={`text-[11px] font-semibold ${
                          p.reviewStatus === "needs_review"
                            ? "text-amber-600 dark:text-amber-400"
                            : p.reviewStatus === "corrected"
                              ? "text-indigo-600 dark:text-violet-450 dark:text-violet-400"
                              : "text-slate-500"
                        }`}
                      >
                        {p.no_tumor_detected ? "Không có khối u" : hasTumorDiagnosis ? reviewText(p.reviewStatus) : "Chưa chẩn đoán"}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    {p.no_tumor_detected ? <span className="text-slate-500">Không áp dụng</span> : hasTumorDiagnosis && p.riskScore != null ? renderRiskBar(p.riskScore) : <span className="text-slate-500">—</span>}
                  </td>
                  <td className="px-6 py-4 text-center">
                    <button 
                      onClick={() => router.push(`/patients/${p.id}`)}
                      className="text-teal-500 font-semibold hover:text-teal-400 opacity-80 group-hover:opacity-100 transition-opacity"
                    >
                      Xem chi tiết
                    </button>
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination Footer */}
        <div className="flex flex-col gap-3 border-t border-slate-800 bg-slate-950/30 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <span className="text-sm text-slate-500">
            Hiển thị <span className="font-semibold text-slate-300">{totalItems > 0 ? startIndex + 1 : 0}</span> đến <span className="font-semibold text-slate-300">{endIndex}</span> trong <span className="font-semibold text-slate-300">{totalItems}</span> bệnh nhân
          </span>
          <div className="flex flex-wrap items-center gap-1">
            <button 
              onClick={() => handlePageChange(currentPage - 1)}
              disabled={currentPage === 1}
              className="p-2 rounded-lg text-slate-500 hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            
            {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
              <button
                key={page}
                onClick={() => handlePageChange(page)}
                className={`w-8 h-8 rounded-lg font-medium text-sm transition-all ${
                  currentPage === page 
                    ? "bg-teal-600 text-white shadow-md shadow-teal-500/20" 
                    : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                }`}
              >
                {page}
              </button>
            ))}

            <button 
              onClick={() => handlePageChange(currentPage + 1)}
              disabled={currentPage === totalPages}
              className="p-2 rounded-lg text-slate-400 hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Bottom KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* KPI 1 */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5 flex items-center justify-between shadow-lg relative overflow-hidden group">
          <div className="absolute top-0 right-0 w-32 h-32 bg-teal-500/5 blur-3xl rounded-full translate-x-1/2 -translate-y-1/2 group-hover:bg-teal-500/10 transition-colors"></div>
          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-1 block">Ca khám đang thực hiện</span>
            <span className="text-3xl font-bold text-slate-100 flex items-center gap-3">
               1,284
            </span>
          </div>
          <div className="h-12 w-12 rounded-xl bg-teal-500/10 flex items-center justify-center border border-teal-500/20 text-teal-600 dark:text-teal-400">
             <FileSpreadsheet className="h-6 w-6" />
          </div>
        </div>

        {/* KPI 2 */}
        <div className="rounded-2xl border border-red-200 dark:border-red-900/30 bg-red-50 dark:bg-red-950/10 p-5 flex items-center justify-between shadow-lg relative overflow-hidden group hover:border-red-300 dark:hover:border-red-900/50 transition-colors">
          <div className="absolute top-0 right-0 w-32 h-32 bg-red-500/5 blur-3xl rounded-full translate-x-1/2 -translate-y-1/2"></div>
          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-1 block">Cần xem xét gấp</span>
            <span className="text-3xl font-bold text-slate-100 flex items-center gap-3">
               12
            </span>
          </div>
          <div className="h-12 w-12 rounded-xl bg-red-500/10 flex items-center justify-center border border-red-500/20 text-red-600 dark:text-red-500 animate-pulse">
             <AlertTriangle className="h-6 w-6" />
          </div>
        </div>

        {/* KPI 3 */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5 flex items-center justify-between shadow-lg relative overflow-hidden group">
          <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/5 blur-3xl rounded-full translate-x-1/2 -translate-y-1/2"></div>
          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-1 block">Độ tin cậy AI</span>
            <span className="text-3xl font-bold text-teal-600 dark:text-teal-400 drop-shadow-[0_0_8px_rgba(20,184,166,0.3)] flex items-center gap-3">
               98.4%
            </span>
          </div>
          <div className="h-12 w-12 rounded-xl bg-slate-800 flex items-center justify-center border border-slate-700 text-teal-600 dark:text-teal-500">
             <BadgeCheck className="h-6 w-6" />
          </div>
        </div>
      </div>

      {/* Create Patient Modal */}
      <CreatePatientModal open={showCreateModal} onClose={() => setShowCreateModal(false)} />
    </div>
  );
}
