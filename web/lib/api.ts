/**
 * Typed fetch helpers for the doc-processor API.
 *
 * Contract (see odd/tasks/doc-processor-prototype.md):
 *   POST /api/jobs        -> 202 { job_id, status }
 *   GET  /api/jobs/{id}   -> 200 { job_id, status, original_filename, content_type,
 *                                 size_bytes, result, error, created_at, updated_at }
 *   GET  /api/jobs        -> 200 { jobs: [ { job_id, status, original_filename, created_at } ] }
 */

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

export type JobStatus = "pending" | "processing" | "ready" | "error";

export interface Job {
  job_id: string;
  status: JobStatus;
  original_filename: string;
  content_type: string | null;
  size_bytes: number | null;
  result: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobSummary {
  job_id: string;
  status: JobStatus;
  original_filename: string;
  created_at: string;
}

export interface CreateJobResponse {
  job_id: string;
  status: JobStatus;
}

export interface JobListResponse {
  jobs: JobSummary[];
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Statuses that end the polling loop (S8). */
const TERMINAL_STATUSES: readonly JobStatus[] = ["ready", "error"];

export function isTerminalStatus(status: JobStatus): boolean {
  return TERMINAL_STATUSES.includes(status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const body: unknown = await response.json();
      if (
        body !== null &&
        typeof body === "object" &&
        "detail" in body &&
        typeof (body as { detail?: unknown }).detail === "string"
      ) {
        detail = (body as { detail: string }).detail;
      }
    } catch {
      // Non-JSON error body: keep the generic message.
    }
    throw new ApiError(response.status, detail);
  }

  return (await response.json()) as T;
}

/** Uploads one file and creates a job (API answers immediately with the job id). */
export async function createJob(file: File): Promise<CreateJobResponse> {
  const formData = new FormData();
  formData.append("file", file);

  return request<CreateJobResponse>("/api/jobs", {
    method: "POST",
    body: formData,
  });
}

/** Reads the current state of one job (polled by JobStatus). */
export async function getJob(jobId: string): Promise<Job> {
  return request<Job>(`/api/jobs/${encodeURIComponent(jobId)}`);
}

/** Lists the most recent jobs, newest first. */
export async function listJobs(): Promise<JobSummary[]> {
  const body = await request<JobListResponse>("/api/jobs");
  return body.jobs;
}
