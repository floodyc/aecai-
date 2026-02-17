"use client";

import { useState, useRef, useEffect, useCallback } from "react";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Exemplar {
  label: string;
  page: number;
  x: number;
  y: number;
  w: number;
  h: number;
  source_dpi: number;
}

interface ExemplarSelectorProps {
  previewId: string;
  pageNumber: number;
  existingExemplars: Exemplar[];
  onSave: (exemplars: Exemplar[]) => void;
  onClose: () => void;
}

/**
 * Full-screen modal for drawing bounding boxes on a high-res page image.
 * Users click-and-drag to select fixture symbols, then type a label.
 */
export default function ExemplarSelector({
  previewId,
  pageNumber,
  existingExemplars,
  onSave,
  onClose,
}: ExemplarSelectorProps) {
  const SOURCE_DPI = 150;

  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Exemplars for THIS page only
  const [exemplars, setExemplars] = useState<Exemplar[]>(
    existingExemplars.filter((e) => e.page === pageNumber)
  );

  // Drawing state
  const [isDrawing, setIsDrawing] = useState(false);
  const [drawStart, setDrawStart] = useState<{ x: number; y: number } | null>(null);
  const [drawEnd, setDrawEnd] = useState<{ x: number; y: number } | null>(null);

  // Label input for newly drawn box
  const [pendingBox, setPendingBox] = useState<{
    x: number; y: number; w: number; h: number;
  } | null>(null);
  const [labelInput, setLabelInput] = useState("");
  const labelRef = useRef<HTMLInputElement>(null);

  // Image natural dimensions (for coordinate mapping)
  const [imgSize, setImgSize] = useState<{ w: number; h: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);

  // Fetch page image
  useEffect(() => {
    const url = `${API_URL}/api/takeoff/preview/${previewId}/page/${pageNumber}?dpi=${SOURCE_DPI}`;
    setLoading(true);
    setError(null);
    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load page image");
        return res.blob();
      })
      .then((blob) => {
        setImageUrl(URL.createObjectURL(blob));
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [previewId, pageNumber]);

  // Clean up blob URL
  useEffect(() => {
    return () => {
      if (imageUrl) URL.revokeObjectURL(imageUrl);
    };
  }, [imageUrl]);

  const handleImageLoad = () => {
    if (imgRef.current) {
      setImgSize({
        w: imgRef.current.naturalWidth,
        h: imgRef.current.naturalHeight,
      });
    }
  };

  // Convert mouse event to image-pixel coordinates
  const toImageCoords = useCallback(
    (e: React.MouseEvent) => {
      if (!imgRef.current || !imgSize) return null;
      const rect = imgRef.current.getBoundingClientRect();
      const scaleX = imgSize.w / rect.width;
      const scaleY = imgSize.h / rect.height;
      return {
        x: (e.clientX - rect.left) * scaleX,
        y: (e.clientY - rect.top) * scaleY,
      };
    },
    [imgSize]
  );

  const handleMouseDown = (e: React.MouseEvent) => {
    if (pendingBox) return; // label dialog open
    const pt = toImageCoords(e);
    if (!pt) return;
    setIsDrawing(true);
    setDrawStart(pt);
    setDrawEnd(pt);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDrawing) return;
    const pt = toImageCoords(e);
    if (pt) setDrawEnd(pt);
  };

  const handleMouseUp = () => {
    if (!isDrawing || !drawStart || !drawEnd) return;
    setIsDrawing(false);

    const x = Math.min(drawStart.x, drawEnd.x);
    const y = Math.min(drawStart.y, drawEnd.y);
    const w = Math.abs(drawEnd.x - drawStart.x);
    const h = Math.abs(drawEnd.y - drawStart.y);

    // Ignore tiny accidental clicks (< 10px in image space)
    if (w < 10 || h < 10) {
      setDrawStart(null);
      setDrawEnd(null);
      return;
    }

    setPendingBox({ x, y, w, h });
    setLabelInput("");
    // Focus label input after render
    setTimeout(() => labelRef.current?.focus(), 50);
  };

  const confirmLabel = () => {
    const label = labelInput.trim().toUpperCase();
    if (!label || !pendingBox) return;

    const newExemplar: Exemplar = {
      label,
      page: pageNumber,
      ...pendingBox,
      source_dpi: SOURCE_DPI,
    };
    setExemplars((prev) => [...prev, newExemplar]);
    setPendingBox(null);
    setDrawStart(null);
    setDrawEnd(null);
  };

  const cancelLabel = () => {
    setPendingBox(null);
    setDrawStart(null);
    setDrawEnd(null);
  };

  const removeExemplar = (index: number) => {
    setExemplars((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSave = () => {
    // Merge: keep exemplars from other pages, replace this page's
    const otherPages = existingExemplars.filter((e) => e.page !== pageNumber);
    onSave([...otherPages, ...exemplars]);
  };

  // Convert image coords to display coords for overlays
  const toDisplayRect = (box: { x: number; y: number; w: number; h: number }) => {
    if (!imgRef.current || !imgSize) return { left: 0, top: 0, width: 0, height: 0 };
    const rect = imgRef.current.getBoundingClientRect();
    const container = containerRef.current?.getBoundingClientRect();
    const offsetX = container ? rect.left - container.left : 0;
    const offsetY = container ? rect.top - container.top : 0;
    const scaleX = rect.width / imgSize.w;
    const scaleY = rect.height / imgSize.h;
    return {
      left: box.x * scaleX + offsetX,
      top: box.y * scaleY + offsetY,
      width: box.w * scaleX,
      height: box.h * scaleY,
    };
  };

  // Current drag rectangle
  const dragRect =
    isDrawing && drawStart && drawEnd
      ? {
          x: Math.min(drawStart.x, drawEnd.x),
          y: Math.min(drawStart.y, drawEnd.y),
          w: Math.abs(drawEnd.x - drawStart.x),
          h: Math.abs(drawEnd.y - drawStart.y),
        }
      : null;

  // Unique labels for the legend
  const uniqueLabels = Array.from(new Set(exemplars.map((e) => e.label)));

  // Colors for different labels
  const COLORS = [
    "rgb(59, 130, 246)",   // blue
    "rgb(16, 185, 129)",   // emerald
    "rgb(245, 158, 11)",   // amber
    "rgb(239, 68, 68)",    // red
    "rgb(168, 85, 247)",   // purple
    "rgb(236, 72, 153)",   // pink
    "rgb(20, 184, 166)",   // teal
    "rgb(249, 115, 22)",   // orange
  ];
  const labelColor = (label: string) =>
    COLORS[uniqueLabels.indexOf(label) % COLORS.length] || COLORS[0];

  return (
    <div className="fixed inset-0 z-50 bg-gray-950/95 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-3 bg-gray-900 border-b border-gray-800">
        <div>
          <h2 className="text-sm font-semibold text-gray-100">
            Select Fixture Symbols — Page {pageNumber}
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Click and drag to draw a box around each fixture symbol.
            Box one of each orientation for the same fixture type.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg text-xs font-medium text-gray-300 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="px-4 py-2 bg-primary-600 hover:bg-primary-500 rounded-lg text-xs font-semibold transition-colors"
          >
            Save {exemplars.length} Exemplar{exemplars.length !== 1 ? "s" : ""}
          </button>
        </div>
      </div>

      {/* Main area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Drawing canvas */}
        <div
          ref={containerRef}
          className="flex-1 overflow-auto relative cursor-crosshair"
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
        >
          {loading && (
            <div className="flex items-center justify-center h-full">
              <div className="w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
            </div>
          )}
          {error && (
            <div className="flex items-center justify-center h-full">
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}
          {imageUrl && (
            <>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                ref={imgRef}
                src={imageUrl}
                alt={`Page ${pageNumber}`}
                onLoad={handleImageLoad}
                className="max-w-none"
                draggable={false}
              />

              {/* Existing exemplar boxes */}
              {exemplars.map((ex, i) => {
                const r = toDisplayRect(ex);
                return (
                  <div
                    key={i}
                    className="absolute pointer-events-none"
                    style={{
                      left: r.left,
                      top: r.top,
                      width: r.width,
                      height: r.height,
                      border: `2px solid ${labelColor(ex.label)}`,
                      backgroundColor: `${labelColor(ex.label)}`.replace("rgb", "rgba").replace(")", ", 0.1)"),
                    }}
                  >
                    <span
                      className="absolute -top-5 left-0 text-[10px] font-bold px-1 rounded"
                      style={{
                        backgroundColor: labelColor(ex.label),
                        color: "white",
                      }}
                    >
                      {ex.label}
                    </span>
                  </div>
                );
              })}

              {/* Pending box (being labeled) */}
              {pendingBox && (
                <div
                  className="absolute pointer-events-none"
                  style={{
                    ...toDisplayRect(pendingBox),
                    border: "2px dashed rgb(250, 204, 21)",
                    backgroundColor: "rgba(250, 204, 21, 0.1)",
                  }}
                />
              )}

              {/* Active drag rectangle */}
              {dragRect && (
                <div
                  className="absolute pointer-events-none"
                  style={{
                    ...toDisplayRect(dragRect),
                    border: "2px dashed white",
                    backgroundColor: "rgba(255, 255, 255, 0.1)",
                  }}
                />
              )}
            </>
          )}
        </div>

        {/* Sidebar: exemplar list + label input */}
        <div className="w-72 bg-gray-900 border-l border-gray-800 flex flex-col">
          {/* Label input dialog */}
          {pendingBox && (
            <div className="p-4 bg-yellow-950/30 border-b border-yellow-900/50">
              <p className="text-xs font-medium text-yellow-300 mb-2">
                Label this symbol:
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  confirmLabel();
                }}
                className="flex gap-2"
              >
                <input
                  ref={labelRef}
                  type="text"
                  value={labelInput}
                  onChange={(e) => setLabelInput(e.target.value.toUpperCase())}
                  placeholder="e.g. LT04"
                  className="flex-1 px-3 py-2 bg-gray-950 border border-gray-700 rounded-lg text-sm text-gray-100 font-mono placeholder:text-gray-600 focus:outline-none focus:border-primary-500"
                />
                <button
                  type="submit"
                  disabled={!labelInput.trim()}
                  className="px-3 py-2 bg-primary-600 hover:bg-primary-500 disabled:bg-gray-800 disabled:text-gray-500 rounded-lg text-xs font-semibold transition-colors"
                >
                  Add
                </button>
              </form>
              <button
                onClick={cancelLabel}
                className="mt-2 text-xs text-gray-500 hover:text-gray-300"
              >
                Cancel
              </button>
            </div>
          )}

          {/* Exemplar list */}
          <div className="flex-1 overflow-y-auto p-4">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
              Exemplars ({exemplars.length})
            </h3>

            {exemplars.length === 0 ? (
              <p className="text-xs text-gray-600">
                Draw a box around a fixture symbol to add an exemplar.
              </p>
            ) : (
              <div className="space-y-2">
                {exemplars.map((ex, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between bg-gray-800 rounded-lg px-3 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <div
                        className="w-3 h-3 rounded-sm"
                        style={{ backgroundColor: labelColor(ex.label) }}
                      />
                      <span className="text-xs font-mono font-medium text-gray-200">
                        {ex.label}
                      </span>
                      <span className="text-[10px] text-gray-500">
                        {Math.round(ex.w)}x{Math.round(ex.h)}px
                      </span>
                    </div>
                    <button
                      onClick={() => removeExemplar(i)}
                      className="text-gray-600 hover:text-red-400 transition-colors"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Legend summary */}
            {uniqueLabels.length > 0 && (
              <div className="mt-4 pt-4 border-t border-gray-800">
                <h4 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-2">
                  Fixture Types
                </h4>
                {uniqueLabels.map((label) => {
                  const count = exemplars.filter((e) => e.label === label).length;
                  return (
                    <div key={label} className="flex items-center gap-2 mb-1">
                      <div
                        className="w-2.5 h-2.5 rounded-sm"
                        style={{ backgroundColor: labelColor(label) }}
                      />
                      <span className="text-xs font-mono text-gray-300">
                        {label}
                      </span>
                      <span className="text-[10px] text-gray-600">
                        {count} exemplar{count !== 1 ? "s" : ""}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Tip */}
          <div className="p-4 border-t border-gray-800">
            <p className="text-[10px] text-gray-600 leading-relaxed">
              Tip: For fixtures that appear in different orientations (0 and 90),
              draw one box for each orientation using the same label.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
