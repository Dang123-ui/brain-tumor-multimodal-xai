"use client";

import { useCallback, useState } from "react";
import { apiBaseUrl } from "@/lib/api";

type StreamEvent = {
  event: string;
  data: unknown;
};

function parseSseChunk(chunk: string): StreamEvent[] {
  return chunk
    .split("\n\n")
    .map((block) => block.trim())
    .filter(Boolean)
    .map((block) => {
      const eventLine = block
        .split("\n")
        .find((line) => line.startsWith("event:"));
      const dataLine = block
        .split("\n")
        .find((line) => line.startsWith("data:"));
      const event = eventLine?.replace("event:", "").trim() || "message";
      const rawData = dataLine?.replace("data:", "").trim() || "null";
      try {
        return { event, data: JSON.parse(rawData) };
      } catch {
        return { event, data: rawData };
      }
    });
}

export function useAgentStream() {
  const [streaming, setStreaming] = useState(false);

  const streamChat = useCallback(
    async (
      payload: Record<string, unknown>,
      handlers: {
        onToken?: (token: string) => void;
        onEvent?: (event: StreamEvent) => void;
        onFinal?: (data: unknown) => void;
        onError?: (error: Error) => void;
      },
    ) => {
      setStreaming(true);
      try {
        const token = localStorage.getItem("token");
        const response = await fetch(`${apiBaseUrl()}/agent/chat/stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify(payload),
        });

        if (!response.ok || !response.body) {
          throw new Error(`Agent stream failed: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const boundary = buffer.lastIndexOf("\n\n");
          if (boundary === -1) continue;

          const ready = buffer.slice(0, boundary + 2);
          buffer = buffer.slice(boundary + 2);

          for (const event of parseSseChunk(ready)) {
            handlers.onEvent?.(event);
            if (event.event === "token") {
              handlers.onToken?.(String(event.data));
            }
            if (event.event === "final") {
              handlers.onFinal?.(event.data);
            }
          }
        }
      } catch (error) {
        handlers.onError?.(error as Error);
      } finally {
        setStreaming(false);
      }
    },
    [],
  );

  return { streaming, streamChat };
}
