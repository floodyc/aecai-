"use client";

interface ErrorViewProps {
  message: string;
  onRetry: () => void;
}

export default function ErrorView({ message, onRetry }: ErrorViewProps) {
  return (
    <div className="max-w-lg mx-auto text-center space-y-6">
      <div className="mx-auto w-16 h-16 rounded-full bg-red-950 flex items-center justify-center">
        <svg
          className="w-8 h-8 text-red-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
          />
        </svg>
      </div>
      <div>
        <h2 className="text-xl font-semibold text-gray-100">
          Processing Failed
        </h2>
        <p className="text-sm text-gray-400 mt-2">{message}</p>
      </div>
      <button
        onClick={onRetry}
        className="px-6 py-2.5 bg-primary-600 hover:bg-primary-500 text-white rounded-lg text-sm font-medium transition-colors"
      >
        Try Again
      </button>
    </div>
  );
}
