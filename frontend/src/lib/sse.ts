import { SSE_URL } from "./api";
import { SseEventSchema, type CitationSource } from "../types";

export type SSECallback = (
  event: "token" | "citations",
  data: string | CitationSource[],
) => void;

const DEFAULT_TIMEOUT_MS = Number(
  import.meta.env.VITE_SSE_TIMEOUT_MS ?? 600_000,
);

export function createSSEConnection(
  path: string,
  body: unknown,
  onEvent: SSECallback,
  onError: (error: Error) => void,
  onComplete: () => void,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): AbortController {
  const controller = new AbortController();
  let reported = false;

  const safeError = (err: Error) => {
    if (!reported) {
      reported = true;
      onError(err);
    }
  };

  const timeoutId = setTimeout(() => {
    controller.abort();
    safeError(new Error("SSE connection timed out"));
  }, timeoutMs);

  fetch(SSE_URL(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok || !response.body) {
        throw new Error(`SSE connection failed: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data: ")) continue;

            let parsed;
            try {
              const result = SseEventSchema.safeParse(JSON.parse(trimmed.slice(6)));
              if (!result.success) {
                console.warn("Invalid SSE payload:", result.error.format());
                continue;
              }
              parsed = result.data;
            } catch {
              console.warn("Malformed SSE line:", trimmed);
              continue;
            }

            if (parsed.event === "done") {
              clearTimeout(timeoutId);
              reader.cancel();
              onComplete();
              return;
            }

            if (parsed.event === "error") {
              clearTimeout(timeoutId);
              reader.cancel();
              safeError(new Error(parsed.data));
              return;
            }

            onEvent(parsed.event, parsed.data);
          }
        }
        clearTimeout(timeoutId);
      } finally {
        reader.releaseLock();
      }
    })
    .catch((error) => {
      clearTimeout(timeoutId);
      if (error instanceof DOMException && error.name === "AbortError") return;
      safeError(error instanceof Error ? error : new Error(String(error)));
    });

  return controller;
}
