"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { AgentWidgetProvider } from "@/contexts/AgentWidgetContext";
import { AgentFloatingWidget } from "@/components/agent/AgentFloatingWidget";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    if (!loading && !user) {
      window.location.href = "/login";
    }
  }, [user, loading, router]);

  if (loading || (!loading && !user)) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center border-t-teal-500">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 rounded-full border-4 border-t-teal-500 border-slate-700 animate-spin" />
          <span className="text-slate-400 text-sm">
            {!loading && !user ? "Đang chuyển hướng đến trang đăng nhập..." : "Đang xác thực..."}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen overflow-x-hidden bg-slate-950 text-slate-200 font-sans selection:bg-teal-500/30">
      <AgentWidgetProvider>
        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        <div className="flex min-h-screen min-w-0 flex-col">
          <Header onOpenSidebar={() => setSidebarOpen(true)} />
          <main className="relative min-w-0 flex-1 overflow-x-hidden p-3 sm:p-4 lg:p-6">
            {children}
          </main>
        </div>
        <AgentFloatingWidget />
      </AgentWidgetProvider>
    </div>
  );
}
