"use client";

import { useState } from "react";
import { Settings, Cpu, Bell, Monitor, Shield, Save, Server, Loader2 } from "lucide-react";

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState("models");
  const [saving, setSaving] = useState(false);

  const handleSave = () => {
     setSaving(true);
     setTimeout(() => setSaving(false), 1000);
  };

  const tabs = [
    { id: "models", label: "Mô hình & Thuật toán", icon: Cpu },
    { id: "notifications", label: "Thông báo & Cảnh báo", icon: Bell },
    { id: "display", label: "Giao diện & Hiển thị", icon: Monitor },
    { id: "security", label: "Bảo mật & Phân quyền", icon: Shield },
  ];

  return (
    <div className="flex h-full flex-col space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
           <h1 className="text-2xl font-bold text-slate-100 mb-2">Cài đặt Hệ thống</h1>
           <p className="text-sm text-slate-400">Thiết lập tham số AI, cấu hình Server và tùy biến giao diện.</p>
        </div>
        
        <button 
           onClick={handleSave}
           disabled={saving}
           className="px-6 py-2.5 bg-teal-600 hover:bg-teal-500 text-white font-bold rounded-xl flex items-center gap-2 shadow-lg shadow-teal-500/20 disabled:opacity-50 transition-all"
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Lưu thay đổi
        </button>
      </div>

      <div className="flex min-h-[calc(100vh-10rem)] flex-col gap-6 md:h-[calc(100vh-10rem)] md:flex-row">
        
        {/* Left Sidebar Tabs */}
        <div className="w-full md:w-64 shrink-0 flex flex-col gap-2">
           {tabs.map(tab => (
             <button
               key={tab.id}
               onClick={() => setActiveTab(tab.id)}
               className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl font-medium transition-colors text-left
                 ${activeTab === tab.id 
                   ? "bg-teal-600/10 text-teal-600 dark:text-teal-400 border border-teal-500/20 shadow-sm" 
                   : "text-slate-400 hover:bg-slate-800 hover:text-slate-200 border border-transparent"}`}
             >
                <tab.icon className={`h-5 w-5 ${activeTab === tab.id ? "text-teal-500" : "text-slate-500"}`} />
                {tab.label}
             </button>
           ))}
        </div>

        {/* Right Settings Content Area */}
        <div className="min-w-0 flex-1 overflow-y-auto rounded-2xl border border-slate-800 bg-slate-900/50 p-4 shadow-lg sm:p-6 lg:p-8 custom-scrollbar">
           
           {activeTab === "models" && (
             <div className="space-y-8 animate-in fade-in duration-300">
                <div className="border-b border-slate-800 pb-4 mb-6">
                  <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                    <Server className="h-5 w-5 text-teal-500" /> Cấu hình Kênh Suy luận (Inference Pipeline)
                  </h2>
                  <p className="text-sm text-slate-400 mt-1">Chọn phiên bản mô hình AI cốt lõi cho từng loại dữ liệu.</p>
                </div>

                {/* MRI Model Group */}
                <div className="space-y-4 max-w-2xl">
                   <label className="block text-sm font-bold text-slate-100 uppercase tracking-wider">1. Phân loại Khối u trên MRI (Tumor Classification)</label>
                   <div className="grid grid-cols-2 gap-4">
                     <label className="flex items-start gap-3 p-4 border border-teal-500/30 bg-teal-500/5 rounded-xl cursor-pointer">
                        <input type="radio" name="mri_model" defaultChecked className="mt-1 text-teal-500 bg-slate-800 border-slate-600 focus:ring-teal-500" />
                        <div>
                          <span className="block font-bold text-slate-200">ResNet-50 v4.2 (Production)</span>
                          <span className="text-xs text-slate-400 dark:text-slate-500 mt-1 block">Acc: 98.4% • Latency: 420ms</span>
                        </div>
                     </label>
                     <label className="flex items-start gap-3 p-4 border border-slate-800 bg-slate-900 rounded-xl cursor-pointer hover:border-slate-700">
                        <input type="radio" name="mri_model" className="mt-1 text-teal-500 bg-slate-800 border-slate-600 focus:ring-teal-500" />
                        <div>
                          <span className="block font-bold text-slate-200">DenseNet-121 v2.0 (Beta)</span>
                          <span className="text-xs text-slate-400 dark:text-slate-500 mt-1 block">Acc: 99.1% • Latency: 850ms</span>
                        </div>
                     </label>
                   </div>
                </div>

                {/* Object Detection Group */}
                <div className="space-y-4 max-w-2xl pt-2 border-t border-slate-800/50">
                   <label className="block text-sm font-bold text-slate-100 uppercase tracking-wider">2. Khoanh vùng Khối u (Segmentation)</label>
                   <select className="w-full bg-slate-800 border border-slate-700 text-slate-100 rounded-lg px-4 py-3 focus:outline-none focus:border-teal-500">
                      <option>U-Net Architecture (v3.1) - Preferred for Gliomas</option>
                      <option>YOLOv5 (v2.0) - Fast Detection</option>
                      <option>Mask R-CNN (Legacy)</option>
                   </select>
                </div>

                {/* Threshold Group */}
                <div className="space-y-4 max-w-2xl pt-2 border-t border-slate-800/50">
                   <div className="flex justify-between items-center">
                     <label className="block text-sm font-bold text-slate-100 uppercase tracking-wider">3. Ngưỡng Cảnh báo Rủi ro Sinh tồn</label>
                     <span className="text-xs font-mono font-bold text-teal-400 bg-teal-500/10 px-2 py-1 rounded">70 / 100</span>
                   </div>
                   <input type="range" min="0" max="100" defaultValue="70" className="w-full accent-teal-500" />
                   <div className="flex justify-between text-xs text-slate-500">
                      <span>Bảo thủ (Tăng tỷ lệ báo động giả)</span>
                      <span>Chặt chẽ (Giảm báo động giả)</span>
                   </div>
                </div>

             </div>
           )}

           {activeTab === "notifications" && (
              <div className="space-y-8 animate-in fade-in duration-300">
                 <div className="border-b border-slate-800 pb-4 mb-6">
                   <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                     <Bell className="h-5 w-5 text-teal-500" /> Cài đặt Thông báo
                   </h2>
                   <p className="text-sm text-slate-400 mt-1">Quản lý cách bạn nhận thông báo từ hệ thống.</p>
                 </div>
                 <div className="space-y-6 max-w-2xl">
                   <div className="flex items-center justify-between p-4 rounded-xl border border-slate-800 bg-slate-800/30">
                     <div>
                       <span className="block font-bold text-slate-200">Chẩn đoán hoàn thành</span>
                       <span className="text-xs text-slate-400 dark:text-slate-500">Nhận thông báo khi AI hoàn tất chẩn đoán.</span>
                     </div>
                     <input type="checkbox" defaultChecked className="h-5 w-5 accent-teal-500 bg-slate-800 border-slate-600 rounded" />
                   </div>
                   <div className="flex items-center justify-between p-4 rounded-xl border border-slate-800 bg-slate-800/30">
                     <div>
                       <span className="block font-bold text-slate-200">Cảnh báo rủi ro cao</span>
                       <span className="text-xs text-slate-400 dark:text-slate-500">Nhận cảnh báo khi phát hiện ca rủi ro cao.</span>
                     </div>
                     <input type="checkbox" defaultChecked className="h-5 w-5 accent-teal-500 bg-slate-800 border-slate-600 rounded" />
                   </div>
                   <div className="flex items-center justify-between p-4 rounded-xl border border-slate-800 bg-slate-800/30">
                     <div>
                       <span className="block font-bold text-slate-200">Email tổng hợp hàng ngày</span>
                       <span className="text-xs text-slate-400 dark:text-slate-500">Nhận báo cáo tổng hợp qua email mỗi ngày.</span>
                     </div>
                     <input type="checkbox" className="h-5 w-5 accent-teal-500 bg-slate-800 border-slate-600 rounded" />
                   </div>
                 </div>
              </div>
            )}

           {activeTab === "display" && (
              <div className="space-y-8 animate-in fade-in duration-300">
                 <div className="border-b border-slate-800 pb-4 mb-6">
                   <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                     <Monitor className="h-5 w-5 text-teal-500" /> Giao diện & Hiển thị
                   </h2>
                   <p className="text-sm text-slate-400 mt-1">Tùy chỉnh giao diện và cách hiển thị dữ liệu.</p>
                 </div>
                 <div className="space-y-6 max-w-2xl">
                   <div className="space-y-3">
                      <label className="block text-sm font-bold text-slate-100 uppercase tracking-wider">Chế độ giao diện</label>
                      <div className="grid grid-cols-2 gap-4">
                        <label className="flex items-center gap-3 p-4 border border-teal-500/30 bg-teal-500/5 rounded-xl cursor-pointer">
                           <input type="radio" name="theme" defaultChecked className="accent-teal-500" />
                           <span className="font-bold text-slate-200">Dark Mode</span>
                        </label>
                        <label className="flex items-center gap-3 p-4 border border-slate-800 bg-slate-900 rounded-xl cursor-pointer hover:border-slate-700">
                           <input type="radio" name="theme" className="accent-teal-500" />
                           <span className="font-bold text-slate-200">Light Mode</span>
                        </label>
                      </div>
                   </div>
                   <div className="space-y-3 pt-2 border-t border-slate-800/50">
                      <label className="block text-sm font-bold text-slate-100 uppercase tracking-wider">Kích thước chữ</label>
                      <select defaultValue="Vừa (14px)" className="w-full bg-slate-800 border border-slate-700 text-slate-100 rounded-lg px-4 py-3 focus:outline-none focus:border-teal-500">
                         <option>Nhỏ (12px)</option>
                         <option>Vừa (14px)</option>
                         <option>Lớn (16px)</option>
                      </select>
                   </div>
                 </div>
              </div>
            )}

           {activeTab === "security" && (
              <div className="space-y-8 animate-in fade-in duration-300">
                 <div className="border-b border-slate-800 pb-4 mb-6">
                   <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                     <Shield className="h-5 w-5 text-teal-500" /> Bảo mật & Phân quyền
                   </h2>
                   <p className="text-sm text-slate-400 mt-1">Quản lý mật khẩu và phiên đăng nhập.</p>
                 </div>
                 <div className="space-y-6 max-w-2xl">
                   <div className="space-y-3">
                      <label className="block text-sm font-bold text-slate-100 uppercase tracking-wider">Đổi mật khẩu</label>
                      <input type="password" placeholder="Mật khẩu hiện tại" className="w-full bg-slate-800 border border-slate-700 text-slate-100 rounded-lg px-4 py-3 focus:outline-none focus:border-teal-500" />
                      <input type="password" placeholder="Mật khẩu mới" className="w-full bg-slate-800 border border-slate-700 text-slate-100 rounded-lg px-4 py-3 focus:outline-none focus:border-teal-500" />
                      <input type="password" placeholder="Xác nhận mật khẩu mới" className="w-full bg-slate-800 border border-slate-700 text-slate-100 rounded-lg px-4 py-3 focus:outline-none focus:border-teal-500" />
                      <button onClick={() => alert('Đổi mật khẩu thành công!')} className="px-5 py-2.5 bg-teal-600 hover:bg-teal-500 text-white font-bold rounded-xl transition-all">
                        Cập nhật mật khẩu
                      </button>
                   </div>
                   <div className="space-y-3 pt-4 border-t border-slate-800/50">
                      <label className="block text-sm font-bold text-slate-100 uppercase tracking-wider">Phiên đăng nhập</label>
                      <div className="p-4 rounded-xl border border-slate-800 bg-slate-800/30 flex items-center justify-between">
                        <div>
                          <span className="block font-bold text-slate-200">Phiên hiện tại</span>
                          <span className="text-xs text-slate-500">Windows • Chrome • Đăng nhập lúc {'phiên này'}</span>
                        </div>
                        <span className="px-3 py-1 rounded-full text-xs font-bold bg-teal-500/10 text-teal-500 border border-teal-500/20">Đang hoạt động</span>
                      </div>
                   </div>
                 </div>
              </div>
            )}

        </div>

      </div>

    </div>
  );
}
