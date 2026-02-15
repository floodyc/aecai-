"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import UploadZone from "@/components/UploadZone";
import PageSelector from "@/components/PageSelector";
import { previewPdf, startTakeoff, PreviewResponse } from "@/lib/api";

const planLabels: Record<string, string> = {
  trial: "Free Trial",
  standard: "Standard",
  professional: "Professional",
  enterprise: "Enterprise",
};

type Step = "upload" | "select-pages";

export default function DashboardPage() {
  const router = useRouter();
  const { user, isLoading } = useAuth();
  const [step, setStep] = useState<Step>("upload");
  const [isUploading, setIsUploading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);

  // Redirect if not logged in
  if (!isLoading && !user) {
    router.replace("/");
    return null;
  }

  if (isLoading || !user) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-6 h-6 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const handleUpload = async (file: File) => {
    setIsUploading(true);
    setError(null);

    try {
      const previewData = await previewPdf(file);
      setPreview(previewData);
      setStep("select-pages");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setIsUploading(false);
    }
  };

  const handleProcess = async (
    selectedPages: number[] | null,
    legendPage: number | null
  ) => {
    if (!preview) return;
    setIsProcessing(true);
    setError(null);

    try {
      const job = await startTakeoff(
        preview.preview_id,
        selectedPages ?? undefined,
        legendPage ?? undefined
      );
      router.push(`/takeoff/${job.id}`);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to start processing"
      );
      setIsProcessing(false);
    }
  };

  const handleBack = () => {
    setStep("upload");
    setPreview(null);
    setError(null);
  };

  const atLimit =
    user.plan === "trial" && user.trial_uploads_remaining <= 0;

  return (
    <div
      className={`mx-auto px-6 py-12 ${
        step === "select-pages" ? "max-w-4xl" : "max-w-2xl"
      }`}
    >
      {/* Account Status Bar */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-8">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-0.5">
              Current Plan
            </p>
            <p className="font-semibold text-gray-100">
              {planLabels[user.plan] || user.plan}
            </p>
          </div>
          <a
            href="/billing"
            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg text-xs font-medium text-gray-300 transition-colors"
          >
            {user.plan === "trial" ? "Upgrade Plan" : "Manage Billing"}
          </a>
        </div>

        {/* Usage Bar */}
        <div>
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span className="text-gray-400">
              {user.plan === "trial" ? "Trial Uploads" : "Pages This Month"}
            </span>
            <span className="text-gray-300 tabular-nums">
              {user.pages_used} / {user.pages_limit}
            </span>
          </div>
          <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                user.pages_used / user.pages_limit > 0.9
                  ? "bg-amber-500"
                  : "bg-primary-500"
              }`}
              style={{
                width: `${Math.min(
                  (user.pages_used / user.pages_limit) * 100,
                  100
                )}%`,
              }}
            />
          </div>
          {user.plan !== "trial" && user.pages_used >= user.pages_limit && (
            <p className="text-xs text-amber-400 mt-1.5">
              Plan limit reached. Additional pages billed at $25/page.
            </p>
          )}
        </div>
      </div>

      {atLimit ? (
        /* Trial exhausted */
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center">
          <div className="mx-auto w-14 h-14 rounded-full bg-amber-950/50 flex items-center justify-center mb-4">
            <svg
              className="w-7 h-7 text-amber-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
              />
            </svg>
          </div>
          <h3 className="font-semibold text-gray-100 mb-2">
            Free Trial Complete
          </h3>
          <p className="text-sm text-gray-400 mb-6 max-w-sm mx-auto">
            You&apos;ve used all 3 free uploads. Upgrade to a paid plan to
            continue processing drawings.
          </p>
          <a
            href="/billing"
            className="inline-block px-6 py-2.5 bg-primary-600 hover:bg-primary-500 rounded-lg text-sm font-semibold transition-colors"
          >
            View Plans & Upgrade
          </a>
        </div>
      ) : step === "upload" ? (
        /* Step 1: Upload */
        <>
          <div className="text-center mb-8">
            <h1 className="text-2xl font-bold tracking-tight text-gray-50 mb-2">
              Lighting Fixture Takeoff
            </h1>
            <p className="text-gray-400 text-sm">
              Upload an electrical drawing PDF to automatically detect and
              count lighting fixtures.
            </p>
          </div>

          <UploadZone onUpload={handleUpload} isUploading={isUploading} />

          {error && (
            <div className="mt-4 p-3 bg-red-950/50 border border-red-900 rounded-lg text-sm text-red-300">
              {error}
            </div>
          )}

          {user.plan === "trial" && (
            <p className="mt-4 text-center text-xs text-gray-500">
              {user.trial_uploads_remaining} free upload
              {user.trial_uploads_remaining !== 1 ? "s" : ""} remaining
            </p>
          )}

          {/* Stats */}
          <div className="mt-14 grid grid-cols-3 gap-6 text-center">
            <div>
              <div className="text-2xl font-bold text-primary-400 mb-1">
                300
              </div>
              <div className="text-xs text-gray-500">DPI Rendering</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-primary-400 mb-1">
                CV
              </div>
              <div className="text-xs text-gray-500">Oval Detection</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-primary-400 mb-1">
                OCR
              </div>
              <div className="text-xs text-gray-500">Fuzzy Correction</div>
            </div>
          </div>
        </>
      ) : (
        /* Step 2: Select Pages */
        <>
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-gray-50 mb-1">
                Select Pages to Process
              </h1>
              <p className="text-gray-400 text-sm">
                {preview!.total_pages} pages found. Choose which pages to
                include in your takeoff.
              </p>
            </div>
            <button
              onClick={handleBack}
              className="px-4 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg text-xs font-medium text-gray-300 transition-colors"
            >
              Upload Different PDF
            </button>
          </div>

          <PageSelector
            pages={preview!.pages}
            onProcess={handleProcess}
            isProcessing={isProcessing}
          />

          {error && (
            <div className="mt-4 p-3 bg-red-950/50 border border-red-900 rounded-lg text-sm text-red-300">
              {error}
            </div>
          )}
        </>
      )}
    </div>
  );
}
