import { Badge } from "../ui/Badge";
import type { DocumentStatus } from "../../types";

const STATUS_MAP: Record<DocumentStatus, "processing" | "completed" | "failed"> = {
  processing: "processing",
  completed: "completed",
  failed: "failed",
};

interface StatusBadgeProps {
  status: DocumentStatus;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  return <Badge variant={STATUS_MAP[status]}>{status}</Badge>;
}
