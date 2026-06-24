"use client";

import {
  createContext,
  ReactNode,
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

export function AgentWidgetProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<AgentWidgetMode>("bubble");
  const [activeThreadId, setActiveThreadId] = useState<string | undefined>();
  const [draftMessage, setDraftMessage] = useState("");
  const [selectedPatientId, setSelectedPatientId] = useState<string | undefined>();
  const [selectedImageId, setSelectedImageId] = useState<number | undefined>();

  const value = useMemo(
    () => ({
      mode,
      setMode,
      activeThreadId,
      setActiveThreadId,
      draftMessage,
      setDraftMessage,
      selectedPatientId,
      setSelectedPatientId,
      selectedImageId,
      setSelectedImageId,
    }),
    [mode, activeThreadId, draftMessage, selectedPatientId, selectedImageId],
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

