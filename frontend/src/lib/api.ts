const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface JobResponse {
  id: string;
  status: "pending" | "processing" | "completed" | "failed";
  created_at: string;
  current_page: number;
  total_pages: number;
  current_floor: string;
  results: TakeoffResults | null;
  error: string | null;
}

export interface TakeoffResults {
  floors: Record<string, Record<string, number>>;
  building_totals: Record<string, number>;
  summary: {
    total_fixtures: number;
    num_floors: number;
    luminaire_types: string[];
  };
  txt_report: string;
}

export async function uploadPdf(file: File): Promise<JobResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_URL}/api/takeoff`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail || "Upload failed");
  }

  return res.json();
}

export async function getJobStatus(jobId: string): Promise<JobResponse> {
  const res = await fetch(`${API_URL}/api/takeoff/${jobId}`);
  if (!res.ok) {
    throw new Error("Failed to fetch job status");
  }
  return res.json();
}

export function getReportUrl(jobId: string): string {
  return `${API_URL}/api/takeoff/${jobId}/report`;
}
