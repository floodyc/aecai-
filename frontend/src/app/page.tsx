"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import UploadZone from "@/components/UploadZone";
import { uploadPdf } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = async (file: File) => {
    setIsUploading(true);
    setError(null);

    try {
      const job = await uploadPdf(file);
      router.push(`/takeoff/${job.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setIsUploading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto px-6 py-16">
      <div className="text-center mb-12">
        <h1 className="text-3xl font-bold tracking-tight text-gray-50 mb-3">
          Lighting Fixture Takeoff
        </h1>
        <p className="text-gray-400 max-w-md mx-auto">
          Upload an electrical drawing PDF to automatically detect and count
          lighting fixtures using computer vision and OCR.
        </p>
      </div>

      <UploadZone onUpload={handleUpload} isUploading={isUploading} />

      {error && (
        <div className="mt-4 p-3 bg-red-950/50 border border-red-900 rounded-lg text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="mt-16 grid grid-cols-3 gap-6 text-center">
        <div>
          <div className="text-2xl font-bold text-primary-400 mb-1">300</div>
          <div className="text-xs text-gray-500">DPI Rendering</div>
        </div>
        <div>
          <div className="text-2xl font-bold text-primary-400 mb-1">CV</div>
          <div className="text-xs text-gray-500">Oval Detection</div>
        </div>
        <div>
          <div className="text-2xl font-bold text-primary-400 mb-1">OCR</div>
          <div className="text-xs text-gray-500">Fuzzy Correction</div>
        </div>
      </div>
    </div>
  );
}
