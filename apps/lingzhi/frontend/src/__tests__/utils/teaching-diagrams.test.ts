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
  it('uses readable vector ticks without changing exact endpoints or equal units', () => {
    const doc = svg('vector_plot')
    expect([...doc.querySelectorAll('[data-tick-x]')].map(el => el.getAttribute('data-tick-x'))).toEqual(['0','1','2','3','4','5'])
    expect([...doc.querySelectorAll('[data-tick-y]')].map(el => el.getAttribute('data-tick-y'))).toEqual(['0','1','2','3','4'])
    const fractional = svg('vector_plot', { vectors: [{label:'v', from:[-.4,.25],to:[.6,-.75]}] })
    expect(fractional.querySelector('[data-vector]')?.getAttribute('data-from')).toBe('-0.4,0.25')
    const ticks = [...fractional.querySelectorAll('[data-tick-x], [data-tick-y]')].map(el => Number(el.getAttribute('data-tick-x') ?? el.getAttribute('data-tick-y')))
    expect(ticks.every(value => Number.isFinite(value) && Math.abs(value / .2 - Math.round(value / .2)) < 1e-6)).toBe(true)
    expect(fractional.documentElement.outerHTML).not.toMatch(/NaN|Infinity/)
  })
  it('keeps vector endpoints and equal axis scale, including translated and zero vectors', () => {
    const doc = svg('vector_plot')
    expect(doc.querySelectorAll('[data-vector]')).toHaveLength(3)
    expect(doc.querySelector('[data-vector="2v"]')?.getAttribute('data-from')).toBe('1,2')
    expect(doc.querySelector('[data-vector="2v"]')?.getAttribute('data-to')).toBe('5,4')
    const coordinates = doc.querySelector('[data-vector="u"] path')!.getAttribute('d')!.match(/-?\d+(?:\.\d+)?/g)!.map(Number)
    expect(Math.abs((coordinates[3]! - coordinates[1]!) / (coordinates[2]! - coordinates[0]!))).toBeCloseTo(2)
    const zero = svg('vector_plot', { vectors: [{label:'zero', from:[0,0], to:[0,0]}] })
    expect(zero.querySelector('[data-vector] circle')).not.toBeNull()
    expect(() => parseTeachingDiagram(fixture('vector_plot', { vectors: [{label:'bad', from:[0], to:[1,2]}] }))).toThrow()
  })
  it('draws every matrix cell and operation, rejecting inconsistent dimensions', () => {
    const doc = svg('matrix_steps')
    expect(doc.querySelectorAll('[data-step]')).toHaveLength(12)
    expect(doc.documentElement.textContent).toContain('R₂ ← R₂ − 2R₁')
    expect(doc.querySelector('[data-step="1"][data-row="1"][data-column="2"]')?.textContent).toBe('-6')
    expect(() => parseTeachingDiagram(fixture('matrix_steps', { steps: [{label:'one', values:[[1,2]]}, {label:'two',values:[[1]]}] }))).toThrow()
  })
  it('keeps long decision labels and details inside their diamond', () => {
    const doc = svg('flowchart', { nodes: [{ id:'check', kind:'decision', label:'是否出现矛盾行 [0...0, c]（c≠0）？', detail:'只讨论消元后矩阵' }, {id:'yes',label:'无解'}, {id:'no',label:'继续判断'}], edges:[{from:'check',to:'yes',label:'是'},{from:'check',to:'no',label:'否'}] })
    const node = doc.querySelector('[data-node-id="check"]')!
    const points = node.querySelector('polygon')!.getAttribute('points')!.split(' ').map(p=>p.split(',').map(Number))
    const xs=points.map(p=>p[0]!), ys=points.map(p=>p[1]!), cx=(Math.min(...xs)+Math.max(...xs))/2, cy=(Math.min(...ys)+Math.max(...ys))/2
    const rx=(Math.max(...xs)-Math.min(...xs))/2, ry=(Math.max(...ys)-Math.min(...ys))/2
    for (const text of node.querySelectorAll('text')) {
      let baseline=Number(text.getAttribute('y'))
      for (const span of text.querySelectorAll('tspan')) {
        baseline+=Number(span.getAttribute('dy'))
        const width=[...span.textContent!].reduce((sum,c)=>sum+(/[^\x00-\xff]/.test(c)?16:8),0)
        for (const y of [baseline-16,baseline+5]) expect((Math.abs(Number(span.getAttribute('x'))-cx)+width/2)/rx+Math.abs(y-cy)/ry).toBeLessThanOrEqual(1)
      }
    }
    expect([...node.querySelectorAll('tspan')].map(n=>n.textContent).join('')).toContain('是否出现矛盾行 [0...0, c]（c≠0）？')
    expect(node.textContent).toContain('只讨论消元后矩阵')
  })
  it("covers all 46 types with unique identities", () => {
    expect(teachingDiagramCatalog.types).toHaveLength(46);
    expect(new Set(teachingDiagramCatalog.types.map((t) => t.id)).size).toBe(
      46,
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
