import { useCallback, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../lib/api";
import type { ConflictDetail, UploadResponse } from "../types";

export function useUpload() {
  const queryClient = useQueryClient();
  const [conflict, setConflict] = useState<ConflictDetail | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);

  const uploadMutation = useMutation<UploadResponse, Error, File>({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return api.post<UploadResponse>("/api/documents/upload", formData);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      setConflict(null);
      setPendingFile(null);
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409 && error.detail) {
        const detail = error.detail as unknown as ConflictDetail;
        setConflict(detail);
      }
    },
  });

  const reingestMutation = useMutation<UploadResponse, Error, { documentId: string; file: File }>({
    mutationFn: async ({ documentId, file }) => {
      const formData = new FormData();
      formData.append("file", file);
      return api.put<UploadResponse>(
        `/api/documents/${documentId}/reingest`,
        formData,
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      setConflict(null);
      setPendingFile(null);
      uploadMutation.reset();
    },
  });

  const mutate = useCallback(
    (file: File) => {
      setPendingFile(file);
      setConflict(null);
      uploadMutation.mutate(file);
    },
    [uploadMutation],
  );

  const overwrite = useCallback(
    (documentId: string) => {
      if (!pendingFile) return;
      reingestMutation.mutate({ documentId, file: pendingFile });
    },
    [pendingFile, reingestMutation],
  );

  const dismiss = useCallback(() => {
    setConflict(null);
    setPendingFile(null);
    uploadMutation.reset();
  }, [uploadMutation]);

  return {
    mutate,
    conflict,
    pendingFile,
    overwrite,
    dismiss,
    isPending: uploadMutation.isPending || reingestMutation.isPending,
    isError: uploadMutation.isError || reingestMutation.isError,
    error: uploadMutation.error || reingestMutation.error,
  };
}
