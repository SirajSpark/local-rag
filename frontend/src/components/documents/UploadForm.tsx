import { useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { Upload } from "lucide-react";
import { useUpload } from "../../hooks/useUpload";
import { Button } from "../ui/Button";
import { cn } from "../../lib/utils";

export function UploadForm() {
  const upload = useUpload();

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      const file = acceptedFiles[0];
      if (file) upload.mutate(file);
    },
    [upload],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        [".docx"],
      "application/vnd.openxmlformats-officedocument.presentationml.presentation":
        [".pptx"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        [".xlsx"],
      "text/plain": [".txt"],
      "image/png": [".png"],
      "image/jpeg": [".jpg", ".jpeg"],
    },
    maxFiles: 1,
    maxSize: 100 * 1024 * 1024,
    disabled: upload.isPending,
  });

  return (
    <>
      <div
        {...getRootProps()}
        className={cn(
          "cursor-pointer rounded-lg border-2 border-dashed p-6 text-center transition-colors",
          isDragActive
            ? "border-teal-500/50 bg-teal-500/5"
            : "border-zinc-700 hover:border-zinc-600",
          upload.isPending && "pointer-events-none opacity-50",
        )}
      >
        <input {...getInputProps()} />
        <Upload className={cn("mx-auto mb-2 h-6 w-6", isDragActive ? "text-teal-400" : "text-zinc-500")} />
        {upload.isPending ? (
          <p className="text-sm text-zinc-400">Uploading...</p>
        ) : isDragActive ? (
          <p className="text-sm text-teal-400">Drop your file here</p>
        ) : (
          <>
            <p className="text-sm font-medium text-zinc-300">
              Drop a document here
            </p>
            <p className="mt-1 text-xs text-zinc-500">
              PDF, DOCX, PPTX, XLSX, TXT, or images
            </p>
          </>
        )}
        {upload.isError && !upload.conflict && (
          <p className="mt-2 text-xs text-red-400">{upload.error?.message}</p>
        )}
      </div>

      {upload.conflict && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="mx-4 w-full max-w-sm rounded-lg bg-zinc-900 border border-zinc-800 p-6 shadow-xl">
            <h3 className="text-lg font-semibold text-zinc-100">
              File already exists
            </h3>
            <p className="mt-2 text-sm text-zinc-400">
              {upload.conflict.processing
                ? `The file "${upload.conflict.filename}" is currently being processed. Please wait.`
                : `A file named "${upload.conflict.filename}" already exists. Do you want to overwrite it?`}
            </p>
            <div className="mt-4 flex justify-end gap-2">
              {upload.conflict.processing ? (
                <Button variant="secondary" onClick={upload.dismiss}>
                  Dismiss
                </Button>
              ) : (
                <>
                  <Button variant="secondary" onClick={upload.dismiss}>
                    Cancel
                  </Button>
                  <Button
                    variant="danger"
                    onClick={() => upload.overwrite(upload.conflict!.existing_document_id)}
                    loading={upload.isPending}
                  >
                    Overwrite
                  </Button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
