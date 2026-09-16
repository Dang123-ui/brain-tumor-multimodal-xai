"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { 
  LayoutDashboard, 
  Users, 
  Upload, 
  History, 
  FileText, 
  Settings,
  BrainCircuit,
  MessagesSquare,
  LogOut,
  X
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";

const navItems = [
  { name: "Tổng quan", href: "/", icon: LayoutDashboard },
  { name: "Bệnh nhân", href: "/patients", icon: Users },
  { name: "Tải lên DICOM/WSI", href: "/upload", icon: Upload },
  { name: "Lịch sử Chẩn đoán", href: "/history", icon: History },
  { name: "Báo cáo AI", href: "/reports", icon: FileText },
  { name: "NeuroBoard", href: "/neuroboard", icon: MessagesSquare },
];

type SidebarProps = {
  open: boolean;
  onClose: () => void;
};

export function Sidebar({ open, onClose }: SidebarProps) {
  const pathname = usePathname();
  const { logout } = useAuth();

  return (
    <>
      {open && (
        <button
          type="button"
          aria-label="Đóng điều hướng"
          className="fixed inset-0 z-40 bg-slate-950/55 backdrop-blur-sm"
          onClick={onClose}
        />
      )}
      <aside
        className={cn(
          "fixed left-0 top-0 z-50 flex h-dvh w-[min(20rem,calc(100vw-2rem))] flex-col border-r border-slate-800 bg-slate-900 text-slate-100 shadow-2xl shadow-slate-950/40 transition-transform duration-200 ease-out sm:w-80",
          open ? "translate-x-0" : "-translate-x-full",
        )}
        aria-hidden={!open}
      >
      {/* App Logo */}
      <div className="flex items-center justify-between gap-3 px-5 py-5">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-teal-600">
            <BrainCircuit className="h-5 w-5 text-white" />
          </div>
          <span className="truncate text-lg font-semibold tracking-tight">NeuroDiagnosis AI</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-100"
          title="Đóng điều hướng"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Navigation */}
      <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto px-4 py-4">
        {navItems.map((item) => {
          const isActive = pathname === item.href || (item.href !== "/" && pathname?.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onClose}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                isActive 
                  ? "bg-teal-600/10 text-teal-500 border-l-2 border-teal-500 rounded-l-none" 
                  : "text-slate-400 hover:bg-slate-800 hover:text-slate-100"
              )}
            >
              <item.icon className={cn("h-5 w-5", isActive ? "text-teal-500" : "text-slate-400")} />
              {item.name}
            </Link>
          );
        })}
      </nav>

      {/* Bottom Section */}
      <div className="p-4 space-y-2">
        <Link
          href="/settings"
          onClick={onClose}
          className={cn(
            "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors mb-4",
            pathname?.startsWith("/settings")
              ? "bg-teal-600/10 text-teal-500 border-l-2 border-teal-500 rounded-l-none" 
              : "text-slate-400 hover:bg-slate-800 hover:text-slate-100"
          )}
        >
          <Settings className="h-5 w-5" />
          Cài đặt
        </Link>
        
        <button
          type="button"
          onClick={() => {
            onClose();
            logout();
          }}
          className="mb-4 flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium text-red-300 transition-colors hover:bg-red-500/10 hover:text-red-200"
        >
          <LogOut className="h-5 w-5" />
          Đăng xuất
        </button>

        {/* System Status Panel */}
        <div className="rounded-xl border border-slate-800 bg-slate-800/50 p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">System Status</span>
            <div className="h-2 w-2 rounded-full bg-teal-500 shadow-[0_0_8px_rgba(20,184,166,0.6)]"></div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-300">Tăng tốc GPU:</span>
            <span className="text-sm font-medium text-teal-500">Active</span>
          </div>
        </div>
      </div>
    </aside>
    </>
  );
}
