import { useState } from "react";
import { FileText, Trash2, ChevronRight } from "lucide-react";
import type { Document } from "../../types";
import { StatusBadge } from "./StatusBadge";
import { Button } from "../ui/Button";
import { useDeleteDocument } from "../../hooks/useDeleteDocument";

interface DocumentItemProps {
  doc: Document;
}

export function DocumentItem({ doc }: DocumentItemProps) {
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [summaryExpanded, setSummaryExpanded] = useState(false);
  const deleteMutation = useDeleteDocument();

  const hasSummary = doc.status === "completed" && doc.summary;

  const handleConfirmDelete = () => {
    deleteMutation.mutate(doc.id, {
      onSuccess: () => setShowDeleteModal(false),
      onError: () => setShowDeleteModal(false),
    });
  };

  return (
    <div className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900">
      {/* Row 1: File info */}
      <div className="flex items-center gap-3 px-4 py-3">
        <FileText className="h-5 w-5 flex-shrink-0 text-zinc-500" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-zinc-200" title={doc.filename}>
            {doc.filename}
          </p>
          <div className="mt-0.5 flex items-center gap-1.5 text-xs text-zinc-500">
            <span>{new Date(doc.created_at).toLocaleDateString()}</span>
            <span aria-hidden="true">&middot;</span>
            <StatusBadge status={doc.status} />
          </div>
        </div>
        <div className="flex-shrink-0">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowDeleteModal(true)}
            className="text-zinc-500 hover:text-red-400"
            disabled={doc.status === "processing"}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Summary expand */}
      {hasSummary && (
        <div className="border-t border-zinc-800/50">
          <button
            onClick={() => setSummaryExpanded(!summaryExpanded)}
            className="flex w-full items-center gap-2 px-4 py-2 text-xs font-medium text-zinc-500 hover:bg-zinc-800/50"
          >
            <ChevronRight
              className={`h-3.5 w-3.5 transition-transform duration-200 ${summaryExpanded ? "rotate-90" : ""}`}
            />
            Summary
          </button>
          {summaryExpanded && (
            <div className="border-t border-zinc-800/50 px-4 pb-3 pt-2">
              <p className="text-xs leading-relaxed text-zinc-400">
                {doc.summary}
              </p>
            </div>
          )}
        </div>
      )}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="mx-4 w-full max-w-sm rounded-lg bg-zinc-900 border border-zinc-800 p-6 shadow-xl">
            <h3 className="text-lg font-semibold text-zinc-100">Delete document</h3>
            <p className="mt-2 text-sm text-zinc-400">
              Are you sure you want to delete "{doc.filename}"?
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setShowDeleteModal(false)}>
                Cancel
              </Button>
              <Button variant="danger" onClick={handleConfirmDelete} loading={deleteMutation.isPending}>
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
