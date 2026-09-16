"use client";

import { useEffect, useState } from "react";
import { apiService } from "@/lib/api";
import { Users, Activity, BarChart3, Star, AlertTriangle, CheckCircle2 } from "lucide-react";

export default function DashboardPage() {
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await apiService.analysis.getDashboardStats();
        setStats(res.data);
      } catch (error) {
        console.error("Failed to load dashboard stats", error);
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, []);

  if (loading) {
    return (
      <div className="flex min-h-[calc(100vh-6rem)] items-center justify-center">
        <div className="animate-pulse flex flex-col items-center">
          <div className="h-12 w-12 rounded-full border-4 border-t-teal-500 border-slate-700 animate-spin mb-4" />
          <p className="text-slate-400">Đang tải thống kê dữ liệu...</p>
        </div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="flex min-h-[calc(100vh-6rem)] items-center justify-center">
        <p className="text-red-400">Không thể tải dữ liệu thống kê.</p>
      </div>
    );
  }

  // Helper to render distribution bars
  const renderDistribution = (dist: Record<string, number>, colors: string[]) => {
    const total = Object.values(dist).reduce((a, b) => a + b, 0) || 1;
    return (
      <div className="space-y-4">
        {Object.entries(dist).map(([key, val], idx) => {
          const percent = ((val / total) * 100).toFixed(1);
          const color = colors[idx % colors.length];
          return (
            <div key={key}>
              <div className="flex justify-between items-center mb-1 text-sm font-medium">
                <span className="text-slate-200">{key}</span>
                <span className="text-slate-400">{val} ({percent}%)</span>
              </div>
              <div className="w-full bg-slate-800 rounded-full h-2.5">
                <div className="h-2.5 rounded-full" style={{ width: `${percent}%`, backgroundColor: color }}></div>
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="flex min-h-[calc(100vh-6rem)] min-w-0 flex-col gap-6 overflow-y-auto pb-6 pr-0 sm:pr-2 custom-scrollbar">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Tổng quan Nghiên cứu</h1>
          <p className="text-slate-400 text-sm mt-1">Dữ liệu thống kê phân tích từ hệ thống AI đa mô thức</p>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg flex items-center gap-4">
          <div className="p-4 bg-teal-500/10 text-teal-600 dark:text-teal-400 rounded-xl"><Users className="h-6 w-6" /></div>
          <div>
            <p className="text-sm font-medium text-slate-400 uppercase tracking-wider">Tổng số hồ sơ</p>
            <p className="text-3xl font-bold text-slate-100 mt-1">{stats.total_patients}</p>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg flex items-center gap-4">
          <div className="p-4 bg-amber-500/10 text-amber-600 dark:text-amber-500 rounded-xl"><Star className="h-6 w-6" /></div>
          <div>
            <p className="text-sm font-medium text-slate-400 uppercase tracking-wider">Điểm XAI (TB)</p>
            <p className="text-3xl font-bold text-slate-100 mt-1">{stats.average_validation_rating.toFixed(1)} <span className="text-lg text-slate-500">/ 5.0</span></p>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg flex items-center gap-4">
          <div className="p-4 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 rounded-xl"><CheckCircle2 className="h-6 w-6" /></div>
          <div>
            <p className="text-sm font-medium text-slate-400 uppercase tracking-wider">Lượt đánh giá</p>
            <p className="text-3xl font-bold text-slate-100 mt-1">{stats.total_validations}</p>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg flex items-center gap-4">
          <div className="p-4 bg-rose-500/10 text-rose-600 dark:text-rose-500 rounded-xl"><Activity className="h-6 w-6" /></div>
          <div>
            <p className="text-sm font-medium text-slate-400 uppercase tracking-wider">Tổng ca chẩn đoán</p>
            <p className="text-3xl font-bold text-slate-100 mt-1">{Object.values(stats.tumor_distribution).reduce((a: any, b: any) => a + b, 0) as number}</p>
          </div>
        </div>
      </div>

      {/* Distribution Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-2">
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg">
          <div className="flex items-center gap-2 mb-6">
            <div className="p-1.5 bg-blue-500/10 text-blue-600 dark:text-blue-400 rounded-md"><BarChart3 className="h-5 w-5" /></div>
            <h2 className="text-lg font-semibold text-slate-100">Phân bố Loại U (Tumor Types)</h2>
          </div>
          {Object.keys(stats.tumor_distribution).length > 0 ? (
            renderDistribution(stats.tumor_distribution, ['#3b82f6', '#0ea5e9', '#14b8a6', '#f59e0b', '#64748b'])
          ) : (
            <p className="text-slate-500 text-center py-8">Chưa có dữ liệu phân loại</p>
          )}
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg">
          <div className="flex items-center gap-2 mb-6">
            <div className="p-1.5 bg-rose-500/10 text-rose-600 dark:text-rose-500 rounded-md"><AlertTriangle className="h-5 w-5" /></div>
            <h2 className="text-lg font-semibold text-slate-100">Phân tầng Nguy cơ (Risk Groups)</h2>
          </div>
          {Object.keys(stats.risk_distribution).length > 0 ? (
            renderDistribution(stats.risk_distribution, ['#f43f5e', '#f59e0b', '#10b981', '#64748b'])
          ) : (
            <p className="text-slate-500 text-center py-8">Chưa có dữ liệu tiên lượng</p>
          )}
        </div>
      </div>
      
      {/* Platform Info */}
      <div className="mt-4 bg-teal-50 dark:bg-teal-950/30 border border-teal-100 dark:border-teal-900/50 rounded-2xl p-6 flex items-start gap-4">
        <div className="mt-1 p-2 bg-teal-500/20 text-teal-600 dark:text-teal-400 rounded-full"><Star className="h-5 w-5" /></div>
        <div>
          <h3 className="text-base font-semibold text-teal-800 dark:text-teal-300">Nền tảng hỗ trợ quyết định lâm sàng (Clinical Validation Loop)</h3>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-2 leading-relaxed">
            Hệ thống này được thiết kế không chỉ để đưa ra kết quả AI mà còn thu thập phản hồi từ các chuyên gia y tế thông qua cơ chế Sanity Check. 
            Mọi đánh giá (Rating) từ bác sĩ đối với Bản đồ nhiệt XAI và Văn bản giải thích đều được lưu trữ phục vụ cho quá trình đánh giá tính khả thi và độ tin cậy của mô hình trong thực tế lâm sàng.
          </p>
        </div>
      </div>
    </div>
  );
}
