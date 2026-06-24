import { useDocuments } from "../../hooks/useDocuments";
import { DocumentItem } from "./DocumentItem";
import { Spinner } from "../ui/Spinner";

export function DocumentList() {
  const { data, isLoading, isError, error } = useDocuments();

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <Spinner />
      </div>
    );
  }

  if (isError) {
    return (
      <p className="text-sm text-red-400">{error?.message ?? "Failed to load documents"}</p>
    );
  }

  if (!data || data.documents.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-zinc-500">
        No documents yet. Upload a file to get started.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {data.documents.map((doc) => (
        <DocumentItem key={doc.id} doc={doc} />
      ))}
    </div>
  );
}
