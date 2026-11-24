"use client";

import { useCallback, useState } from "react";
import JobList from "@/components/JobList";
import JobStatus from "@/components/JobStatus";
import UploadForm from "@/components/UploadForm";

export default function HomePage() {
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [listRefreshKey, setListRefreshKey] = useState(0);

  const handleJobCreated = useCallback((jobId: string) => {
    setActiveJobId(jobId);
  }, []);

  const handleJobSettled = useCallback(() => {
    // A job reached `ready` or `error`: refresh the list so it reflects it.
    setListRefreshKey((key) => key + 1);
  }, []);

  return (
    <>
      <section className="card">
        <h2>Subir documento</h2>
        <UploadForm onJobCreated={handleJobCreated} />
      </section>

      {activeJobId !== null && (
        <section className="card">
          <h2>Estado del job</h2>
          <JobStatus jobId={activeJobId} onSettled={handleJobSettled} />
        </section>
      )}

      <section className="card">
        <JobList refreshKey={listRefreshKey} />
      </section>
    </>
  );
}
