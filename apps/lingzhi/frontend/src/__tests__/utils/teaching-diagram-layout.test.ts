import { describe, expect, it } from "vitest";
import { teachingDiagramSamples } from "../../../dev/teaching-diagram-samples";
import {
  parseTeachingDiagram,
  teachingDiagramSvg,
} from "../../utils/teaching-diagrams";
import { diagramReadingRows } from "../../utils/teaching-diagram-layout";

const spec = (type: string) =>
  parseTeachingDiagram(
    JSON.stringify(teachingDiagramSamples.find((s) => s.type === type)),
  );

describe("responsive teaching diagram presentation", () => {
  it("uses one scaling system for arrowheads, strokes and text at every embedding size", () => {
    const raw = teachingDiagramSvg(spec("flowchart"), "responsive");
    const doc = new DOMParser().parseFromString(raw, "image/svg+xml");
    const markers = [...doc.querySelectorAll("marker")];
    expect(markers).toHaveLength(3);
    for (const marker of markers)
      expect(marker.getAttribute("markerUnits")).toBe("userSpaceOnUse");
    expect(doc.querySelector("marker path")?.getAttribute("fill")).toBe(
      "context-stroke",
    );
    expect(raw).not.toContain("non-scaling-stroke");
    expect(doc.querySelector("style")?.textContent).toContain(
      ".teaching-diagram-svg text",
    );
  });
  it("reflows actual quantities and labels without inventing or rounding values", () => {
    const d = spec("bar_chart");
    expect(diagramReadingRows(d)).toEqual(
      d.items.map((item) => ({
        label: item.label,
        value: `${item.value} ${d.unit}`,
      })),
    );
    const matrix = spec("heatmap");
    const text = diagramReadingRows(matrix)
      .map((row) => row.value)
      .join("\n");
    expect(text).toContain("缺测 / Missing");
    expect(text).toContain(": 0");
  });
  it("preserves sets and series with their complete names and observations", () => {
    const set = spec("venn");
    for (const s of set.sets)
      expect(diagramReadingRows(set)).toContainEqual({
        label: s.label,
        value: `{${s.items.join(", ")}}`,
      });
    const line = spec("line_chart");
    const rows = diagramReadingRows(line);
    expect(rows.map((row) => row.label)).toEqual(
      line.series.map((s) => s.label),
    );
    expect(rows.map((row) => row.value).join("\n")).toContain("缺测 / Missing");
  });
});
