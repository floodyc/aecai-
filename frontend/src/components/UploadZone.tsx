"use client";

import { useCallback, useState, useRef } from "react";

interface UploadZoneProps {
  onUpload: (file: File) => void;
  isUploading: boolean;
}

export default function UploadZone({ onUpload, isUploading }: UploadZoneProps) {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((file: File) => {
    if (file.type !== "application/pdf") {
      alert("Please upload a PDF file.");
      return;
    }
    setSelectedFile(file);
  }, []);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragActive(false);

      if (e.dataTransfer.files?.[0]) {
        handleFile(e.dataTransfer.files[0]);
      }
    },
    [handleFile]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files?.[0]) {
        handleFile(e.target.files[0]);
      }
    },
    [handleFile]
  );

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="space-y-6">
      <div
        className={`
          relative border-2 border-dashed rounded-xl p-12 text-center
          transition-colors cursor-pointer
          ${
            dragActive
              ? "border-primary-400 bg-primary-950/30"
              : "border-gray-700 hover:border-gray-500 bg-gray-900/50"
          }
        `}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,application/pdf"
          onChange={handleChange}
          className="hidden"
        />

        <div className="space-y-4">
          <div className="mx-auto w-16 h-16 rounded-full bg-gray-800 flex items-center justify-center">
            <svg
              className="w-8 h-8 text-gray-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.338-2.32 3 3 0 013.803 3.637A4.5 4.5 0 0118 19.5H6.75z"
              />
            </svg>
          </div>
          <div>
            <p className="text-gray-300 font-medium">
              Drop your electrical drawing PDF here
            </p>
            <p className="text-gray-500 text-sm mt-1">
              or click to browse files
            </p>
          </div>
        </div>
      </div>

      {selectedFile && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-red-950 rounded-lg flex items-center justify-center">
              <span className="text-red-400 text-xs font-bold">PDF</span>
            </div>
            <div>
              <p className="text-sm font-medium text-gray-200">
                {selectedFile.name}
              </p>
              <p className="text-xs text-gray-500">
                {formatSize(selectedFile.size)}
              </p>
            </div>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onUpload(selectedFile);
            }}
            disabled={isUploading}
            className={`
              px-6 py-2.5 rounded-lg font-medium text-sm transition-colors
              ${
                isUploading
                  ? "bg-gray-700 text-gray-400 cursor-not-allowed"
                  : "bg-primary-600 hover:bg-primary-500 text-white"
              }
            `}
          >
            {isUploading ? "Uploading..." : "Start Takeoff"}
          </button>
        </div>
      )}
    </div>
  );
}
