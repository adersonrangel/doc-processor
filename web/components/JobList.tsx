"use client";

import { useEffect, useState } from "react";
import { listJobs, type JobSummary } from "@/lib/api";

export default function JobList({ refreshKey = 0 }: { refreshKey?: number }) {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [manualRefreshKey, setManualRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      setLoading(true);
      try {
        const next = await listJobs();
        if (cancelled) {
          return;
        }
        setJobs(next);
        setError(null);
      } catch (err) {
        if (cancelled) {
          return;
        }
        setError(err instanceof Error ? err.message : "No se pudo cargar la lista.");
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void run();

    return () => {
      cancelled = true;
    };
  }, [refreshKey, manualRefreshKey]);

  return (
    <>
      <div className="row" style={{ marginTop: 0, marginBottom: "0.75rem" }}>
        <button
          type="button"
          className="secondary"
          onClick={() => setManualRefreshKey((key) => key + 1)}
          disabled={loading}
        >
          {loading ? "Cargando…" : "Recargar"}
        </button>
        <span className="muted">{jobs.length} job(s)</span>
      </div>

      {error !== null && <p className="error-text">{error}</p>}

      {error === null && !loading && jobs.length === 0 && (
        <p className="muted">Todavía no hay documentos.</p>
      )}

      {jobs.length > 0 && (
        <table className="jobs">
          <thead>
            <tr>
              <th>Archivo</th>
              <th>Estado</th>
              <th>Creado</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.job_id}>
                <td>
                  {job.original_filename}
                  <br />
                  <code className="muted">{job.job_id}</code>
                </td>
                <td>
                  <span className={`badge ${job.status}`}>{job.status}</span>
                </td>
                <td>{formatDate(job.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}
