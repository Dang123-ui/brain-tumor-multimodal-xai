"use client";

import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";

type AgentWidgetMode = "bubble" | "panel" | "expanded";

type AgentWidgetContextValue = {
  mode: AgentWidgetMode;
  setMode: (mode: AgentWidgetMode) => void;
  activeThreadId?: string;
  setActiveThreadId: (threadId?: string) => void;
  draftMessage: string;
  setDraftMessage: (message: string) => void;
  selectedPatientId?: string;
  setSelectedPatientId: (patientId?: string) => void;
  selectedImageId?: number;
  setSelectedImageId: (imageId?: number) => void;
};

const AgentWidgetContext = createContext<AgentWidgetContextValue | null>(null);
const ACTIVE_THREAD_STORAGE_KEY = "neuro-agent-active-thread-id";

export function AgentWidgetProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<AgentWidgetMode>("bubble");
  const [activeThreadIdState, setActiveThreadIdState] = useState<string | undefined>(() => {
    if (typeof window === "undefined") return undefined;
    return localStorage.getItem(ACTIVE_THREAD_STORAGE_KEY) || undefined;
  });
  const [draftMessage, setDraftMessage] = useState("");
  const [selectedPatientId, setSelectedPatientId] = useState<string | undefined>();
  const [selectedImageId, setSelectedImageId] = useState<number | undefined>();

  const setActiveThreadId = useCallback((threadId?: string) => {
    setActiveThreadIdState(threadId);
    if (typeof window === "undefined") return;
    if (threadId) {
      localStorage.setItem(ACTIVE_THREAD_STORAGE_KEY, threadId);
    } else {
      localStorage.removeItem(ACTIVE_THREAD_STORAGE_KEY);
    }
  }, []);

  const value = useMemo(
    () => ({
      mode,
      setMode,
      activeThreadId: activeThreadIdState,
      setActiveThreadId,
      draftMessage,
      setDraftMessage,
      selectedPatientId,
      setSelectedPatientId,
      selectedImageId,
      setSelectedImageId,
    }),
    [mode, activeThreadIdState, setActiveThreadId, draftMessage, selectedPatientId, selectedImageId],
  );

  return (
    <AgentWidgetContext.Provider value={value}>
      {children}
    </AgentWidgetContext.Provider>
  );
}

export function useAgentWidget() {
  const context = useContext(AgentWidgetContext);
  if (!context) {
    throw new Error("useAgentWidget must be used inside AgentWidgetProvider");
  }
  return context;
}
