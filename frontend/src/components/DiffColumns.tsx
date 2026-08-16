/* eslint-disable no-restricted-syntax -- Diff view uses inline pre/grid styling */
/**
 * The two-column body of a side-by-side text diff: a header per side, then one
 * row per line with changed lines tinted.
 *
 * Renders as four consecutive grid cells rather than its own container, so the
 * caller owns the grid and can append aligned cells of its own — which is what
 * the drift panel does with its resolution buttons. Wrap it in
 * `<div style={diffGridStyle}>` (plus whatever border/rounding you want) to get
 * a plain diff with nothing after it.
 *
 * Lightweight and dependency-free, suitable for short workflow files.
 */
import React from "react";

export const diffGridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1fr 1fr",
  fontFamily: "monospace",
  fontSize: "0.8rem",
};

const HEADER_CLASS =
  "bg-slate-50 dark:bg-slate-800 px-2 py-1 text-sm font-semibold border-b border-slate-200 dark:border-slate-700";

export const DiffColumns: React.FC<{
  left: string;
  right: string;
  leftLabel: string;
  rightLabel: string;
}> = ({ left, right, leftLabel, rightLabel }) => {
  const leftLines = (left || "").split("\n");
  const rightLines = (right || "").split("\n");
  const max = Math.max(leftLines.length, rightLines.length);
  // A rendered line is identified by where it sits and what it says, so editing
  // a line remounts that row rather than reusing the previous one's state.
  const rows: { l: string; r: string; changed: boolean; lKey: string; rKey: string }[] = [];
  for (let i = 0; i < max; i++) {
    const l = leftLines[i] ?? "";
    const r = rightLines[i] ?? "";
    rows.push({ l, r, changed: l !== r, lKey: `${i}:${l}`, rKey: `${i}:${r}` });
  }

  return (
    <>
      <div className={`${HEADER_CLASS} border-r`}>{leftLabel}</div>
      <div className={HEADER_CLASS}>{rightLabel}</div>

      <div
        className="m-0 px-2 py-1 overflow-x-auto whitespace-pre border-r border-slate-200 dark:border-slate-700"
        style={{ background: "transparent" }}
      >
        {rows.map((row) => (
          <div
            key={row.lKey}
            style={{ backgroundColor: row.changed && row.l ? "rgba(239,68,68,0.10)" : undefined }}
          >
            {row.l || " "}
          </div>
        ))}
      </div>
      <div
        className="m-0 px-2 py-1 overflow-x-auto whitespace-pre"
        style={{ background: "transparent" }}
      >
        {rows.map((row) => (
          <div
            key={row.rKey}
            style={{ backgroundColor: row.changed && row.r ? "rgba(16,185,129,0.12)" : undefined }}
          >
            {row.r || " "}
          </div>
        ))}
      </div>
    </>
  );
};

export default DiffColumns;
