"use client";

import { useState } from "react";
import { PagePreview } from "@/lib/api";

interface PageSelectorProps {
  pages: PagePreview[];
  onProcess: (selectedPages: number[] | null) => void;
  isProcessing: boolean;
}

export default function PageSelector({
  pages,
  onProcess,
  isProcessing,
}: PageSelectorProps) {
  const [selected, setSelected] = useState<Set<number>>(() => {
    // Pre-select all non-legend pages
    const s = new Set<number>();
    for (const p of pages) {
      if (!p.is_legend) s.add(p.page_number);
    }
    return s;
  });

  const legendPage = pages.find((p) => p.is_legend);
  const allSelected = selected.size === pages.length;
  const nonLegendCount = pages.filter((p) => !p.is_legend).length;
  const selectedNonLegend = pages.filter(
    (p) => !p.is_legend && selected.has(p.page_number)
  ).length;

  const togglePage = (pageNum: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(pageNum)) {
        next.delete(pageNum);
      } else {
        next.add(pageNum);
      }
      return next;
    });
  };

  const selectAll = () => {
    setSelected(new Set(pages.map((p) => p.page_number)));
  };

  const selectNone = () => {
    setSelected(new Set());
  };

  const selectNonLegend = () => {
    setSelected(
      new Set(pages.filter((p) => !p.is_legend).map((p) => p.page_number))
    );
  };

  const handleProcess = () => {
    if (selected.size === 0) return;
    // null means all pages
    if (selected.size === pages.length) {
      onProcess(null);
    } else {
      onProcess(Array.from(selected).sort((a, b) => a - b));
    }
  };

  return (
    <div className="space-y-6">
      {/* Legend Detection Banner */}
      {legendPage && (
        <div className="bg-amber-950/30 border border-amber-900/50 rounded-xl p-4 flex items-start gap-3">
          <svg
            className="w-5 h-5 text-amber-400 mt-0.5 shrink-0"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <div>
            <p className="text-sm font-medium text-amber-300">
              Symbol Legend Detected — Page {legendPage.page_number}
            </p>
            <p className="text-xs text-amber-500 mt-0.5">
              This page contains the fixture symbol legend. It has been
              excluded from processing by default.
            </p>
          </div>
        </div>
      )}

      {/* Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={selectAll}
            className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg text-xs font-medium text-gray-300 transition-colors"
          >
            All Pages
          </button>
          <button
            onClick={selectNonLegend}
            className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg text-xs font-medium text-gray-300 transition-colors"
          >
            All Except Legend
          </button>
          <button
            onClick={selectNone}
            className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg text-xs font-medium text-gray-300 transition-colors"
          >
            Clear
          </button>
        </div>
        <p className="text-xs text-gray-500 tabular-nums">
          {selected.size} of {pages.length} pages selected
        </p>
      </div>

      {/* Page Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
        {pages.map((page) => {
          const isSelected = selected.has(page.page_number);
          return (
            <button
              key={page.page_number}
              onClick={() => togglePage(page.page_number)}
              className={`relative group rounded-xl overflow-hidden border-2 transition-all ${
                isSelected
                  ? page.is_legend
                    ? "border-amber-500 ring-1 ring-amber-500/20"
                    : "border-primary-500 ring-1 ring-primary-500/20"
                  : "border-gray-800 hover:border-gray-600"
              }`}
            >
              {/* Thumbnail */}
              <div className="aspect-[8.5/11] bg-gray-900 relative">
                <img
                  src={`data:image/jpeg;base64,${page.thumbnail}`}
                  alt={`Page ${page.page_number}`}
                  className="w-full h-full object-cover"
                />
                {/* Overlay when not selected */}
                {!isSelected && (
                  <div className="absolute inset-0 bg-gray-950/60" />
                )}
              </div>

              {/* Footer */}
              <div
                className={`px-3 py-2 flex items-center justify-between text-xs ${
                  isSelected ? "bg-gray-900" : "bg-gray-900/80"
                }`}
              >
                <span
                  className={`font-medium ${
                    isSelected ? "text-gray-200" : "text-gray-500"
                  }`}
                >
                  Page {page.page_number}
                </span>
                {page.is_legend && (
                  <span className="px-1.5 py-0.5 bg-amber-950 text-amber-400 rounded text-[10px] font-semibold">
                    LEGEND
                  </span>
                )}
              </div>

              {/* Checkbox indicator */}
              <div
                className={`absolute top-2 right-2 w-5 h-5 rounded-md flex items-center justify-center transition-colors ${
                  isSelected
                    ? page.is_legend
                      ? "bg-amber-500"
                      : "bg-primary-500"
                    : "bg-gray-800/80 border border-gray-600"
                }`}
              >
                {isSelected && (
                  <svg
                    className="w-3 h-3 text-white"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={3}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                )}
              </div>
            </button>
          );
        })}
      </div>

      {/* Process Button */}
      <div className="flex items-center justify-between pt-2">
        <p className="text-xs text-gray-500">
          {selected.size > 0
            ? `~${Math.round((selected.size * 70) / 60)} min estimated processing time`
            : "Select at least one page to process"}
        </p>
        <button
          onClick={handleProcess}
          disabled={selected.size === 0 || isProcessing}
          className="px-6 py-2.5 bg-primary-600 hover:bg-primary-500 disabled:bg-gray-800 disabled:text-gray-500 rounded-lg text-sm font-semibold transition-colors"
        >
          {isProcessing
            ? "Starting..."
            : selected.size === pages.length
            ? "Process All Pages"
            : `Process ${selected.size} Page${selected.size !== 1 ? "s" : ""}`}
        </button>
      </div>
    </div>
  );
}
