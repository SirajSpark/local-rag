import ReactMarkdown from "react-markdown";
import type { ChatMessage } from "../../types";
import { CitationCard } from "./CitationCard";
import { cn } from "../../lib/utils";

interface ChatMessageProps {
  message: ChatMessage;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";
  const isThinking = !message.content && !message.error && !message.citations?.length;

  if (isThinking) {
    return (
      <div className="flex justify-start">
        <p className="px-1 py-2 text-sm text-zinc-500 animate-pulse">
          Thinking...
        </p>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex",
        isUser ? "justify-end" : "justify-start",
      )}
    >
      <div
        className={cn(
          "max-w-[80%] rounded-lg px-4 py-2",
          isUser
            ? "bg-[#134e4a] text-teal-50 border border-[#1a5c54]"
            : "bg-zinc-900 text-zinc-100 border border-zinc-800",
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap text-sm leading-relaxed">
            {message.content}
          </p>
        ) : (
          <div className="prose prose-sm prose-invert max-w-none">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        )}

        {message.error && (
          <p className="text-xs text-red-400">{message.error}</p>
        )}

        {message.citations && message.citations.length > 0 && (
          <div className="mt-3 space-y-2 border-t border-zinc-700/50 pt-3">
            <p className="text-xs font-medium text-zinc-500">Sources</p>
            {message.citations.map((citation, i) => (
              <CitationCard key={i} citation={citation} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
