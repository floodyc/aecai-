"use client";

import { JobResponse } from "@/lib/api";

interface ProgressViewProps {
  job: JobResponse;
}

export default function ProgressView({ job }: ProgressViewProps) {
  const progress =
    job.total_pages > 0
      ? Math.round((job.current_page / job.total_pages) * 100)
      : 0;

  return (
    <div className="max-w-lg mx-auto space-y-8">
      <div className="text-center space-y-2">
        <h2 className="text-xl font-semibold text-gray-100">
          Processing Your Drawing
        </h2>
        <p className="text-sm text-gray-400">
          Detecting and identifying lighting fixtures using computer vision
        </p>
      </div>

      <div className="space-y-3">
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">
            {job.current_floor || "Initializing..."}
          </span>
          <span className="text-gray-300 font-medium">{progress}%</span>
        </div>

        <div className="w-full bg-gray-800 rounded-full h-2.5 overflow-hidden">
          <div
            className="bg-primary-500 h-full rounded-full transition-all duration-500 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>

        {job.total_pages > 0 && (
          <p className="text-xs text-gray-500 text-center">
            Page {job.current_page} of {job.total_pages}
          </p>
        )}
      </div>

      <div className="flex justify-center">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <svg
            className="w-4 h-4 animate-spin text-primary-500"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          Processing takes ~70 seconds per page at 300 DPI
        </div>
      </div>
    </div>
  );
}
