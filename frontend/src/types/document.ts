export const DOCUMENT_STATUS = {
  PROCESSING: "processing",
  COMPLETED: "completed",
  FAILED: "failed",
} as const;

export type DocumentStatus =
  (typeof DOCUMENT_STATUS)[keyof typeof DOCUMENT_STATUS];

export interface Document {
  id: string;
  filename: string;
  status: DocumentStatus;
  created_at: string;
  summary?: string | null;
}

export interface DocumentListResponse {
  documents: Document[];
}

export interface UploadResponse {
  document_id: string;
  status: DocumentStatus;
}

export interface ConflictDetail {
  existing_document_id: string;
  filename: string;
  processing: boolean;
}
