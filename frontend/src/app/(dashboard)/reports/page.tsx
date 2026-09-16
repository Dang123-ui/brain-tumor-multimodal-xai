"use client";

import { useEffect, useState } from "react";
import { Printer, Download, Share2, CheckCircle2, AlertOctagon, FileText, Beaker, Brain } from "lucide-react";
import { GaugeChart } from "@/components/ui/GaugeChart";
import { SurvivalCurve } from "@/components/ui/SurvivalCurve";
import { apiService } from "@/lib/api";
import { ImagePreviewModal, ImagePreviewState } from "@/components/ui/ImagePreviewModal";

const DEMO_MRI_IMAGE = "https://images.unsplash.com/photo-1559757175-9b78a05eacbe?auto=format&fit=crop&w=400&q=80";

export default function ReportPage() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [previewImage, setPreviewImage] = useState<ImagePreviewState | null>(null);

  useEffect(() => {
    // Trong thực tế, ID bệnh nhân sẽ lấy từ URL hoặc state quản lý
    apiService.analysis.getResult("1")
      .then(res => {
        setData(res.data);
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="flex min-h-[calc(100vh-6rem)] items-center justify-center">
        <div className="animate-spin h-10 w-10 border-4 border-t-teal-500 border-slate-700 rounded-full" />
      </div>
    );
  }

  // Dữ liệu mẫu nếu chưa có kết quả thực
  const result = data || {
    patient_id: "ND-8829-X",
    tumor_label: "Glioblastoma (GBM)",
    classification_confidence: 0.942,
    risk_score: 84,
    risk_group: "High",
    survival_curve_data: [
      { time: 0, survival_probability: 1.0 },
      { time: 6, survival_probability: 0.92 },
      { time: 12, survival_probability: 0.85 },
      { time: 18, survival_probability: 0.65 },
      { time: 24, survival_probability: 0.42 },
      { time: 36, survival_probability: 0.28 }
    ]
  };

  return (
    <div className="relative flex min-h-[calc(100vh-6rem)] min-w-0 flex-col overflow-hidden lg:h-[calc(100vh-6rem)]">
      
      {/* Top Action Bar */}
      <div className="relative z-10 flex shrink-0 flex-col gap-3 border-b border-slate-800 bg-slate-900 p-4 shadow-lg lg:flex-row lg:items-center lg:justify-between">
        <h1 className="flex items-center gap-2 text-lg font-bold sm:text-xl">
          <FileText className="text-teal-500" />
          NeuroDiagnosis AI: Báo cáo Lâm sàng
        </h1>
        <div className="flex flex-wrap gap-2 sm:gap-3">
          <button
            onClick={() => {
              navigator.clipboard.writeText(window.location.href);
              alert("Đã sao chép liên kết báo cáo vào clipboard!");
            }}
            className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm font-semibold text-slate-300 transition hover:bg-slate-700 sm:px-4"
          >
            <Share2 className="h-4 w-4" /> Chia sẻ
          </button>
          <button
            onClick={() => window.print()}
            className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm font-semibold text-slate-300 transition hover:bg-slate-700 sm:px-4"
          >
             <Printer className="h-4 w-4" /> In Báo Cáo
          </button>
          <button
            onClick={() => alert("Chức năng xuất PDF đang được phát triển. Bạn có thể sử dụng In Báo Cáo > Save as PDF.")}
            className="flex items-center gap-2 rounded-lg bg-teal-600 px-3 py-2 text-sm font-bold text-white shadow-lg shadow-teal-500/20 transition hover:bg-teal-500 sm:px-4"
          >
            <Download className="h-4 w-4" /> Xuất PDF
          </button>
        </div>
      </div>

      {/* Main Report Content - A4 Proportions with shadow styling inner container */}
      <div className="flex flex-1 justify-center overflow-auto bg-slate-950/40 p-3 sm:p-6 lg:p-10">
        
        <div className="w-full max-w-4xl bg-slate-950 rounded-xl shadow-2xl relative text-slate-200 flex flex-col h-fit mb-12 border border-slate-800">
           
           {/* Report Header Band */}
           <div className="h-4 w-full bg-teal-600 shrink-0"></div>
           
           {/* Report Inner - Printable Canvas */}
           <div className="flex flex-1 flex-col p-4 sm:p-8 lg:p-12">
             
             {/* Report Title & Logos */}
             <div className="flex justify-between items-start border-b-2 border-slate-800 pb-6 mb-8">
               <div className="flex flex-col">
                 <div className="flex items-center gap-2 text-teal-500 mb-2">
                   <Brain className="h-8 w-8" />
                   <h2 className="text-3xl font-black uppercase tracking-tight text-slate-100">NeuroDiagnosis</h2>
                 </div>
                 <span className="text-sm font-bold tracking-widest text-slate-400 uppercase">AI-Assisted Oncology Diagnostic Report</span>
               </div>
               
               <div className="text-right flex flex-col gap-1 text-sm font-mono text-slate-400">
                  <span className="bg-slate-800 text-slate-200 px-3 py-1 rounded inline-block font-bold self-end mb-2">REPORT # REP-2023-{result.patient_id}</span>
                  <span suppressHydrationWarning><strong>Date:</strong> {new Date().toLocaleDateString('vi-VN')}</span>
                  <span><strong>Model Ver:</strong> Core-V4.2.1-Fusion</span>
               </div>
             </div>

             {/* Patient Info Block */}
             <div className="grid grid-cols-2 md:grid-cols-4 gap-6 bg-slate-900 p-6 rounded-lg shadow-sm border border-slate-800 mb-8">
                <div className="flex flex-col">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">Mã BN (Patient ID)</span>
                  <span className="font-mono font-bold text-slate-100 border-b border-teal-500/20 pb-1">{result.patient_id}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">Họ Và Tên</span>
                  <span className="font-bold text-slate-100 border-b border-teal-500/20 pb-1">Trần Văn B.</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">Giới tính / Tuổi</span>
                  <span className="font-bold text-slate-100 border-b border-teal-500/20 pb-1">Nam / 52</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">Bác sĩ Chỉ định</span>
                  <span className="font-bold text-slate-100 border-b border-teal-500/20 pb-1">BS. Lê Thị M.</span>
                </div>
             </div>

             {/* Diagnosis Result Sections */}
             <div className="flex flex-col lg:flex-row gap-8 mb-8">
               
               {/* Left Column Component: Diagnosis & Survival */}
               <div className="flex-1 flex flex-col gap-6">
                 
                 {/* Classification Box */}
                 <div className="bg-slate-900 p-6 rounded-lg shadow-sm border border-slate-800 relative overflow-hidden">
                   <div className="absolute top-0 right-0 p-3 bg-red-500/10 text-red-500 border-l border-b border-red-500/25 rounded-bl-lg font-bold flex items-center gap-1">
                      <AlertOctagon className="h-4 w-4" /> Khẩn cấp
                   </div>

                   <h3 className="text-sm font-bold uppercase tracking-wider text-teal-500 mb-4 flex items-center gap-2 border-b border-slate-800 pb-2">
                      <Brain className="h-4 w-4" /> 1. Phân loại Khối U AI
                   </h3>
                   
                   <div className="flex flex-col mb-4">
                     <span className="text-4xl font-black text-slate-100 mb-1">{result.tumor_label}</span>
                     <span className="text-sm font-medium text-slate-300 bg-slate-800/50 self-start px-2 py-0.5 rounded">Grade IV Astrocytoma</span>
                   </div>

                   <div className="w-full bg-slate-800 rounded-full h-2 mb-2">
                     <div className="bg-teal-600 h-2 rounded-full" style={{ width: `${result.classification_confidence * 100}%` }}></div>
                   </div>
                   <div className="flex justify-between text-xs font-bold text-slate-300 mb-4 border-b border-slate-800 pb-4">
                      <span>Độ tin cậy:</span>
                      <span className="text-teal-500">{(result.classification_confidence * 100).toFixed(1)}%</span>
                   </div>
                 </div>

                 {/* Prognosis Box */}
                 <div className="bg-slate-900 p-6 rounded-lg shadow-sm border border-slate-800">
                    <h3 className="text-sm font-bold uppercase tracking-wider text-teal-500 mb-4 flex items-center gap-2 border-b border-slate-800 pb-2">
                      <Beaker className="h-4 w-4" /> 2. Tiên lượng & Yếu tố Rủi ro
                   </h3>
                   
                   <div className="flex items-center gap-6 mb-8">
                      <div className="w-40 shrink-0 opacity-90 drop-shadow-md">
                         <GaugeChart value={result.risk_score} />
                      </div>
                      
                      <div className="flex flex-col gap-3">
                         <div className={`p-3 rounded border ${result.risk_group === 'High' ? 'bg-red-500/10 border-red-500/25 text-red-400' : 'bg-teal-500/10 border-teal-500/25 text-teal-400'}`}>
                           <span className="block text-xs font-bold uppercase mb-1">Chỉ số rủi ro sinh tồn</span>
                           <span className="text-2xl font-bold">{result.risk_score} <span className="text-sm font-normal">/ 100</span></span>
                         </div>
                      </div>
                   </div>

                   {/* Kaplan-Meier Chart */}
                   <div className="mt-4 border-t border-slate-800 pt-6">
                      <SurvivalCurve 
                        data={result.survival_curve_data} 
                        color={result.risk_group === 'High' ? "#ef4444" : "#14b8a6"} 
                      />
                   </div>
                 </div>

               </div>
               
               {/* Right Column Component: Visual Evidence (XAI) */}
               <div className="w-full lg:w-1/3 flex flex-col gap-6">
                 <div className="bg-slate-900 p-6 rounded-lg shadow-sm border border-slate-800 h-full flex flex-col">
                   <h3 className="text-sm font-bold uppercase tracking-wider text-teal-500 mb-4 flex items-center gap-2 border-b border-slate-800 pb-2">
                      <CheckCircle2 className="h-4 w-4" /> 3. Bằng chứng Hình ảnh
                   </h3>
                   
                   {/* Annotated Scans */}
                   <div className="flex flex-col gap-4 flex-1">
                      
                      <div className="flex flex-col bg-slate-950/50 p-2 rounded border border-slate-800 relative overflow-hidden group">
                        <button
                          type="button"
                          onClick={() => setPreviewImage({ title: "T2 Axial (Lớp cắt #42)", src: DEMO_MRI_IMAGE })}
                          className="mb-2 block w-full overflow-hidden rounded bg-slate-950"
                        >
                          <img src={DEMO_MRI_IMAGE} alt="Axial view" className="h-40 w-full object-cover opacity-90 group-hover:scale-105 transition-transform" />
                        </button>
                        <div className="pointer-events-none absolute top-1/2 left-1/2 h-12 w-16 -translate-x-1/2 -translate-y-1/2 rounded border-2 border-red-500 bg-red-500/20 mix-blend-multiply"></div>
                        <span className="text-xs font-bold text-center text-slate-400 block">T2 Axial (Lớp cắt #42)</span>
                      </div>

                      <div className="flex flex-col bg-slate-950/50 p-2 rounded border border-slate-800 relative overflow-hidden group">
                        <button
                          type="button"
                          onClick={() => setPreviewImage({ title: "Bản đồ nhiệt XAI (Grad-CAM)", src: DEMO_MRI_IMAGE })}
                          className="mb-2 block w-full overflow-hidden rounded bg-slate-950"
                        >
                          <img src={DEMO_MRI_IMAGE} alt="heatmap" className="h-40 w-full object-cover grayscale mix-blend-multiply opacity-90 group-hover:scale-105 transition-transform" />
                        </button>
                        <div className="pointer-events-none absolute inset-2 left-1/2 top-10 h-3/4 w-3/4 -translate-x-1/2 rounded-full bg-gradient-to-tr from-transparent via-red-500/40 to-yellow-500/40 mix-blend-multiply blur-xl"></div>
                        <span className="text-xs font-bold text-center text-slate-400 block">Bản đồ nhiệt XAI (Grad-CAM)</span>
                      </div>

                   </div>
                 </div>
               </div>
             </div>

             {/* Generative Summary & Recommendations */}
             <div className="bg-teal-500/10 p-6 rounded-lg border-l-4 border-teal-500 text-slate-200 shadow-sm mt-auto">
               <h4 className="font-bold mb-2 flex items-center gap-2 text-teal-400">
                  <Brain className="h-5 w-5" /> Tóm tắt & Gợi ý (AI Sinh tạo)
               </h4>
               <p className="text-sm leading-relaxed mb-4 text-slate-400">
                 Dựa trên phân tích đa mô thức (MRI + Gen + Lâm sàng), bệnh nhân thuộc nhóm nguy cơ <strong>{result.risk_group}</strong>. Đường cong sinh tồn tiên lượng xác suất sống sót giảm mạnh sau 18 tháng nếu không can thiệp.
               </p>
               <p className="text-sm font-bold text-teal-400">
                 Gợi ý: Hội chẩn đa chuyên khoa khẩn cấp.
               </p>
             </div>

             <div className="mt-8 pt-4 border-t border-slate-800 text-center text-xs text-slate-500 font-mono">
                Generated by NeuroDiagnosis AI Platform - Not for final clinical diagnosis without physician approval.
             </div>

           </div>
           
        </div>
      </div>
      {previewImage && <ImagePreviewModal preview={previewImage} onClose={() => setPreviewImage(null)} />}
    </div>
  );
}
