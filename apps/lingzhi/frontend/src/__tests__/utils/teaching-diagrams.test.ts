import { describe, expect, it } from "vitest";
import { teachingDiagramSamples } from "../../../dev/teaching-diagram-samples";
import {
  parseTeachingDiagram,
  teachingDiagramCatalog,
  teachingDiagramSvg,
} from "../../utils/teaching-diagrams";

const fixture = (type: string, overrides = {}) =>
  JSON.stringify({
    ...teachingDiagramSamples.find((s) => s.type === type),
    ...overrides,
  });
const svg = (type: string, overrides = {}) =>
  new DOMParser().parseFromString(
    teachingDiagramSvg(
      parseTeachingDiagram(fixture(type, overrides)),
      "sample",
    ),
    "image/svg+xml",
  );

describe("teaching diagram semantics and geometry", () => {
  it("covers all 44 types with unique identities", () => {
    expect(teachingDiagramCatalog.types).toHaveLength(44);
    expect(new Set(teachingDiagramCatalog.types.map((t) => t.id)).size).toBe(
      44,
    );
    expect(teachingDiagramSamples.map((s) => s.type)).toEqual(
      teachingDiagramCatalog.types.map((t) => t.id),
    );
  });
  it.each(teachingDiagramSamples.map((s) => [s.type, s]))(
    "draws %s without dropping its source, invalid numbers or executable content",
    (_type, sample) => {
      const spec = parseTeachingDiagram(JSON.stringify(sample)),
        xml = teachingDiagramSvg(spec, "sample");
      const doc = new DOMParser().parseFromString(xml, "image/svg+xml");
      expect(doc.querySelector("parsererror")).toBeNull();
      expect(doc.querySelector("svg > title")?.textContent).toBe(spec.title);
      expect(doc.querySelector("svg > desc")?.textContent).toContain(
        spec.source,
      );
      expect(doc.querySelector("svg > desc")?.textContent).toContain(
        spec.summary,
      );
      expect(xml).not.toMatch(/NaN|Infinity|undefined/);
      expect(doc.querySelector("script,foreignObject,image,a")).toBeNull();
      const ids = [...doc.querySelectorAll("[id]")].map((n) => n.id);
      expect(new Set(ids).size).toBe(ids.length);
      expect(+doc.documentElement.getAttribute("height")!).toBeGreaterThan(0);
    },
  );
  it("keeps complete and hostile labels as text", () => {
    const label = "<img src=x onerror=alert(1)> " + "很长的名称".repeat(24);
    const doc = svg("architecture", { nodes: [{ id: "a", label }], edges: [] });
    expect(doc.querySelector("image,img,script")).toBeNull();
    expect(
      [...doc.querySelectorAll("tspan")].map((n) => n.textContent).join(""),
    ).toContain(label);
  });
  it("uses a common zero baseline for positive and negative bars", () => {
    const doc = svg("bar_chart", {
      items: [
        { label: "A", value: -5 },
        { label: "B", value: 10 },
      ],
    });
    const negative = doc.querySelector('[data-value="-5"]')!,
      positive = doc.querySelector('[data-value="10"]')!;
    expect(+positive.getAttribute("width")!).toBeCloseTo(
      +negative.getAttribute("width")! * 2,
    );
    expect(
      +negative.getAttribute("x")! + +negative.getAttribute("width")!,
    ).toBeCloseTo(+positive.getAttribute("x")!);
  });
  it("keeps a finite extent for a single very large observation", () => {
    const doc = svg("timeline", {
      items: [{ label: "Observation", value: 1e100 }],
    });
    expect(doc.documentElement.outerHTML).not.toMatch(/NaN|Infinity/);
  });
  it("positions time and duration according to real intervals", () => {
    const doc = svg("timeline"),
      circles = [...doc.querySelectorAll("[data-time]")];
    const xs = circles.map((c) => +c.getAttribute("cx")!);
    expect(xs[2]! - xs[1]!).toBeCloseTo(2 * (xs[1]! - xs[0]!));
    expect(xs[3]! - xs[2]!).toBeCloseTo(3 * (xs[1]! - xs[0]!));
    const gantt = svg("gantt"),
      tasks = [...gantt.querySelectorAll("[data-start]")];
    expect(+tasks[1]!.getAttribute("width")!).toBeCloseTo(
      +tasks[0]!.getAttribute("width")! * 1.5,
    );
  });
  it("lays out cyclic algorithms in forward order while keeping the repeat edge", () => {
    const doc = svg("flowchart", {
      nodes: [
        { id: "start", label: "Start" },
        { id: "check", label: "Check", kind: "decision" },
        { id: "next", label: "Increment" },
        { id: "end", label: "End" },
      ],
      edges: [
        { from: "start", to: "check" },
        { from: "check", to: "next", label: "continue" },
        { from: "check", to: "end", label: "finished" },
        { from: "next", to: "check", label: "repeat" },
      ],
    });
    const y = (id: string) =>
      +doc.querySelector(`[data-node-id="${id}"] text`)!.getAttribute("y")!;
    expect(y("check")).toBeGreaterThan(y("start"));
    expect(y("next")).toBeGreaterThan(y("check"));
    expect(doc.documentElement.textContent).toContain("repeat");
  });
  it("accumulates waterfall changes exactly once", () => {
    const doc = svg("waterfall"),
      segments = [...doc.querySelectorAll("rect[data-from]")];
    expect(
      segments.map((r) => [
        r.getAttribute("data-from"),
        r.getAttribute("data-to"),
      ]),
    ).toEqual([
      ["0", "100"],
      ["100", "130"],
      ["130", "110"],
      ["0", "110"],
    ]);
  });
  it("keeps missing heatmap values distinct from zero and breaks missing line segments", () => {
    const matrix = svg("heatmap");
    expect(
      matrix.querySelector('[data-row="0"][data-column="1"]')?.textContent,
    ).toContain("∅");
    expect(
      matrix.querySelector('[data-row="1"][data-column="1"]')?.textContent,
    ).toBe("0");
    const lines = [
      ...svg("line_chart").querySelectorAll('path[stroke-width="2.5"]'),
    ];
    expect(lines).toHaveLength(2);
    expect(lines[1]!.getAttribute("d")).not.toContain("L");
  });
  it("computes actual finite-set intersections", () => {
    const doc = svg("venn");
    expect(doc.documentElement.textContent).toContain("A ∩ B: {3, 4}");
    expect(doc.documentElement.textContent).toContain("A ∩ ¬B: {1, 2}");
  });
  it.each([
    [
      "tree",
      {
        nodes: [
          { id: "a", label: "A" },
          { id: "b", label: "B" },
        ],
        edges: [
          { from: "a", to: "b" },
          { from: "b", to: "a" },
        ],
      },
    ],
    ["architecture", { edges: [{ from: "missing", to: "a" }] }],
    ["flowchart", { edges: [{ from: "check", to: "read" }] }],
    [
      "sankey",
      {
        edges: [
          { from: "a", to: "b", value: 10 },
          { from: "b", to: "c", value: 9 },
          { from: "c", to: "d", value: 9 },
        ],
      },
    ],
    ["radar", { scale: [0, 3] }],
    ["gantt", { items: [{ label: "A", start: 5, end: 3 }] }],
    [
      "treemap",
      {
        items: [
          { label: "Empty", value: 0 },
          { label: "Other", value: 1 },
        ],
      },
    ],
    ["heatmap", { values: [[1], [2]] }],
    [
      "pyramid_funnel",
      {
        items: [
          { label: "A", value: 1 },
          { label: "B", value: 2 },
        ],
      },
    ],
    [
      "axonometric_plan",
      { items: [{ label: "A", x: 0, y: 0, width: -1, height: 2 }] },
    ],
    ["story_map", { rows: ["unknown"] }],
    [
      "architecture",
      {
        nodes: Array.from({ length: 25 }, (_, i) => ({
          id: String(i),
          label: String(i),
        })),
        edges: [],
      },
    ],
  ])(
    "rejects misleading or oversized %s data instead of drawing it",
    (type, overrides) => {
      expect(() =>
        parseTeachingDiagram(fixture(type as string, overrides)),
      ).toThrow();
    },
  );
});
