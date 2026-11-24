"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, getJob, isTerminalStatus, type Job } from "@/lib/api";

/** S8: the browser learns the result by polling every 2-3 s. */
export const POLL_INTERVAL_MS = 2500;

function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

function formatSize(bytes: number | null): string {
  if (bytes === null) {
    return "—";
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function JobStatus({
  jobId,
  onSettled,
}: {
  jobId: string;
  onSettled?: (job: Job) => void;
}) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [polling, setPolling] = useState(true);

  // Keep the latest callback without restarting the polling effect.
  const onSettledRef = useRef(onSettled);
  useEffect(() => {
    onSettledRef.current = onSettled;
  }, [onSettled]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    setJob(null);
    setError(null);
    setPolling(true);

    async function poll() {
      try {
        const current = await getJob(jobId);
        if (cancelled) {
          return;
        }
        setJob(current);
        setError(null);
        if (isTerminalStatus(current.status)) {
          setPolling(false);
          onSettledRef.current?.(current);
          return;
        }
      } catch (err) {
        if (cancelled) {
          return;
        }
        setError(err instanceof Error ? err.message : "Error consultando el estado.");
        if (err instanceof ApiError && err.status === 404) {
          setPolling(false);
          return;
        }
      }

      if (cancelled) {
        return;
      }
      timer = setTimeout(() => {
        void poll();
      }, POLL_INTERVAL_MS);
    }

    void poll();

    return () => {
      cancelled = true;
      if (timer !== null) {
        clearTimeout(timer);
      }
    };
  }, [jobId]);

  return (
    <div>
      <div className="row" style={{ marginTop: 0 }}>
        <span className={`badge ${job?.status ?? "pending"}`}>
          {job?.status ?? "pending"}
        </span>
        <code>{jobId}</code>
        {polling && <span className="muted">actualizando cada 2.5 s…</span>}
      </div>

      {job !== null && (
        <>
          <dl className="meta">
            <dt>Archivo</dt>
            <dd>{job.original_filename}</dd>
            <dt>Tipo</dt>
            <dd>{job.content_type ?? "—"}</dd>
            <dt>Tamaño</dt>
            <dd>{formatSize(job.size_bytes)}</dd>
            <dt>Creado</dt>
            <dd>{formatDate(job.created_at)}</dd>
            <dt>Actualizado</dt>
            <dd>{formatDate(job.updated_at)}</dd>
          </dl>

          {job.status === "ready" && (
            <div className="result-box">
              <strong>Resultado:</strong> {job.result ?? "—"}
            </div>
          )}

          {job.status === "error" && (
            <p className="error-text">{job.error ?? "El job terminó con error."}</p>
          )}
        </>
      )}

      {error !== null && <p className="error-text">{error}</p>}
    </div>
  );
}
