"use client";

import { useState } from "react";
import { TakeoffResults, Diagnostics, getReportUrl } from "@/lib/api";

interface ResultsViewProps {
  jobId: string;
  results: TakeoffResults;
}

export default function ResultsView({ jobId, results }: ResultsViewProps) {
  const { floors, building_totals, summary, diagnostics } = results;
  const floorNames = Object.keys(floors);
  const types = summary.luminaire_types;
  const [showDiag, setShowDiag] = useState(summary.total_fixtures === 0);

  const downloadJson = () => {
    const blob = new Blob([JSON.stringify(results, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `aecai_results_${jobId}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadCsv = () => {
    const escape = (val: string | number) => {
      const s = String(val);
      return s.includes(",") || s.includes('"')
        ? `"${s.replace(/"/g, '""')}"`
        : s;
    };

    const header = ["Floor", ...types, "Total"];
    const rows: string[][] = [];

    for (const floor of floorNames) {
      const counts = floors[floor];
      const rowTotal = Object.values(counts).reduce((a, b) => a + b, 0);
      rows.push([
        floor,
        ...types.map((t) => String(counts[t] || 0)),
        String(rowTotal),
      ]);
    }

    rows.push([
      "Building Total",
      ...types.map((t) => String(building_totals[t] || 0)),
      String(summary.total_fixtures),
    ]);

    const csv =
      [header, ...rows].map((r) => r.map(escape).join(",")).join("\n") + "\n";

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `aecai_takeoff_${jobId}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-8">
      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">
            Total Fixtures
          </p>
          <p className="text-3xl font-bold text-primary-400">
            {summary.total_fixtures.toLocaleString()}
          </p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">
            Floors Processed
          </p>
          <p className="text-3xl font-bold text-gray-100">
            {summary.num_floors}
          </p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">
            Luminaire Types
          </p>
          <p className="text-3xl font-bold text-gray-100">{types.length}</p>
        </div>
      </div>

      {/* Fixture Count Table */}
      <div className="space-y-4">
        <h3 className="font-semibold text-gray-100">Fixture Count by Floor</h3>

        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="text-left px-4 py-3 text-xs text-gray-500 uppercase tracking-wider font-medium sticky left-0 bg-gray-900 z-10">
                    Type
                  </th>
                  {floorNames.map((floor) => (
                    <th
                      key={floor}
                      className="text-right px-4 py-3 text-xs text-gray-500 uppercase tracking-wider font-medium whitespace-nowrap"
                    >
                      {floor}
                    </th>
                  ))}
                  <th className="text-right px-4 py-3 text-xs text-primary-400 uppercase tracking-wider font-semibold">
                    Total
                  </th>
                </tr>
              </thead>
              <tbody>
                {types.map((t) => {
                  const total = building_totals[t] || 0;
                  if (total === 0) return null;
                  return (
                    <tr
                      key={t}
                      className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors"
                    >
                      <td className="px-4 py-2.5 font-mono text-gray-200 font-medium sticky left-0 bg-gray-900 z-10">
                        {t}
                      </td>
                      {floorNames.map((floor) => {
                        const count = floors[floor][t] || 0;
                        return (
                          <td
                            key={floor}
                            className={`text-right px-4 py-2.5 tabular-nums ${
                              count > 0
                                ? "text-gray-100"
                                : "text-gray-700"
                            }`}
                          >
                            {count > 0 ? count : "\u2014"}
                          </td>
                        );
                      })}
                      <td className="text-right px-4 py-2.5 tabular-nums font-semibold text-primary-400">
                        {total}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="bg-primary-950/30 border-t-2 border-primary-800">
                  <td className="px-4 py-3 font-bold text-primary-300 sticky left-0 bg-primary-950/30 z-10">
                    Building Total
                  </td>
                  {floorNames.map((floor) => {
                    const floorTotal = Object.values(floors[floor]).reduce(
                      (a, b) => a + b,
                      0
                    );
                    return (
                      <td
                        key={floor}
                        className="text-right px-4 py-3 tabular-nums font-semibold text-primary-200"
                      >
                        {floorTotal}
                      </td>
                    );
                  })}
                  <td className="text-right px-4 py-3 tabular-nums font-bold text-primary-300">
                    {summary.total_fixtures.toLocaleString()}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      </div>

      {/* Diagnostics Panel */}
      {diagnostics && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <button
            onClick={() => setShowDiag(!showDiag)}
            className="w-full px-5 py-4 border-b border-gray-800 flex items-center justify-between hover:bg-gray-800/30 transition-colors"
          >
            <h3 className="font-semibold text-gray-100 flex items-center gap-2">
              {summary.total_fixtures === 0 && (
                <span className="w-2 h-2 rounded-full bg-amber-500" />
              )}
              Pipeline Diagnostics
            </h3>
            <svg
              className={`w-4 h-4 text-gray-400 transition-transform ${
                showDiag ? "rotate-180" : ""
              }`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 9l-7 7-7-7"
              />
            </svg>
          </button>

          {showDiag && (
            <div className="px-5 py-4 space-y-4 text-sm">
              {/* Legend / prefix info */}
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">
                  Detection Method
                </p>
                {diagnostics.legend_source === "exemplars" ? (
                  <p className="text-gray-300">
                    Template matching with{" "}
                    <span className="font-mono font-semibold text-primary-400">
                      {diagnostics.templates_extracted ?? 0}
                    </span>{" "}
                    exemplar{(diagnostics.templates_extracted ?? 0) !== 1 ? "s" : ""}{" "}
                    {diagnostics.active_codes?.length > 0 && (
                      <span className="text-gray-400">
                        ({diagnostics.active_codes.join(", ")})
                      </span>
                    )}
                  </p>
                ) : diagnostics.fixture_prefix ? (
                  <p className="text-gray-300">
                    All ovals captured, filtered by prefix:{" "}
                    <span className="font-mono font-semibold text-primary-400">
                      {diagnostics.fixture_prefix}*
                    </span>
                  </p>
                ) : (
                  <p className="text-gray-300">
                    All ovals with alphanumeric text captured (no prefix filter)
                  </p>
                )}
              </div>

              {/* Per-page breakdown */}
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">
                  Per-Page Detection
                </p>
                <div className="space-y-2">
                  {Object.entries(diagnostics.pages).map(
                    ([pageName, info]) => (
                      <div
                        key={pageName}
                        className="bg-gray-950 border border-gray-800 rounded-lg px-4 py-2.5"
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-gray-200 font-medium">
                            {pageName}
                          </span>
                          {info.status === "skipped" ? (
                            <span className="text-xs text-gray-500">
                              Skipped
                            </span>
                          ) : info.detection_method === "template" ? (
                            <span className="text-xs text-gray-400">
                              <span
                                className={
                                  (info.template_matches ?? 0) === 0
                                    ? "text-red-400 font-semibold"
                                    : "text-primary-400"
                                }
                              >
                                {info.template_matches ?? 0} shapes
                              </span>
                              {" → "}
                              <span
                                className={
                                  (info.ocr_recognised ?? 0) === 0
                                    ? "text-amber-400"
                                    : "text-green-400"
                                }
                              >
                                {info.ocr_recognised ?? 0} recognised
                              </span>
                            </span>
                          ) : (
                            <span className="text-xs text-gray-400">
                              <span
                                className={
                                  info.shapes_found === 0
                                    ? "text-red-400 font-semibold"
                                    : "text-primary-400"
                                }
                              >
                                {info.shapes_found} ovals
                              </span>
                              {" → "}
                              <span
                                className={
                                  info.shapes_matched === 0
                                    ? "text-amber-400"
                                    : "text-green-400"
                                }
                              >
                                {info.shapes_matched} matched
                              </span>
                            </span>
                          )}
                        </div>
                        {info.raw_ocr_samples &&
                          info.raw_ocr_samples.length > 0 && (
                            <div className="mt-1.5">
                              <span className="text-[10px] text-gray-500 uppercase">
                                Raw OCR samples:{" "}
                              </span>
                              <span className="text-xs text-gray-400 font-mono">
                                {info.raw_ocr_samples
                                  .map((s) => `"${s}"`)
                                  .join(", ")}
                              </span>
                            </div>
                          )}
                        {info.status !== "skipped" &&
                          info.detection_method === "template" &&
                          (info.template_matches ?? 0) === 0 && (
                            <p className="text-xs text-red-400 mt-1">
                              No shapes matched the template on this page.
                            </p>
                          )}
                        {info.status !== "skipped" &&
                          info.detection_method === "template" &&
                          (info.template_matches ?? 0) > 0 &&
                          (info.ocr_recognised ?? 0) === 0 && (
                            <p className="text-xs text-amber-400 mt-1">
                              Shapes found but OCR could not read fixture codes.
                            </p>
                          )}
                        {info.status !== "skipped" &&
                          info.detection_method !== "template" &&
                          (info.shapes_found ?? 0) === 0 && (
                            <p className="text-xs text-red-400 mt-1">
                              No ovals detected on this page.
                            </p>
                          )}
                        {info.status !== "skipped" &&
                          info.detection_method !== "template" &&
                          (info.shapes_found ?? 0) > 0 &&
                          info.shapes_matched === 0 && (
                            <p className="text-xs text-amber-400 mt-1">
                              Ovals found but no text matched the prefix/codes.
                            </p>
                          )}
                      </div>
                    )
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Download Buttons */}
      <div className="flex flex-wrap gap-3">
        <button
          onClick={downloadCsv}
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-500 rounded-lg text-sm font-semibold text-white transition-colors"
        >
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
            />
          </svg>
          Export Spreadsheet (.csv)
        </button>
        <a
          href={getReportUrl(jobId)}
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg text-sm font-medium text-gray-200 transition-colors"
        >
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
          Download TXT Report
        </a>
        <button
          onClick={downloadJson}
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg text-sm font-medium text-gray-200 transition-colors"
        >
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
            />
          </svg>
          Download JSON Data
        </button>
      </div>
    </div>
  );
}
