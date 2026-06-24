import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

interface DeleteResponse {
  message: string;
  document_id: string;
}

export function useDeleteDocument() {
  const queryClient = useQueryClient();

  return useMutation<DeleteResponse, Error, string>({
    mutationFn: (documentId) =>
      api.delete<DeleteResponse>(`/api/documents/${documentId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}
