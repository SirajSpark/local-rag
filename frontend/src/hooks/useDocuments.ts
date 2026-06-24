import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { DocumentListResponse } from "../types";

const DOCUMENTS_KEY = ["documents"] as const;

export function useDocuments() {
  return useQuery<DocumentListResponse>({
    queryKey: DOCUMENTS_KEY,
    queryFn: () => api.get<DocumentListResponse>("/api/documents"),
    refetchInterval: (query) => {
      const docs = query.state.data?.documents;
      if (!docs) return false;

      const now = Date.now();
      const needsUpdate = docs.some((d) => {
        if (d.status === "processing") return true;
        if (d.status === "completed" && !d.summary) {
          const ageMs = now - new Date(d.created_at).getTime();
          return ageMs < 5 * 60 * 1000; // give up after 5 min
        }
        return false;
      });

      return needsUpdate ? 2_000 : false;
    },
  });
}
