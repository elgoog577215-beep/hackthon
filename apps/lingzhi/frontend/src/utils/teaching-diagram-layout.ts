import type { TeachingDiagram } from "./teaching-diagrams";

// One coordinate system for shapes, strokes, arrowheads and text. Marker
// dimensions must not multiply the line's stroke width when the SVG shrinks.
export const teachingDiagramStyle =
  '.teaching-diagram-svg text{font-family:system-ui,"Microsoft YaHei",sans-serif}.teaching-diagram-svg{background:#fff}';

export const teachingDiagramMarkers = (id: string) =>
  `<marker id="${id}" markerUnits="userSpaceOnUse" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="10" markerHeight="10" orient="auto"><path d="M1 1L9 5L1 9Z" fill="context-stroke"/></marker>` +
  `<marker id="${id}-inheritance" markerUnits="userSpaceOnUse" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="12" markerHeight="12" orient="auto"><path d="M1 1L11 6L1 11Z" fill="#fff" stroke="context-stroke"/></marker>` +
  `<marker id="${id}-composition" markerUnits="userSpaceOnUse" viewBox="0 0 16 12" refX="15" refY="6" markerWidth="14" markerHeight="12" orient="auto"><path d="M1 6L8 1L15 6L8 11Z" fill="context-stroke"/></marker>`;

export type DiagramReadingRow = { label: string; value: string };

// Compact figures are an overview. Reflow the actual labels and values below
// them instead of forcing readers to decipher scaled-down SVG lettering.
export function diagramReadingRows(d: TeachingDiagram): DiagramReadingRow[] {
  const unit = d.unit ? ` ${d.unit}` : "";
  const groupLabel = (id?: string) => d.groups.find((g) => g.id === id)?.label;
  if (d.series.length)
    return d.series.map((s) => ({
      label: s.label,
      value: s.points
        ? s.points
            .map(
              (p) =>
                `${p.label || p.x}: ${p.y === null ? "缺测 / Missing" : p.y + unit}`,
            )
            .join("; ")
        : (s.values || [])
            .map((value, i) => `${d.axes[i] || i + 1}: ${value}${unit}`)
            .join("; "),
    }));
  if (d.sets.length)
    return [
      ...d.sets.map((s) => ({
        label: s.label,
        value: `{${s.items.join(", ")}}`,
      })),
      ...(d.universe
        ? [{ label: "全集 / Universe", value: `{${d.universe.join(", ")}}` }]
        : []),
    ];
  if (d.rows.length && d.columns.length && d.values.length)
    return d.rows.map((label, i) => ({
      label,
      value: d.columns
        .map(
          (column, j) =>
            `${column}: ${d.values[i]?.[j] === null ? "缺测 / Missing" : d.values[i]?.[j]}${unit}`,
        )
        .join("; "),
    }));
  if (d.items.length)
    return d.items.map((item) => ({
      label: item.label,
      value: [
        item.value === undefined ? "" : `${item.value}${unit}`,
        item.start === undefined || item.end === undefined
          ? ""
          : `${item.start} → ${item.end}${unit}`,
        item.x === undefined || item.y === undefined
          ? ""
          : `(${item.x}, ${item.y})${unit}`,
        item.width === undefined || item.height === undefined
          ? ""
          : `${item.width} × ${item.height}${item.depth === undefined ? "" : ` × ${item.depth}`}${unit}`,
        groupLabel(item.group),
        item.detail,
      ]
        .filter(Boolean)
        .join(" · "),
    }));
  // Additional validated geometry may carry vectors without the generic item
  // fields. Keep this projection optional so the original contract still works.
  const vectors = (
    d as unknown as {
      vectors?: {
        label: string;
        from: number[];
        to: number[];
        detail?: string;
      }[];
    }
  ).vectors;
  if (vectors?.length)
    return vectors.map((v) => ({
      label: v.label,
      value: `(${v.from.join(", ")}) → (${v.to.join(", ")})${unit}${v.detail ? ` · ${v.detail}` : ""}`,
    }));
  const steps = (
    d as unknown as {
      steps?: {
        label: string;
        operation?: string;
        values: (number | string)[][];
      }[];
    }
  ).steps;
  if (steps?.length)
    return steps.map((step) => ({
      label: step.label,
      value: [
        step.operation,
        ...step.values.map((row) => `[${row.join(", ")}]`),
      ]
        .filter(Boolean)
        .join("\n"),
    }));
  if (d.before && d.after)
    return [
      {
        label: "之前 / Before",
        value: d.before.nodes.map((n) => n.label).join("; "),
      },
      {
        label: "之后 / After",
        value: d.after.nodes.map((n) => n.label).join("; "),
      },
    ];
  return d.nodes.map((n) => ({
    label: n.label,
    value: [
      n.detail,
      groupLabel(n.group),
      n.status,
      n.parent ? d.nodes.find((p) => p.id === n.parent)?.label : "",
    ]
      .filter(Boolean)
      .join(" · "),
  }));
}
