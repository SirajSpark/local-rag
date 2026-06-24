import { FileText } from "lucide-react";
import type { CitationSource } from "../../types";

interface CitationCardProps {
  citation: CitationSource;
}

export function CitationCard({ citation }: CitationCardProps) {
  return (
    <div className="rounded-lg border border-zinc-700/50 bg-zinc-800 p-2.5">
      <div className="flex items-center gap-1.5 text-xs text-zinc-400">
        <FileText className="h-3.5 w-3.5" />
        <span className="font-medium text-zinc-300">{citation.filename}</span>
      </div>
    </div>
  );
}
