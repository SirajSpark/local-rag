import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from "react";
import { ArrowUp, Trash2 } from "lucide-react";
import { ChatMessage } from "./ChatMessage";
import { cn } from "../../lib/utils";
import type { ChatMessage as ChatMessageType } from "../../types";

interface ChatWindowProps {
  messages: ChatMessageType[];
  isLoading: boolean;
  onSend: (question: string) => void;
  onClear: () => void;
}

export function ChatWindow({
  messages,
  isLoading,
  onSend,
  onClear,
}: ChatWindowProps) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const autoResize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  useEffect(() => {
    autoResize();
  }, [input, autoResize]);

  function handleSubmit() {
    if (!input.trim() || isLoading) return;
    onSend(input.trim());
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  const hasInput = input.trim().length > 0;

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto min-h-0">
        {messages.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <div className="max-w-md text-center">
              <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-zinc-800 border border-zinc-700">
                <svg className="h-6 w-6 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
                </svg>
              </div>
              <h2 className="mb-2 text-lg font-semibold text-zinc-100">
                Ask about your documents
              </h2>
              <p className="text-sm text-zinc-500">
                Upload a document in the sidebar, then ask questions about its contents.
                The assistant will answer with citations from your documents.
              </p>
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-2xl space-y-4 px-4 py-6">
            {messages.map((msg) => (
              <ChatMessage key={msg.id} message={msg} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="mx-auto w-full max-w-2xl px-4 pb-6">
        <div className="relative rounded-xl border border-zinc-800 bg-zinc-900 focus-within:ring-1 focus-within:ring-teal-500/30 focus-within:border-zinc-700 transition-colors">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything..."
            disabled={isLoading}
            rows={1}
            maxLength={2000}
            aria-label="Ask a question about your documents"
            className="w-full resize-none bg-transparent px-4 pt-3 pb-10 text-sm text-zinc-100 placeholder:text-zinc-500 focus:outline-none disabled:opacity-50"
          />
          <div className="absolute bottom-2 right-2 flex items-center gap-1.5">
            {input.length > 0 && (
              <span
                className={cn(
                  "text-xs tabular-nums",
                  input.length >= 2000 ? "text-red-400" : "text-zinc-500",
                )}
              >
                {input.length}/2000
              </span>
            )}
            {messages.length > 0 && (
              <button
                type="button"
                onClick={onClear}
                title="Clear chat"
                className="rounded-lg p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300 transition-colors"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            )}
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!hasInput || isLoading}
              className={cn(
                "flex h-7 w-7 items-center justify-center rounded-full transition-colors",
                hasInput
                  ? "bg-teal-500 text-zinc-950 hover:bg-teal-400"
                  : "bg-zinc-800 text-zinc-600",
              )}
            >
              <ArrowUp className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
