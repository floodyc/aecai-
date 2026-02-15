"use client";

import { useState, useRef } from "react";
import { PagePreview } from "@/lib/api";

interface PageSelectorProps {
  pages: PagePreview[];
  onProcess: (
    selectedPages: number[] | null,
    legendPage: number | null,
    legendImage: File | null,
    fixturePrefix: string | null
  ) => void;
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

  // Legend page the user has designated (auto-detected initially)
  const [legendPageNum, setLegendPageNum] = useState<number | null>(() => {
    const detected = pages.find((p) => p.is_legend);
    return detected ? detected.page_number : null;
  });

  // Optional user-uploaded legend image (snapshot of the lighting table)
  const [legendImage, setLegendImage] = useState<File | null>(null);
  const legendInputRef = useRef<HTMLInputElement>(null);

  // Fixture code prefix (e.g. "LT") — user tells us what codes start with
  const [fixturePrefix, setFixturePrefix] = useState("");

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

  const toggleLegend = (pageNum: number) => {
    setLegendPageNum((prev) => (prev === pageNum ? null : pageNum));
    // If setting a page as legend, deselect it from processing
    if (legendPageNum !== pageNum) {
      setSelected((prev) => {
        const next = new Set(prev);
        next.delete(pageNum);
        return next;
      });
    }
    // Clear uploaded image when selecting a PDF page as legend
    setLegendImage(null);
  };

  const handleLegendImageChange = (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      alert("Please upload an image file (PNG, JPG, etc.).");
      return;
    }
    setLegendImage(file);
    // Clear PDF legend page selection — uploaded image takes priority
    setLegendPageNum(null);
  };

  const removeLegendImage = () => {
    setLegendImage(null);
    if (legendInputRef.current) legendInputRef.current.value = "";
  };

  const selectAll = () => {
    const s = new Set(pages.map((p) => p.page_number));
    // Don't select the legend page for processing
    if (legendPageNum) s.delete(legendPageNum);
    setSelected(s);
  };

  const selectNone = () => {
    setSelected(new Set());
  };

  const handleProcess = () => {
    if (selected.size === 0) return;
    const selectedPages =
      selected.size === pages.length
        ? null
        : Array.from(selected).sort((a, b) => a - b);
    const prefix = fixturePrefix.trim() || null;
    onProcess(selectedPages, legendPageNum, legendImage, prefix);
  };

  const hasLegend = legendPageNum !== null || legendImage !== null;

  return (
    <div className="space-y-6">
      {/* Legend Selection Banner */}
      <div
        className={`rounded-xl p-4 flex items-start gap-3 ${
          hasLegend
            ? "bg-amber-950/30 border border-amber-900/50"
            : "bg-blue-950/30 border border-blue-900/50"
        }`}
      >
        <svg
          className={`w-5 h-5 mt-0.5 shrink-0 ${
            hasLegend ? "text-amber-400" : "text-blue-400"
          }`}
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
        <div className="flex-1">
          {legendImage ? (
            <>
              <p className="text-sm font-medium text-amber-300">
                Legend Image Uploaded
              </p>
              <div className="flex items-center gap-2 mt-1">
                <p className="text-xs text-amber-500">
                  {legendImage.name} — fixture codes will be extracted from
                  this image.
                </p>
                <button
                  onClick={removeLegendImage}
                  className="text-xs text-red-400 hover:text-red-300 underline shrink-0"
                >
                  Remove
                </button>
              </div>
            </>
          ) : legendPageNum ? (
            <>
              <p className="text-sm font-medium text-amber-300">
                Symbol Legend — Page {legendPageNum}
              </p>
              <p className="text-xs text-amber-500 mt-0.5">
                Fixture codes will be extracted from this page. Right-click any
                thumbnail to change, or upload a snapshot below.
              </p>
            </>
          ) : (
            <>
              <p className="text-sm font-medium text-blue-300">
                No Symbol Legend Selected
              </p>
              <p className="text-xs text-blue-500 mt-0.5">
                Right-click a page thumbnail to designate it as the symbol
                legend, or upload a snapshot of the lighting fixture table.
              </p>
            </>
          )}

          {/* Upload legend image button */}
          {!legendImage && (
            <div className="mt-2.5">
              <input
                ref={legendInputRef}
                type="file"
                accept="image/*"
                onChange={handleLegendImageChange}
                className="hidden"
              />
              <button
                onClick={() => legendInputRef.current?.click()}
                className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg text-xs font-medium text-gray-300 transition-colors inline-flex items-center gap-1.5"
              >
                <svg
                  className="w-3.5 h-3.5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                  />
                </svg>
                Upload Legend Snapshot
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Fixture Code Prefix */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <label
          htmlFor="fixture-prefix"
          className="block text-sm font-medium text-gray-200 mb-1"
        >
          Fixture Code Prefix
        </label>
        <p className="text-xs text-gray-500 mb-3">
          Enter the prefix that fixture codes start with (e.g.{" "}
          <span className="font-mono text-gray-400">LT</span> for LT04, LT12A).
          Only ovals with matching text will be counted.
        </p>
        <input
          id="fixture-prefix"
          type="text"
          value={fixturePrefix}
          onChange={(e) => setFixturePrefix(e.target.value.toUpperCase())}
          placeholder="e.g. LT"
          className="w-40 px-3 py-2 bg-gray-950 border border-gray-700 rounded-lg text-sm text-gray-100 font-mono placeholder:text-gray-600 focus:outline-none focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
        />
      </div>

      {/* Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={selectAll}
            className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg text-xs font-medium text-gray-300 transition-colors"
          >
            Select All
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
          const isLegend = legendPageNum === page.page_number;
          return (
            <div key={page.page_number} className="relative">
              <button
                onClick={() => {
                  if (!isLegend) togglePage(page.page_number);
                }}
                onContextMenu={(e) => {
                  e.preventDefault();
                  toggleLegend(page.page_number);
                }}
                className={`relative group rounded-xl overflow-hidden border-2 transition-all w-full ${
                  isLegend
                    ? "border-amber-500 ring-1 ring-amber-500/20"
                    : isSelected
                    ? "border-primary-500 ring-1 ring-primary-500/20"
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
                  {/* Overlay when not selected and not legend */}
                  {!isSelected && !isLegend && (
                    <div className="absolute inset-0 bg-gray-950/60" />
                  )}
                  {/* Legend overlay */}
                  {isLegend && (
                    <div className="absolute inset-0 bg-amber-950/20" />
                  )}
                </div>

                {/* Footer */}
                <div
                  className={`px-3 py-2 flex items-center justify-between text-xs ${
                    isSelected || isLegend ? "bg-gray-900" : "bg-gray-900/80"
                  }`}
                >
                  <span
                    className={`font-medium ${
                      isSelected || isLegend ? "text-gray-200" : "text-gray-500"
                    }`}
                  >
                    Page {page.page_number}
                  </span>
                  {isLegend && (
                    <span className="px-1.5 py-0.5 bg-amber-950 text-amber-400 rounded text-[10px] font-semibold">
                      LEGEND
                    </span>
                  )}
                </div>

                {/* Checkbox indicator */}
                {!isLegend && (
                  <div
                    className={`absolute top-2 right-2 w-5 h-5 rounded-md flex items-center justify-center transition-colors ${
                      isSelected
                        ? "bg-primary-500"
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
                )}
                {/* Legend badge */}
                {isLegend && (
                  <div className="absolute top-2 right-2 w-5 h-5 rounded-md flex items-center justify-center bg-amber-500">
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
                        d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
                      />
                    </svg>
                  </div>
                )}
              </button>

              {/* Set as Legend button (shown on hover via group) */}
              <button
                onClick={() => toggleLegend(page.page_number)}
                className={`absolute bottom-12 left-1/2 -translate-x-1/2 px-2 py-1 rounded text-[10px] font-medium whitespace-nowrap opacity-0 hover:opacity-100 transition-opacity ${
                  isLegend
                    ? "bg-amber-600 text-white"
                    : "bg-gray-700 text-gray-200"
                }`}
                title={
                  isLegend
                    ? "Remove as legend page"
                    : "Set as symbol legend page"
                }
              >
                {isLegend ? "Remove Legend" : "Set as Legend"}
              </button>
            </div>
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
