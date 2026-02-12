"use client";

import { useParams, useRouter } from "next/navigation";
import useSWR from "swr";
import { getJobStatus, JobResponse } from "@/lib/api";
import ProgressView from "@/components/ProgressView";
import ResultsView from "@/components/ResultsView";
import ErrorView from "@/components/ErrorView";

const fetcher = (jobId: string) => getJobStatus(jobId);

export default function TakeoffPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = params.id as string;

  const { data: job, error } = useSWR<JobResponse>(
    jobId ? jobId : null,
    fetcher,
    {
      refreshInterval: (data) => {
        if (!data) return 2000;
        if (data.status === "completed" || data.status === "failed") return 0;
        return 2000;
      },
    }
  );

  if (error) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-16">
        <ErrorView
          message="Could not connect to the server."
          onRetry={() => router.push("/")}
        />
      </div>
    );
  }

  if (!job) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-16">
        <div className="flex justify-center">
          <div className="w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-16">
      {job.status === "failed" && (
        <ErrorView
          message={job.error || "An unknown error occurred."}
          onRetry={() => router.push("/")}
        />
      )}

      {(job.status === "pending" || job.status === "processing") && (
        <ProgressView job={job} />
      )}

      {job.status === "completed" && job.results && (
        <ResultsView jobId={jobId} results={job.results} />
      )}
    </div>
  );
}
