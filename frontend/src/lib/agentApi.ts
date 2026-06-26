import { api } from "@/lib/api";

export type AgentMessageRole = "user" | "assistant" | "tool" | "error";

export type AgentChatResponse = {
  thread_id: string;
  message: string;
  intent: string;
  actions: Array<Record<string, unknown>>;
  tool_results?: Record<string, unknown>;
};

export type AgentConversation = {
  thread_id: string;
  patient_id?: number | null;
  image_id?: number | null;
  title?: string | null;
  status: string;
  summary?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type AgentStoredMessage = {
  id: number;
  role: AgentMessageRole;
  content?: string | null;
  message_type?: string;
  metadata?: Record<string, unknown> | null;
  created_at?: string | null;
};

export type AgentPatient = {
  id: number;
  patient_external_id?: string | null;
  name?: string | null;
  age?: number | null;
  gender?: string | null;
};

export type QuickMriResponse = {
  message: string;
  patient: {
    id: number;
    patient_external_id?: string | null;
    name?: string | null;
  };
  image_id: number;
  task_id: number;
  status: string;
  summary: string;
};

export const agentApi = {
  chat: async (payload: {
    message: string;
    thread_id?: string;
    patient_id?: string;
    image_id?: number;
    selected_region?: Record<string, unknown>;
  }) => {
    return api.post<AgentChatResponse>("/agent/chat", payload);
  },

  searchPatients: async (query: string) => {
    return api.get<{ items: AgentPatient[] }>("/agent/patients/search", {
      params: { q: query, limit: 8 },
    });
  },

  quickMri: async (payload: { patientId?: string; file: File }) => {
    const formData = new FormData();
    formData.append("file", payload.file);
    if (payload.patientId?.trim()) {
      formData.append("patient_id", payload.patientId.trim());
    }
    return api.post<QuickMriResponse>("/agent/quick-mri", formData, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 1200000,
    });
  },

  quickMriSummary: async (imageId: string | number) => {
    return api.get<{
      image_id: number;
      patient_id: string;
      status: string;
      summary: string;
      result: Record<string, unknown>;
    }>(`/agent/quick-mri/${imageId}/summary`);
  },

  notifications: async () => {
    return api.get<{ items: Array<{ type: string; message: string }> }>(
      "/agent/notifications",
    );
  },

  conversations: async () => {
    return api.get<{ items: AgentConversation[] }>("/agent/conversations");
  },

  conversationMessages: async (threadId: string) => {
    return api.get<{ thread_id: string; messages: AgentStoredMessage[] }>(
      `/agent/conversations/${encodeURIComponent(threadId)}`,
    );
  },

  deleteConversation: async (threadId: string) => {
    return api.delete<{ deleted: boolean }>(
      `/agent/conversations/${encodeURIComponent(threadId)}`,
    );
  },
};
