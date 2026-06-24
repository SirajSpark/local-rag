import { z } from "zod";

export const CitationSourceSchema = z.object({
  filename: z.string(),
});
export type CitationSource = z.infer<typeof CitationSourceSchema>;

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: CitationSource[];
  error?: string;
}

export const SseTokenEventSchema = z.object({
  event: z.literal("token"),
  data: z.string(),
});

export const SseCitationsEventSchema = z.object({
  event: z.literal("citations"),
  data: z.array(CitationSourceSchema),
});

export const SseErrorEventSchema = z.object({
  event: z.literal("error"),
  data: z.string(),
});

export const SseDoneEventSchema = z.object({
  event: z.literal("done"),
  data: z.unknown(),
});

export const SseEventSchema = z.discriminatedUnion("event", [
  SseTokenEventSchema,
  SseCitationsEventSchema,
  SseErrorEventSchema,
  SseDoneEventSchema,
]);
