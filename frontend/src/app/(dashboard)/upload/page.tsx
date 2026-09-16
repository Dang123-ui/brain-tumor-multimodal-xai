"use client";

import type { ChangeEvent } from "react";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  UploadCloud,
  FileType,
  Clock,
  PlayCircle,
  Loader2,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import { api, apiService } from "@/lib/api";
import MriResultCard from "@/components/ai/MriResultCard";

const recentUploads = [
  { id: 1, name: "Study_MRI_442", time: "Hôm nay, 10:24", size: "420 MB", status: "READY" },
  { id: 2, name: "WSI_Pathology_09", time: "Hôm qua, 16:12", size: "1.8 GB", status: "READY" },
  { id: 3, name: "DICOM_Series_772", desc: "Đang trích xuất metadata...", status: "PROCESSING" },
  { id: 4, name: "Neuro_CT_X10", time: "24/10/2023", size: "85 MB", status: "READY" },
];

type UploadResultState = {
  kind: "idle" | "success" | "error";
  imageId?: number | string;
  patientId?: string;
  data?: any;
  error?: string;
};

type UploadTab = "dicom" | "rna" | "clinical" | "wsi";

const MRI_RESULT_STORAGE_KEY = "neuro_mri_upload_result";
const MRI_PATIENT_STORAGE_KEY = "neuro_mri_patient_id";

export default function UploadPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [activeTab, setActiveTab] = useState<UploadTab>("dicom");
  const [uploading, setUploading] = useState(false);
  const [patientId, setPatientId] = useState("");
  const [mriFiles, setMriFiles] = useState<File[]>([]);
  const [wsiFiles, setWsiFiles] = useState<File[]>([]);
  const [rnaFile, setRnaFile] = useState<File | null>(null);
  const [ki67, setKi67] = useState("");
  const [grade, setGrade] = useState("");
  const [idhMutation, setIdhMutation] = useState("");
  const [mgmtMethylation, setMgmtMethylation] = useState("");
  const [statusMsg, setStatusMsg] = useState({ text: "", type: "" });
  const [progress, setProgress] = useState<{ percent: number; status: string } | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadResultState>({ kind: "idle" });
  const [uploadedStatus, setUploadedStatus] = useState({
    mri: false,
    wsi: false,
    rna: false,
    clinical: false,
  });
  const [lastUploadedImageId, setLastUploadedImageId] = useState<number | string | null>(null);
  // Khi vào từ "Tải dữ liệu mới", ẩn nút pipeline cho đến khi user thực sự upload file mới
  const [requireNewUpload, setRequireNewUpload] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const queryPatientId = searchParams.get("patientId") || searchParams.get("patient_id");
    const queryTab = searchParams.get("tab");
    const forceNewUpload = searchParams.get("new") === "1";
    const savedResult = window.sessionStorage.getItem(MRI_RESULT_STORAGE_KEY);
    const savedPatientId = window.sessionStorage.getItem(MRI_PATIENT_STORAGE_KEY);

    if (forceNewUpload) {
      window.sessionStorage.removeItem(MRI_RESULT_STORAGE_KEY);
      setUploadResult({ kind: "idle" });
      setLastUploadedImageId(null);
      setProgress(null);
      setStatusMsg({ text: "", type: "" });
      // Yêu cầu upload mới, ẩn nút pipeline cho đến khi upload xong
      setRequireNewUpload(true);
    } else {
      setRequireNewUpload(false);
    }

    if (queryPatientId) {
      setPatientId(queryPatientId);
    } else if (savedPatientId) {
      setPatientId(savedPatientId);
    }

    if (queryTab === "dicom" || queryTab === "rna" || queryTab === "clinical" || queryTab === "wsi") {
      setActiveTab(queryTab);
    }

    if (forceNewUpload || !savedResult) {
      return;
    }

    try {
      const parsed = JSON.parse(savedResult);
      setUploadResult(parsed);
      if (!queryPatientId && parsed?.patientId) {
        setPatientId(parsed.patientId);
      }
    } catch {
      window.sessionStorage.removeItem(MRI_RESULT_STORAGE_KEY);
    }
  }, [searchParams]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (patientId.trim()) {
      window.sessionStorage.setItem(MRI_PATIENT_STORAGE_KEY, patientId);
    } else {
      window.sessionStorage.removeItem(MRI_PATIENT_STORAGE_KEY);
    }
  }, [patientId]);

  // Auto-check existing uploads from DB when patient ID changes
  useEffect(() => {
    const pid = patientId.trim();
    const queryTab = searchParams.get("tab");
    const forceNewUpload = searchParams.get("new") === "1";
    if (!pid) {
      setUploadedStatus({ mri: false, wsi: false, rna: false, clinical: false });
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const res = await api.get(`/records/patients/${encodeURIComponent(pid)}/upload-status`);
        const data = res.data;
        const hasMri = Boolean(data.has_mri);
        setUploadedStatus({
          mri: hasMri,
          wsi: Boolean(data.has_wsi),
          rna: Boolean(data.has_rna),
          clinical: Boolean(data.has_clinical),
        });
        
        // Nếu bệnh nhân đã có sẵn MRI trong DB, không yêu cầu upload mới nữa để cho phép chạy pipeline ngay lập tức
        if (hasMri) {
          setRequireNewUpload(false);
        }

        // Pre-fill clinical values if they exist
        if (data.clinical) {
          if (data.clinical.ki67_index != null) setKi67(String(data.clinical.ki67_index));
          if (data.clinical.grade) setGrade(String(data.clinical.grade));
          if (data.clinical.idh_mutation) setIdhMutation(String(data.clinical.idh_mutation));
          if (data.clinical.mgmt_methylation) setMgmtMethylation(String(data.clinical.mgmt_methylation));
        }
      } catch {
        // Patient not found or no data yet — ignore
      }
    }, 600);

    return () => clearTimeout(timer);
  }, [patientId, searchParams]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (uploadResult.kind === "idle") {
      window.sessionStorage.removeItem(MRI_RESULT_STORAGE_KEY);
      return;
    }
    window.sessionStorage.setItem(MRI_RESULT_STORAGE_KEY, JSON.stringify(uploadResult));
  }, [uploadResult]);

  const handleMriFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files.length > 0) {
      setMriFiles(Array.from(event.target.files));
    }
  };

  const handleRnaFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files.length > 0) {
      setRnaFile(event.target.files[0]);
    }
  };

  const handleWsiFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files.length > 0) {
      setWsiFiles(Array.from(event.target.files));
    }
  };

  const getErrorMessage = (err: any, fallback: string) => {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((item: any) => item.msg || JSON.stringify(item)).join(", ");
    }
    if (detail && typeof detail === "object") return JSON.stringify(detail);
    return err.message || fallback;
  };

  const resetMriCard = () => {
    setUploadResult({ kind: "idle" });
    setMriFiles([]);
    setStatusMsg({ text: "", type: "" });
    if (typeof window !== "undefined") {
      window.sessionStorage.removeItem(MRI_RESULT_STORAGE_KEY);
    }
  };

  const handleDownloadReport = async (imageId: string | number) => {
    try {
      const response = await apiService.analysis.downloadReport(imageId);
      const blob = new Blob([response.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `mri_report_${imageId}.pdf`;
      link.click();
      setTimeout(() => {
        window.URL.revokeObjectURL(url);
      }, 60000);
    } catch (err: any) {
      console.error("PDF Download Error:", err);
      alert(err.response?.data?.detail || "Lỗi tải báo cáo.");
    }
  };

  const handleUploadDicom = async () => {
    if (mriFiles.length === 0 || !patientId.trim()) {
      setStatusMsg({
        text: "Vui lòng nhập mã bệnh nhân và chọn ít nhất 1 file ảnh/MRI.",
        type: "error",
      });
      return;
    }

    setUploading(true);
    setStatusMsg({ text: "", type: "" });

    try {
      const isSeries = mriFiles.length > 1 || mriFiles[0].name.toLowerCase().endsWith(".zip");
      let imageId: string | number;

      if (isSeries) {
        setStatusMsg({ text: `Đang tải lên chuỗi ${mriFiles.length} ảnh...`, type: "success" });
        const uploadResponse = await apiService.upload.mriSeries(
          patientId.trim(), 
          mriFiles.length === 1 && mriFiles[0].name.toLowerCase().endsWith(".zip") ? mriFiles[0] : mriFiles
        );
        imageId = uploadResponse.data?.image_id;
      } else {
        setStatusMsg({ text: "Đang tải lên ảnh MRI...", type: "success" });
        const uploadResponse = await apiService.upload.mri(patientId.trim(), mriFiles[0]);
        imageId = uploadResponse.data?.image_id;
      }

      if (!imageId) {
        throw new Error("Upload thành công nhưng backend không trả về image_id.");
      }

      setLastUploadedImageId(imageId);
      setUploadedStatus(prev => ({ ...prev, mri: true }));
      // Upload mới thành công — cho phép hiện nút pipeline
      setRequireNewUpload(false);
      setStatusMsg({
        text: "Tải lên MRI thành công. Bạn có thể tải thêm dữ liệu khác hoặc bấm 'Chạy Tổng Hợp' ở dưới.",
        type: "success",
      });
      setMriFiles([]);
    } catch (err: any) {
      const errorText = `Lỗi upload MRI: ${getErrorMessage(err, "Không thể xử lý file MRI.")}`;
      setStatusMsg({ text: errorText, type: "error" });
    } finally {
      setUploading(false);
    }
  };

  const handleUploadWsi = async () => {
    if (wsiFiles.length === 0 || !patientId.trim()) {
      setStatusMsg({
        text: "Vui lòng nhập mã bệnh nhân và chọn file ZIP hoặc các tiles WSI.",
        type: "error",
      });
      return;
    }

    setUploading(true);
    setStatusMsg({ text: "", type: "" });

    try {
      setStatusMsg({ text: `Đang tải lên và lọc ${wsiFiles.length} tiles WSI bằng AI...`, type: "success" });
      const response = await apiService.upload.wsiSeries(
        patientId.trim(),
        wsiFiles.length === 1 && wsiFiles[0].name.toLowerCase().endsWith(".zip") ? wsiFiles[0] : wsiFiles
      );
      
      const { image_id, num_valid_tiles } = response.data;
      setLastUploadedImageId(image_id);
      setUploadedStatus(prev => ({ ...prev, wsi: true }));
      setStatusMsg({ 
        text: `Upload WSI thành công (Giữ lại ${num_valid_tiles} tiles).`, 
        type: "success" 
      });
      setWsiFiles([]);
    } catch (err: any) {
      const errorText = `Lỗi xử lý WSI: ${getErrorMessage(err, "Không thể tải lên WSI.")}`;
      setStatusMsg({ text: errorText, type: "error" });
    } finally {
      setUploading(false);
    }
  };

  const handleUploadRna = async () => {
    if (!rnaFile || !patientId.trim()) {
      setStatusMsg({
        text: "Vui lòng nhập mã bệnh nhân và chọn file RNA (.csv/.tsv).",
        type: "error",
      });
      return;
    }

    setUploading(true);
    setStatusMsg({ text: "", type: "" });

    try {
      await apiService.upload.rna(patientId.trim(), rnaFile);
      setUploadedStatus(prev => ({ ...prev, rna: true }));
      setStatusMsg({ text: "Tải lên dữ liệu RNA thành công.", type: "success" });
      setRnaFile(null);
    } catch (err: any) {
      setStatusMsg({
        text: `Lỗi upload RNA: ${getErrorMessage(err, "Hãy bảo đảm file có cột patient_id hợp lệ.")}`,
        type: "error",
      });
    } finally {
      setUploading(false);
    }
  };

  const handleUpdateClinical = async () => {
    if (!patientId.trim() || !ki67) {
      setStatusMsg({
        text: "Vui lòng nhập mã bệnh nhân và chỉ số KI-67.",
        type: "error",
      });
      return;
    }

    setUploading(true);
    setStatusMsg({ text: "", type: "" });

    try {
      await apiService.upload.clinical(patientId.trim(), { 
        ki67_index: ki67 ? parseFloat(ki67) : null,
        grade: grade || null,
        idh_mutation: idhMutation || null,
        mgmt_methylation: mgmtMethylation || null
      });
      setUploadedStatus(prev => ({ ...prev, clinical: true }));
      setStatusMsg({ text: "Cập nhật dữ liệu lâm sàng thành công.", type: "success" });
    } catch (err: any) {
      setStatusMsg({
        text: `Lỗi cập nhật: ${getErrorMessage(err, "Không thể cập nhật thông tin lâm sàng.")}`,
        type: "error",
      });
    } finally {
      setUploading(false);
    }
  };

  const handleRunFullPipeline = async () => {
    if (!patientId.trim()) {
      setStatusMsg({ text: "Vui lòng nhập Mã bệnh nhân để chạy pipeline.", type: "error" });
      return;
    }

    setUploading(true);
    setStatusMsg({ text: "Đang kích hoạt quy trình phân tích tổng hợp AI...", type: "success" });
    setProgress(null);

    try {
      if (lastUploadedImageId) {
        setStatusMsg({ text: "Đang chạy pipeline MRI cho ảnh vừa upload...", type: "success" });
        const mriTaskResponse = await apiService.inference.runMri(lastUploadedImageId);
        const mriTaskId = mriTaskResponse.data?.task_id;

        if (mriTaskId) {
          await apiService.inference.waitForTask(mriTaskId, 3000, 1200000, (p, s) => {
            const percent = Math.min(60, Math.round((p || 0) * 0.6));
            setProgress({ percent, status: s });
            setStatusMsg({ text: s, type: "success" });
          });
        }
      }

      setStatusMsg({ text: "Đang chạy pipeline tiên lượng đa mô thức...", type: "success" });
      const taskResponse = await apiService.inference.runPrognosis(patientId.trim());
      const taskId = taskResponse.data?.task_id;
      
      if (taskId) {
        await apiService.inference.waitForTask(taskId, 3000, 1200000, (p, s) => {
          const percent = lastUploadedImageId ? 60 + Math.round((p || 0) * 0.4) : p;
          setProgress({ percent, status: s });
          setStatusMsg({ text: s, type: "success" });
        });
      }

      // Đạt 100% trước khi chuyển trang
      setProgress({ percent: 100, status: "Hoàn tất! Đang chuyển sang trang kết quả..." });
      setStatusMsg({ text: "Quy trình phân tích tổng hợp hoàn tất thành công.", type: "success" });

      // Delay nhẹ để người dùng thấy 100%
      await new Promise((resolve) => setTimeout(resolve, 1500));

      // Tự động chuyển sang trang kết quả
      router.push(`/results/${patientId.trim()}`);
    } catch (err: any) {
      const errorText = `Lỗi chạy pipeline: ${getErrorMessage(err, "Không thể thực hiện phân tích.")}`;
      setStatusMsg({ text: errorText, type: "error" });
      setProgress(null);
      setUploading(false);
    }
  };

  const renderMriCard = () => {
    if (uploadResult.kind !== "idle") {
      return (
        <MriResultCard
          title={uploadResult.kind === "success" ? "Kết quả MRI vừa chạy xong" : "Lỗi MRI pipeline"}
          result={uploadResult.data || null}
          onClose={resetMriCard}
          onRetry={uploadResult.kind === "error" ? resetMriCard : undefined}
          onDownload={
            uploadResult.kind === "success" && uploadResult.imageId
              ? () => handleDownloadReport(uploadResult.imageId as string | number)
              : undefined
          }
          onExtraAction={resetMriCard}
          extraActionLabel="Tải tiếp ảnh"
        />
      );
    }

    return (
      <div className="flex-1 rounded-2xl border-2 border-dashed border-slate-300 dark:border-slate-700 bg-slate-800/50 flex flex-col items-center justify-center p-12 relative group hover:border-teal-500/50 hover:bg-slate-800/50 transition-all">
        <div className="h-20 w-20 rounded-full bg-teal-500/10 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
          <UploadCloud className="h-10 w-10 text-teal-500" />
        </div>

        <h3 className="text-xl font-bold text-slate-100 mb-2 text-center">
          Tải lên ảnh / MRI để chạy pipeline YOLOv11 {"->"} DynUNet {"->"} DenseNet169
        </h3>
        <p className="text-slate-400 italic mb-8">
          Hỗ trợ tải lên 1 file đơn, nhiều file (.dcm/.png) hoặc file nén (.zip).
        </p>

        <div className="flex flex-col items-center gap-4 w-full max-w-sm">
          <input
            type="text"
            placeholder="Mã bệnh nhân (Patient ID)"
            value={patientId}
            onChange={(event) => setPatientId(event.target.value)}
            className="w-full px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 mb-2 focus:border-teal-500 outline-none"
          />
          <label className="w-full relative">
            <input type="file" multiple className="hidden" onChange={handleMriFileChange} />
            <div className="w-full px-6 py-3 cursor-pointer bg-teal-600 hover:bg-teal-500 text-white font-semibold rounded-xl transition-all shadow-md flex justify-center">
              + Chọn file / Chuỗi ảnh MRI
            </div>
          </label>
          {mriFiles.length > 0 && (
            <div className="text-teal-400 text-sm">
              Đã chọn {mriFiles.length} file {mriFiles.length === 1 ? `(${mriFiles[0].name})` : ""}
            </div>
          )}
          {!uploadedStatus.mri ? (
            <button
              onClick={handleUploadDicom}
              disabled={uploading || !patientId.trim() || mriFiles.length === 0}
              className="w-full mt-2 px-6 py-3 bg-slate-100 hover:bg-slate-200 text-slate-950 font-bold rounded-xl disabled:opacity-50 flex justify-center items-center"
            >
              {uploading && activeTab === "dicom" ? <Loader2 className="h-5 w-5 animate-spin mr-2" /> : null}
              Tải lên MRI
            </button>
          ) : (
            <div className="flex gap-2 w-full mt-2">
              <div className="flex-1 px-6 py-3 bg-slate-700 text-slate-400 font-bold rounded-xl flex justify-center items-center cursor-not-allowed">
                Đã tải (MRI)
              </div>
              <button
                onClick={() => setUploadedStatus(prev => ({ ...prev, mri: false }))}
                className="px-4 py-3 bg-slate-800 hover:bg-slate-700 text-slate-100 font-medium rounded-xl border border-slate-700 transition-all"
              >
                Cập nhật
              </button>
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="grid min-h-[calc(100vh-6rem)] grid-cols-1 gap-6 lg:h-[calc(100vh-6rem)] lg:grid-cols-3">
      <div className="lg:col-span-2 flex flex-col">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-slate-100 mb-1">Tải lên mới</h1>
            <p className="text-sm text-slate-400">
              Đẩy dữ liệu lên backend và chạy đúng pipeline MRI hoặc multimodal.
            </p>
          </div>

          <div className="flex bg-slate-800 p-1 rounded-lg border border-slate-700">
            <button
              onClick={() => setActiveTab("dicom")}
              className={`px-4 py-1.5 text-sm font-medium rounded-md transition-all ${
                activeTab === "dicom"
                  ? "bg-slate-900 text-slate-100 shadow-sm"
                  : "text-slate-500 dark:text-slate-400 hover:text-teal-600 dark:hover:text-teal-400"
              }`}
            >
              MRI (Ảnh)
            </button>
            <button
              onClick={() => setActiveTab("wsi")}
              className={`px-4 py-1.5 text-sm font-medium rounded-md transition-all ${
                activeTab === "wsi"
                  ? "bg-slate-900 text-slate-100 shadow-sm"
                  : "text-slate-500 dark:text-slate-400 hover:text-teal-600 dark:hover:text-teal-400"
              }`}
            >
              WSI (Mô bệnh học)
            </button>
            <button
              onClick={() => setActiveTab("rna")}
              className={`px-4 py-1.5 text-sm font-medium rounded-md transition-all ${
                activeTab === "rna"
                  ? "bg-slate-900 text-slate-100 shadow-sm"
                  : "text-slate-500 dark:text-slate-400 hover:text-teal-600 dark:hover:text-teal-400"
              }`}
            >
              RNA
            </button>
            <button
              onClick={() => setActiveTab("clinical")}
              className={`px-4 py-1.5 text-sm font-medium rounded-md transition-all ${
                activeTab === "clinical"
                  ? "bg-slate-900 text-slate-100 shadow-sm"
                  : "text-slate-500 dark:text-slate-400 hover:text-teal-600 dark:hover:text-teal-400"
              }`}
            >
              Lâm sàng
            </button>
          </div>
        </div>

        {statusMsg.text && (
          <div
            className={`mb-6 p-5 rounded-2xl border flex flex-col gap-4 shadow-lg ${
              statusMsg.type === "error"
                ? "bg-rose-500/10 text-rose-500 border-rose-500/20"
                : "bg-emerald-500/10 text-emerald-500 border-emerald-500/20"
            }`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {uploading ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : statusMsg.type === "error" ? (
                  <AlertCircle className="h-5 w-5" />
                ) : (
                  <CheckCircle2 className="h-5 w-5" />
                )}
                <span className="font-medium text-sm">{statusMsg.text}</span>
              </div>
              
              {statusMsg.type === "success" && !uploading && patientId.trim() && (
                <button
                  onClick={() => router.push(`/patients/${patientId.trim()}`)}
                  className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider bg-emerald-500 text-white px-3 py-1.5 rounded-lg hover:bg-emerald-600 transition-all"
                >
                  Xem hồ sơ <ArrowRight className="h-4 w-4" />
                </button>
              )}
            </div>

            {/* Thanh tiến trình thời gian thực */}
            {progress && (
              <div className="w-full space-y-3 pt-2 border-t border-white/10">
                <div className="flex justify-between items-end mb-1">
                  <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                    {progress.status}
                  </span>
                  <span className="text-sm font-mono font-bold text-emerald-400">
                    {progress.percent}%
                  </span>
                </div>
                <div className="w-full bg-slate-800 rounded-full h-2.5 overflow-hidden border border-white/5">
                  <div 
                    className="bg-gradient-to-r from-emerald-600 to-emerald-400 h-full transition-all duration-700 ease-in-out relative shadow-[0_0_15px_rgba(16,185,129,0.3)]"
                    style={{ width: `${progress.percent}%` }}
                  >
                    <div className="absolute inset-0 bg-[linear-gradient(45deg,rgba(255,255,255,0.1)_25%,transparent_25%,transparent_50%,rgba(255,255,255,0.1)_50%,rgba(255,255,255,0.1)_75%,transparent_75%,transparent)] bg-[length:20px_20px] animate-[progress-bar-stripes_1s_linear_infinite]" />
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === "dicom" && renderMriCard()}

        {activeTab === "wsi" && (
           <div className="flex-1 rounded-2xl border-2 border-dashed border-rose-300 dark:border-rose-700/50 bg-slate-900 flex flex-col items-center justify-center p-12 relative group hover:border-rose-500/50 hover:bg-rose-900/10 transition-all">
             <div className="h-20 w-20 rounded-full bg-rose-50 dark:bg-rose-500/10 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
               <UploadCloud className="h-10 w-10 text-rose-600 dark:text-rose-500" />
             </div>

             <h3 className="text-xl font-bold text-slate-100 mb-2 text-center">Tải lên WSI Tiles (Chuỗi ảnh)</h3>
             <p className="text-slate-400 mb-8 max-w-md text-center italic">
               Hệ thống sẽ tự động lọc các tiles rỗng và chọn 200 tiles tốt nhất bằng CNN.
             </p>

             <div className="flex flex-col items-center gap-4 w-full max-w-sm">
                <input
                  type="text"
                  placeholder="Mã bệnh nhân (Patient ID)"
                  value={patientId}
                  onChange={(event) => setPatientId(event.target.value)}
                  className="w-full px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 mb-2 focus:border-rose-500 outline-none"
                />
                <label className="w-full relative">
                  <input type="file" multiple accept="image/*,.zip" className="hidden" onChange={handleWsiFileChange} />
                  <div className="w-full px-6 py-3 cursor-pointer bg-rose-600 hover:bg-rose-500 text-white font-semibold rounded-xl transition-all shadow-md flex justify-center">
                    + Chọn file ZIP / WSI Tiles
                  </div>
                </label>
                {wsiFiles.length > 0 && <div className="text-rose-600 dark:text-rose-400 text-sm">Đã chọn {wsiFiles.length} tiles</div>}

                {!uploadedStatus.wsi ? (
                  <button
                    onClick={handleUploadWsi}
                    disabled={uploading || !patientId.trim() || wsiFiles.length === 0}
                    className="w-full mt-2 px-6 py-3 bg-slate-100 hover:bg-slate-200 text-slate-955 text-slate-950 font-bold rounded-xl disabled:opacity-50 flex justify-center items-center"
                  >
                    {uploading && activeTab === "wsi" ? <Loader2 className="h-5 w-5 animate-spin mr-2" /> : null}
                    Lọc và Tải lên WSI
                  </button>
                ) : (
                  <div className="flex gap-2 w-full mt-2">
                    <div className="flex-1 px-6 py-3 bg-slate-700 text-slate-400 font-bold rounded-xl flex justify-center items-center cursor-not-allowed">
                      Đã tải (WSI)
                    </div>
                    <button
                      onClick={() => setUploadedStatus(prev => ({ ...prev, wsi: false }))}
                      className="px-4 py-3 bg-slate-800 hover:bg-slate-700 text-slate-100 font-medium rounded-xl border border-slate-700 transition-all"
                    >
                      Cập nhật
                    </button>
                  </div>
                )}
              </div>
           </div>
        )}

        {activeTab === "rna" && (
          <div className="flex-1 rounded-2xl border-2 border-dashed border-indigo-300 dark:border-indigo-700/50 bg-slate-900 flex flex-col items-center justify-center p-12 relative group hover:border-indigo-500/50 hover:bg-indigo-900/10 transition-all">
            <div className="h-20 w-20 rounded-full bg-indigo-50 dark:bg-indigo-500/10 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
              <FileType className="h-10 w-10 text-indigo-600 dark:text-indigo-500" />
            </div>

            <h3 className="text-xl font-bold text-slate-100 mb-2 text-center">Tải lên dữ liệu RNA-seq</h3>
            <p className="text-slate-400 mb-8 max-w-md text-center">
              Backend yêu cầu truyền đúng patient_id cùng file RNA.
            </p>

            <div className="flex flex-col items-center gap-4 w-full max-w-sm">
              <input
                type="text"
                placeholder="Mã bệnh nhân (Patient ID)"
                value={patientId}
                onChange={(event) => setPatientId(event.target.value)}
                className="w-full px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 mb-2 focus:border-indigo-500 outline-none"
              />
              <label className="w-full relative">
                <input type="file" accept=".csv,.tsv" className="hidden" onChange={handleRnaFileChange} />
                <div className="w-full px-6 py-3 cursor-pointer bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-xl transition-all shadow-md flex justify-center">
                  Chọn file RNA
                </div>
              </label>
              {rnaFile && <div className="text-indigo-600 dark:text-indigo-400 text-sm">{rnaFile.name}</div>}
              
              {!uploadedStatus.rna ? (
                <button
                  onClick={handleUploadRna}
                  disabled={uploading || !patientId.trim() || !rnaFile}
                  className="w-full mt-2 px-6 py-3 bg-slate-100 hover:bg-slate-200 text-slate-950 font-bold rounded-xl disabled:opacity-50 flex justify-center items-center"
                >
                  {uploading && activeTab === "rna" ? <Loader2 className="h-5 w-5 animate-spin mr-2" /> : null}
                  Tải lên RNA
                </button>
              ) : (
                <div className="flex gap-2 w-full mt-2">
                  <div className="flex-1 px-6 py-3 bg-slate-700 text-slate-400 font-bold rounded-xl flex justify-center items-center cursor-not-allowed">
                    Đã tải (RNA)
                  </div>
                  <button
                    onClick={() => setUploadedStatus(prev => ({ ...prev, rna: false }))}
                    className="px-4 py-3 bg-slate-800 hover:bg-slate-700 text-slate-100 font-medium rounded-xl border border-slate-700 transition-all"
                  >
                    Cập nhật
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === "clinical" && (
          <div className="flex-1 rounded-2xl border border-slate-800 bg-slate-900 p-8 flex flex-col shadow-sm">
            <h3 className="text-xl font-bold text-slate-100 mb-6 border-b border-slate-800 pb-4">
              Cập nhật chỉ số lâm sàng
            </h3>

            <div className="space-y-6 max-w-md">
              <div>
                <label className="block text-sm font-medium text-slate-400 mb-2">
                  Mã bệnh nhân (Patient ID)
                </label>
                <input
                  type="text"
                  required
                  value={patientId}
                  onChange={(event) => setPatientId(event.target.value)}
                  className="w-full px-4 py-3 bg-slate-800 border border-slate-700 text-slate-100 focus:border-emerald-500 outline-none"
                />
              </div>

                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-400 mb-1.5">Chỉ số KI-67 (%)</label>
                    <input
                      type="number"
                      value={ki67}
                      disabled={uploadedStatus.clinical || uploading}
                      onChange={(e) => setKi67(e.target.value)}
                      placeholder="VD: 15"
                      className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-2.5 text-slate-100 focus:outline-none focus:ring-2 focus:ring-teal-500/50 disabled:opacity-50 disabled:cursor-not-allowed"
                    />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-400 mb-1.5">Bậc u (WHO Grade)</label>
                      <select
                        value={grade}
                        disabled={uploadedStatus.clinical || uploading}
                      onChange={(e) => setGrade(e.target.value)}
                      className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-2.5 text-slate-100 focus:outline-none focus:ring-2 focus:ring-teal-500/50 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <option value="">Chọn bậc u</option>
                        <option value="2">WHO Grade II</option>
                        <option value="3">WHO Grade III</option>
                        <option value="4">WHO Grade IV (GBM)</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-400 mb-1.5">Đột biến IDH</label>
                      <select
                        value={idhMutation}
                        disabled={uploadedStatus.clinical || uploading}
                        onChange={(e) => setIdhMutation(e.target.value)}
                        className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-2.5 text-slate-100 focus:outline-none focus:ring-2 focus:ring-teal-500/50 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <option value="">Chưa xác định</option>
                        <option value="1">Có đột biến (Mutant)</option>
                        <option value="0">Không đột biến (Wildtype)</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-400 mb-1.5">MGMT Methylation</label>
                      <select
                        value={mgmtMethylation}
                        disabled={uploadedStatus.clinical || uploading}
                        onChange={(e) => setMgmtMethylation(e.target.value)}
                        className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-2.5 text-slate-100 focus:outline-none focus:ring-2 focus:ring-teal-500/50 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <option value="">Chưa xác định</option>
                        <option value="1">Có Methylation (Positive)</option>
                        <option value="0">Không Methylation (Negative)</option>
                      </select>
                    </div>
                  </div>
                </div>

              <div className="pt-4">
                {!uploadedStatus.clinical ? (
                  <button
                    onClick={handleUpdateClinical}
                    disabled={uploading || !patientId.trim() || (!ki67 && !grade && !idhMutation && !mgmtMethylation)}
                    className="w-full px-6 py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-xl disabled:opacity-50 transition-all flex justify-center items-center shadow-md"
                  >
                    {uploading && activeTab === "clinical" ? <Loader2 className="h-5 w-5 animate-spin mr-2" /> : null}
                    Lưu thông tin lâm sàng
                  </button>
                ) : (
                  <div className="flex gap-2 w-full mt-2">
                    <div className="flex-1 px-6 py-3 bg-slate-700 text-slate-400 font-bold rounded-xl flex justify-center items-center cursor-not-allowed">
                      Đã lưu lâm sàng
                    </div>
                    <button
                      onClick={() => setUploadedStatus(prev => ({ ...prev, clinical: false }))}
                      className="px-4 py-3 bg-slate-800 hover:bg-slate-700 text-slate-100 font-medium rounded-xl border border-slate-700 transition-all"
                    >
                      Cập nhật
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Nút Chạy Tổng Hợp cố định ở dưới - Chỉ hiện khi có MRI */}
        {uploadedStatus.mri && !requireNewUpload && (
          <div className="mt-8 p-6 rounded-2xl bg-teal-50 dark:bg-slate-800/50 border border-teal-200 dark:border-teal-500/30 flex flex-col items-center">
            <h4 className="text-teal-600 dark:text-teal-400 font-bold mb-2 flex items-center gap-2">
              <PlayCircle className="h-5 w-5" /> Sẵn sàng phân tích tổng hợp
            </h4>
            <p className="text-slate-600 dark:text-slate-400 text-sm mb-6 text-center">
              Dữ liệu đã được chuẩn bị cho bệnh nhân <strong>{patientId}</strong>. 
              Nhấn nút dưới đây để kích hoạt toàn bộ AI Pipeline.
            </p>
            <button
              onClick={handleRunFullPipeline}
              disabled={uploading}
              className="px-12 py-4 bg-teal-600 hover:bg-teal-500 text-white text-lg font-black rounded-2xl transition-all shadow-md flex items-center gap-3 disabled:opacity-50"
            >
              {uploading && statusMsg.text.includes("quy trình") ? (
                <Loader2 className="h-6 w-6 animate-spin" />
              ) : (
                <PlayCircle className="h-6 w-6" />
              )}
              CHẠY TỔNG HỢP / KÍCH HOẠT PIPELINE AI
            </button>
          </div>
        )}
      </div>

      <div className="flex flex-col w-full h-full">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
            <Clock className="h-5 w-5 text-teal-600 dark:text-teal-500" /> Tải lên gần đây
          </h2>
          <button className="text-sm text-teal-600 dark:text-teal-500 hover:text-teal-400">Xem tất cả</button>
        </div>

        <div className="flex flex-col gap-4 overflow-y-auto custom-scrollbar pr-2">
          {recentUploads.map((item) => (
            <div
              key={item.id}
              className="rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-sm flex flex-col relative overflow-hidden group"
            >
              <div
                className={`absolute left-0 top-0 h-full w-1 ${
                  item.status === "READY" ? "bg-teal-500" : "bg-slate-600"
                }`}
              />

              <div className="flex justify-between items-start mb-3 ml-2">
                <h4 className="font-semibold text-slate-100">{item.name}</h4>
                <span
                  className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded border tracking-wider ${
                    item.status === "READY"
                      ? "text-teal-600 bg-teal-50 dark:bg-teal-400/10 border-teal-200 dark:border-teal-400/20"
                      : "text-slate-500 bg-slate-100 border-slate-200 dark:bg-slate-800 dark:border-slate-700"
                  }`}
                >
                  {item.status}
                </span>
              </div>

              <div className="flex items-center gap-2 text-xs text-slate-400 dark:text-slate-400 mb-4 ml-2">
                {item.time && (
                  <>
                    <Clock className="h-3.5 w-3.5" />
                    <span>{item.time}</span>
                    <span className="mx-1">•</span>
                    <span>{item.size}</span>
                  </>
                )}
                {item.desc && (
                  <span className="flex items-center gap-2 animate-pulse">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> {item.desc}
                  </span>
                )}
              </div>

              <button
                disabled={item.status !== "READY"}
                onClick={() => router.push("/patients")}
                className="ml-2 py-2 w-full rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 disabled:opacity-50 text-sm font-medium text-slate-700 dark:text-slate-100 transition-colors flex items-center justify-center gap-2"
              >
                {item.status === "READY" ? (
                  <>
                    <PlayCircle className="h-4 w-4" /> Xem hồ sơ và phân tích
                  </>
                ) : (
                  "Đang xử lý dữ liệu..."
                )}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
