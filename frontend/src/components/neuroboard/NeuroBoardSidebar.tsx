"use client";

import {
  Bookmark,
  ClipboardList,
  Newspaper,
  Stethoscope,
} from "lucide-react";
import type { NeuroFeedScope, NeuroPostType } from "./types";

export type NeuroBoardView = "feed" | "review_queue" | "my_cases";

type Props = {
  activeView: NeuroBoardView;
  scope: NeuroFeedScope;
  postType?: NeuroPostType;
  onViewChange: (view: NeuroBoardView) => void;
  onScopeChange: (scope: NeuroFeedScope) => void;
  onTypeChange: (postType?: NeuroPostType) => void;
};

const viewItems = [
  { value: "feed" as const, label: "Feed", icon: Newspaper },
  { value: "review_queue" as const, label: "Review Queue", icon: ClipboardList },
  { value: "my_cases" as const, label: "My Cases", icon: Stethoscope },
];

export function NeuroBoardSidebar({
  activeView,
  scope,
  postType,
  onViewChange,
  onScopeChange,
  onTypeChange,
}: Props) {
  return (
    <aside className="sticky top-24 hidden h-fit space-y-6 xl:block">
      <div>
        <p className="mb-2 px-3 text-xs font-semibold uppercase text-slate-500">
          NeuroBoard
        </p>
        <nav className="space-y-1" aria-label="NeuroBoard navigation">
          {viewItems.map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => onViewChange(item.value)}
              className={`flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm font-medium transition ${
                activeView === item.value
                  ? "bg-white text-[#0D47A1] shadow-sm ring-1 ring-[#90CAF9]"
                  : "text-[#0F172A] hover:bg-white/80"
              }`}
            >
              <item.icon className="h-5 w-5" />
              {item.label}
            </button>
          ))}
        </nav>
      </div>

      {activeView === "feed" && (
        <div className="border-t border-[#90CAF9] pt-5">
          <p className="mb-2 px-3 text-xs font-semibold uppercase text-slate-500">
            Feed filters
          </p>
          <div className="space-y-1">
            <button
              type="button"
              onClick={() => onScopeChange("all")}
              className={`flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm ${
                scope === "all" ? "bg-white font-semibold text-[#0D47A1] shadow-sm ring-1 ring-[#90CAF9]" : "text-[#0F172A] hover:bg-white/80"
              }`}
            >
              <Newspaper className="h-5 w-5" />
              Feed
            </button>
            <button
              type="button"
              onClick={() => onScopeChange("saved")}
              className={`flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm ${
                scope === "saved" ? "bg-white font-semibold text-[#0D47A1] shadow-sm ring-1 ring-[#90CAF9]" : "text-[#0F172A] hover:bg-white/80"
              }`}
            >
              <Bookmark className="h-5 w-5" />
              Saved
            </button>
            <button
              type="button"
              onClick={() => onTypeChange(undefined)}
              className={`flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm ${
                !postType ? "bg-white font-semibold text-[#0D47A1] shadow-sm ring-1 ring-[#90CAF9]" : "text-[#0F172A] hover:bg-white/80"
              }`}
            >
              All posts
            </button>
            <button
              type="button"
              onClick={() => onTypeChange("normal")}
              className={`flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm ${
                postType === "normal" ? "bg-white font-semibold text-[#0D47A1] shadow-sm ring-1 ring-[#90CAF9]" : "text-[#0F172A] hover:bg-white/80"
              }`}
            >
              Normal posts
            </button>
            <button
              type="button"
              onClick={() => onTypeChange("clinical_case")}
              className={`flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm ${
                postType === "clinical_case" ? "bg-white font-semibold text-[#0D47A1] shadow-sm ring-1 ring-[#90CAF9]" : "text-[#0F172A] hover:bg-white/80"
              }`}
            >
              Clinical Case
            </button>
          </div>
        </div>
      )}
    </aside>
  );
}
