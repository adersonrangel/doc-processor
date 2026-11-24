"use client";

import { useRef, useState, type ChangeEvent, type DragEvent, type FormEvent } from "react";
import { createJob } from "@/lib/api";

const ACCEPTABLE_EXTENSIONS = ["pdf", "xlsx", "docx", "txt"];
const ACCEPTED_FILES = ACCEPTABLE_EXTENSIONS.map((ext) => `.${ext}`).join(",");

export default function UploadForm({
  onJobCreated,
}: {
  onJobCreated: (jobId: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function selectFile(selected: File | undefined) {
    setError(null);
    setFile(selected ?? null);
  }

  function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    selectFile(event.target.files?.[0]);
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(true);
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    selectFile(event.dataTransfer.files?.[0]);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (file === null || submitting) {
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const created = await createJob(file);
      setFile(null);
      if (inputRef.current !== null) {
        inputRef.current.value = "";
      }
      onJobCreated(created.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo subir el archivo.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div
        className={dragging ? "dropzone dragging" : "dropzone"}
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {file === null ? (
          <>
            <p>Arrastra un archivo aquí o haz clic para elegirlo</p>
            <p className="muted">
              {ACCEPTABLE_EXTENSIONS.join(", ").toUpperCase()} · máx. 10 MB
            </p>
          </>
        ) : (
          <>
            <p className="file-name">{file.name}</p>
            <p className="muted">{formatSize(file.size)}</p>
          </>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_FILES}
        onChange={handleInputChange}
        hidden
      />

      <div className="row">
        <button type="submit" disabled={file === null || submitting}>
          {submitting ? "Subiendo…" : "Subir documento"}
        </button>
        {file !== null && !submitting && (
          <button
            type="button"
            className="secondary"
            onClick={() => selectFile(undefined)}
          >
            Quitar
          </button>
        )}
      </div>

      {error !== null && <p className="error-text">{error}</p>}
    </form>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
