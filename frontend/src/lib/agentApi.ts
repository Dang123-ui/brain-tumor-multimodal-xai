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

export type AgentChatPayload = {
  message: string;
  thread_id?: string;
  current_page?: string;
  patient_id?: string;
  image_id?: number;
  selected_region?: Record<string, unknown>;
};

export type AgentStreamFinal = {
  thread_id: string;
  intent: string;
  message: string;
  actions: Array<Record<string, unknown>>;
};

export type AgentStreamToolResult = {
  intent?: string;
  actions?: Array<Record<string, unknown>>;
  tool_results?: Record<string, unknown>;
};

type AgentStreamHandlers = {
  onStatus?: (data: Record<string, unknown>) => void;
  onToolResult?: (data: AgentStreamToolResult) => void;
  onToken?: (token: string) => void;
  onFinal?: (data: AgentStreamFinal) => void;
};

function apiBaseUrl() {
  return String(api.defaults.baseURL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
}

function authHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function dispatchSseEvent(
  rawEvent: string,
  handlers: AgentStreamHandlers,
) {
  const lines = rawEvent.split(/\r?\n/);
  const event = lines
    .find((line) => line.startsWith("event:"))
    ?.slice("event:".length)
    .trim();
  const dataText = lines
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice("data:".length).trimStart())
    .join("\n");

  if (!event || !dataText) return;

  let data: unknown;
  try {
    data = JSON.parse(dataText);
  } catch {
    data = dataText;
  }

  if (event === "status" && typeof data === "object" && data !== null) {
    handlers.onStatus?.(data as Record<string, unknown>);
  }
  if (event === "tool_result" && typeof data === "object" && data !== null) {
    handlers.onToolResult?.(data as AgentStreamToolResult);
  }
  if (event === "token") {
    handlers.onToken?.(typeof data === "string" ? data : String(data ?? ""));
  }
  if (event === "final" && typeof data === "object" && data !== null) {
    handlers.onFinal?.(data as AgentStreamFinal);
  }
}

export const agentApi = {
  chat: async (payload: AgentChatPayload) => {
    return api.post<AgentChatResponse>("/agent/chat", payload);
  },

  chatStream: async (
    payload: AgentChatPayload,
    handlers: AgentStreamHandlers,
  ) => {
    const response = await fetch(`${apiBaseUrl()}/agent/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      let detail = response.statusText || "Agent stream failed";
      try {
        const errorBody = await response.json();
        detail = errorBody.detail || detail;
      } catch {
        // Keep HTTP status text when the body is not JSON.
      }
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }

    if (!response.body) {
      throw new Error("Trình duyệt không hỗ trợ stream response.");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split(/\n\n/);
      buffer = events.pop() || "";
      events.forEach((event) => dispatchSseEvent(event, handlers));
    }

    buffer += decoder.decode();
    if (buffer.trim()) {
      dispatchSseEvent(buffer, handlers);
    }
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
