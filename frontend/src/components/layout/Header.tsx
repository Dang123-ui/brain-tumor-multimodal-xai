"use client";

import { Bell, Menu, Moon, Sun } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/contexts/ThemeContext";

function displayName(username?: string, role?: string) {
  if (!username) return role === "admin" ? "Admin" : "Tài khoản";
  if (username === "admin") return "Admin";

  const cleaned = username.replace(/^doctor_/, "").replace(/[_-]+/g, " ").trim();
  const name = cleaned
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");

  return role === "doctor" ? `Dr. ${name || username}` : name || username;
}

function roleLabel(role?: string) {
  if (role === "admin") return "Administrator";
  if (role === "researcher") return "Senior Researcher";
  if (role === "doctor") return "Neuroradiologist";
  return "NeuroDiagnosis User";
}

export function Header({ onOpenSidebar }: { onOpenSidebar: () => void }) {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const name = displayName(user?.username, user?.role);
  const subtitle = user?.username === "admin" ? "Administrator" : roleLabel(user?.role);
  const avatarSeed = encodeURIComponent(user?.username || user?.id || "user");

  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-slate-800 bg-slate-900/80 px-3 backdrop-blur-sm md:px-6">
      {/* Left: Page context breadcrumb */}
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <button
          type="button"
          onClick={onOpenSidebar}
          className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-slate-800 bg-slate-950/40 text-slate-300 transition-colors hover:border-teal-500/40 hover:bg-slate-800 hover:text-slate-100"
          title="Mở điều hướng"
        >
          <Menu className="h-5 w-5" />
        </button>
        <span className="text-sm font-medium text-slate-500">NeuroDiagnosis AI</span>
      </div>

      {/* Right Navigation */}
      <div className="ml-auto flex items-center gap-2 md:gap-4">
        {/* Language indicator (VN only — EN hidden per decision) */}
        <span className="hidden items-center rounded-lg border border-slate-700 bg-slate-800 px-3 py-1 text-xs font-medium text-slate-300 sm:flex">
          🇻🇳 VN
        </span>

        {/* Theme Toggle */}
        <button 
          onClick={toggleTheme}
          className="rounded-full p-2 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
          title={theme === "dark" ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối"}
        >
          {theme === "dark" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </button>

        {/* Notifications */}
        <button className="relative rounded-full p-2 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors">
          <Bell className="h-5 w-5" />
          <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-red-500 border-2 border-slate-900"></span>
        </button>

        {/* User Profile */}
        <div className="ml-1 flex items-center gap-3 border-l border-slate-700 pl-3 md:ml-2 md:pl-4">
          <div className="hidden flex-col items-end lg:flex">
            <span className="text-sm font-semibold text-slate-200">
              {name}
            </span>
            <span className="text-xs text-slate-400">
              {subtitle}
            </span>
          </div>
          <button onClick={logout} className="relative h-9 w-9 overflow-hidden rounded-full bg-slate-700 hover:ring-2 hover:ring-teal-500 transition-all">
            {/* Remote avatar service is intentionally rendered without Next image optimization. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img 
              src={`https://api.dicebear.com/7.x/avataaars/svg?seed=${avatarSeed}&backgroundColor=0d9488`}
              alt={name}
              className="h-full w-full object-cover"
            />
          </button>
        </div>
      </div>
    </header>
  );
}
