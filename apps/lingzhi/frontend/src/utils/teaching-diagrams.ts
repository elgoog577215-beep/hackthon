import catalog from "../../../shared/teaching-diagrams-v1.json";
import { teachingDiagramMarkers, teachingDiagramStyle } from './teaching-diagram-layout';

export const teachingDiagramCatalog = catalog;
export type DiagramNode = {
  id: string;
  label: string;
  detail?: string;
  parent?: string;
  group?: string;
  kind?: string;
  status?: string;
  row?: string;
  x?: number;
  y?: number;
};
export type DiagramEdge = {
  from: string;
  to: string;
  label?: string;
  kind?: string;
  value?: number;
};
export type DiagramItem = {
  id?: string;
  label: string;
  detail?: string;
  parent?: string;
  group?: string;
  value?: number;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  depth?: number;
  start?: number;
  end?: number;
};
export type DiagramGroup = { id: string; label: string; limit?: number };
export type DiagramSeries = {
  label: string;
  values?: number[];
  points?: { x: number; y: number | null; label?: string }[];
};
export type TeachingDiagram = {
  schema_version: string;
  type: string;
  title: string;
  summary: string;
  source: string;
  unit?: string;
  nodes: DiagramNode[];
  edges: DiagramEdge[];
  items: DiagramItem[];
  groups: DiagramGroup[];
  rows: string[];
  columns: string[];
  values: (string | number | null)[][];
  series: DiagramSeries[];
  axes: string[];
  sets: { label: string; items: string[] }[];
  universe?: string[];
  scale?: number[];
  x_domain?: number[];
  y_domain?: number[];
  x_label?: string;
  y_label?: string;
  start?: number;
  hub?: string;
  effect?: string;
  before?: { nodes: DiagramNode[]; edges: DiagramEdge[] };
  after?: { nodes: DiagramNode[]; edges: DiagramEdge[] };
  vectors?: { label: string; from: number[]; to: number[] }[];
  steps?: { label: string; operation: string; values: (number | string)[][] }[];
};
export type DiagramScene = { width: number; height: number; body: string };

const record = (v: unknown): Record<string, unknown> => {
  if (!v || typeof v !== "object" || Array.isArray(v))
    throw new Error("Expected an object / 需要对象");
  return v as Record<string, unknown>;
};
const string = (v: unknown, max = 1000): string => {
  if (typeof v !== "string" || !v.trim() || v.length > max)
    throw new Error("Missing or overlong text / 文字缺失或过长");
  return v;
};
const number = (v: unknown): number => {
  if (typeof v !== "number" || !Number.isFinite(v) || Math.abs(v) > 1e100)
    throw new Error(
      "A bounded finite number is required / 需要合理范围的有限数值",
    );
  return v;
};
const array = (v: unknown, max = 32): unknown[] => {
  if (!Array.isArray(v) || v.length > max)
    throw new Error("Invalid collection size / 数据数量不合适");
  return v;
};
const strings = (v: unknown, max = 32): string[] =>
  array(v, max).map((x) => string(x, 300));
const nodes = (v: unknown): DiagramNode[] =>
  array(v, 24).map((raw) => {
    const r = record(raw),
      n: DiagramNode = { id: string(r.id, 80), label: string(r.label, 300) };
    for (const key of [
      "detail",
      "parent",
      "group",
      "kind",
      "status",
      "row",
    ] as const)
      if (r[key]! !== undefined) n[key]! = string(r[key]!);
    for (const key of ["x", "y"] as const)
      if (r[key]! !== undefined) n[key]! = number(r[key]!);
    return n;
  });
const edges = (v: unknown): DiagramEdge[] =>
  array(v, 48).map((raw) => {
    const r = record(raw),
      e: DiagramEdge = { from: string(r.from, 80), to: string(r.to, 80) };
    if (r.label !== undefined) e.label = string(r.label, 500);
    if (r.kind !== undefined) e.kind = string(r.kind, 40);
    if (r.value !== undefined) e.value = number(r.value);
    return e;
  });
const items = (v: unknown): DiagramItem[] =>
  array(v).map((raw) => {
    const r = record(raw),
      i: DiagramItem = { label: string(r.label, 300) };
    for (const key of ["id", "detail", "parent", "group"] as const)
      if (r[key]! !== undefined) i[key]! = string(r[key]!);
    for (const key of [
      "value",
      "x",
      "y",
      "width",
      "height",
      "depth",
      "start",
      "end",
    ] as const)
      if (r[key]! !== undefined) i[key]! = number(r[key]!);
    return i;
  });
const need = (ok: unknown, message: string) => {
  if (!ok) throw new Error(message);
};
const unique = (ids: string[]) =>
  need(new Set(ids).size === ids.length, "Duplicate identity / 身份重复");
const graphCheck = (ns: DiagramNode[], es: DiagramEdge[]) => {
  need(ns.length > 0, "Missing nodes / 缺少节点");
  unique(ns.map((n) => n.id));
  const ids = new Set(ns.map((n) => n.id));
  for (const e of es)
    need(
      ids.has(e.from) && ids.has(e.to),
      "Unknown edge endpoint / 连线端点不存在",
    );
};
export function diagramRanks(ns: DiagramNode[], es: DiagramEdge[]): number[] {
  const ranks = ns.map(() => 0),
    degrees = ns.map((n) => es.filter((e) => e.to === n.id).length);
  const queue = ns.map((_, i) => i).filter((i) => !degrees[i]!);
  let visited = 0;
  while (queue.length) {
    const i = queue.shift()!;
    visited++;
    for (const e of es.filter((e) => e.from === ns[i]!.id)) {
      const j = ns.findIndex((n) => n.id === e.to);
      ranks[j]! = Math.max(ranks[j]!, ranks[i]! + 1);
      if (--degrees[j]! === 0) queue.push(j);
    }
  }
  return visited === ns.length ? ranks : [];
}
export function parseTeachingDiagram(raw: string): TeachingDiagram {
  need(raw.length <= 65000, "Diagram too large / 图表过大");
  const r = record(JSON.parse(raw));
  need(
    r.schema_version === catalog.schema_version,
    "Unsupported version / 图表版本不支持",
  );
  const type = string(r.type, 80),
    entry = catalog.types.find((t) => t.id === type);
  need(entry, "Unsupported diagram type / 图型不支持");
  const d: TeachingDiagram = {
    schema_version: catalog.schema_version,
    type,
    title: string(r.title, 300),
    summary: string(r.summary, 5000),
    source: string(r.source, 2000),
    nodes: r.nodes === undefined ? [] : nodes(r.nodes),
    edges: r.edges === undefined ? [] : edges(r.edges),
    items: r.items === undefined ? [] : items(r.items),
    groups:
      r.groups === undefined
        ? []
        : array(r.groups, 12).map((raw) => {
            const g = record(raw);
            return {
              id: string(g.id, 80),
              label: string(g.label, 300),
              ...(g.limit === undefined ? {} : { limit: number(g.limit) }),
            };
          }),
    rows: r.rows === undefined ? [] : strings(r.rows, 16),
    columns: r.columns === undefined ? [] : strings(r.columns, 16),
    axes: r.axes === undefined ? [] : strings(r.axes, 8),
    values:
      r.values === undefined
        ? []
        : array(r.values, 16).map((row) =>
            array(row, 16).map((x) =>
              x === null
                ? null
                : typeof x === "string"
                  ? string(x, 300)
                  : number(x),
            ),
          ),
    series:
      r.series === undefined
        ? []
        : array(r.series, 8).map((raw) => {
            const s = record(raw);
            return {
              label: string(s.label, 300),
              ...(s.values === undefined
                ? {}
                : { values: array(s.values, 8).map(number) }),
              ...(s.points === undefined
                ? {}
                : {
                    points: array(s.points).map((raw) => {
                      const p = record(raw);
                      return {
                        x: number(p.x),
                        y: p.y === null ? null : number(p.y),
                        ...(p.label === undefined
                          ? {}
                          : { label: string(p.label, 300) }),
                      };
                    }),
                  }),
            };
          }),
    sets:
      r.sets === undefined
        ? []
        : array(r.sets, 3).map((raw) => {
            const s = record(raw);
            return { label: string(s.label, 300), items: strings(s.items) };
          }),
  };
  for (const key of ["unit", "hub", "effect", "x_label", "y_label"] as const)
    if (r[key]! !== undefined) d[key]! = string(r[key]!, 500);
  for (const key of ["scale", "x_domain", "y_domain"] as const)
    if (r[key]! !== undefined) {
      const domain = array(r[key]!, 2).map(number);
      need(
        domain.length === 2 && domain[1]! > domain[0]!,
        "Invalid scale / 尺度范围不成立",
      );
      d[key]! = domain;
    }
  if (r.start !== undefined) d.start = number(r.start);
  if (r.universe !== undefined) d.universe = strings(r.universe, 96);
  for (const key of ["before", "after"] as const)
    if (r[key]! !== undefined) {
      const g = record(r[key]!);
      d[key]! = { nodes: nodes(g.nodes), edges: edges(g.edges || []) };
      graphCheck(d[key]!.nodes, d[key]!.edges);
    }
  unique(d.groups.map((g) => g.id));
  unique(d.rows);
  unique(d.columns);
  const family = entry!.family;
  if (family === 'vectors') {
    d.vectors = array(r.vectors, 8).map(raw => {
      const v = record(raw), from = array(v.from, 2).map(number), to = array(v.to, 2).map(number);
      need(from.length === 2 && to.length === 2 && [...from, ...to].every(x => Math.abs(x) <= 1e6), 'Need bounded 2D coordinates / 需要有限二维坐标');
      return { label: string(v.label, 240), from, to };
    });
    need(d.vectors.length, 'Missing vectors / 缺少向量');
  }
  if (family === 'matrix_steps') {
    d.steps = array(r.steps, 6).map(raw => {
      const s = record(raw), values = array(s.values, 6).map(row => array(row, 6).map(v => typeof v === 'number' ? number(v) : string(v, 20)));
      need(values.length && values[0]!.length && values.every(row => row.length === values[0]!.length), 'Matrix dimensions disagree / 矩阵行列不一致');
      need(values.flat().every(v => typeof v !== 'string' || !/[\\\n]/.test(v)), 'Use plain matrix values / 矩阵元素使用短纯文本');
      return { label: string(s.label, 240), operation: s.operation === undefined ? '' : string(s.operation, 240), values };
    });
    need(d.steps.length && d.steps.every(s => s.values.length === d.steps![0]!.values.length && s.values[0]!.length === d.steps![0]!.values[0]!.length), 'Steps need matching matrices / 各步矩阵维度需要一致');
  }
  if (
    [
      "graph",
      "flow",
      "tree",
      "entity",
      "sequence",
      "loop",
      "process",
      "grouped",
      "swimlane",
      "wardley",
      "sankey",
    ].includes(family)
  )
    graphCheck(d.nodes, d.edges);
  if (["tree", "nested"].includes(family)) {
    graphCheck(d.nodes, d.edges);
    for (const n of d.nodes)
      if (n.parent) {
        need(
          d.nodes.some((p) => p.id === n.parent),
          "Unknown parent / 父节点不存在",
        );
        if (!d.edges.some((e) => e.from === n.parent && e.to === n.id))
          d.edges.push({ from: n.parent, to: n.id });
      }
    need(
      d.edges.every(
        (e) => d.edges.filter((other) => other.to === e.to).length === 1,
      ),
      "A tree needs one parent / 层级图需要单父关系",
    );
    need(
      diagramRanks(d.nodes, d.edges).length,
      "Containment cannot have cycles / 包含关系不能成环",
    );
  }
  if (family === "delta")
    need(d.before && d.after, "Both snapshots required / 需要前后快照");
  if (family === "flow")
    for (const n of d.nodes.filter((n) => n.kind === "decision")) {
      const outgoing = d.edges.filter((e) => e.from === n.id);
      need(
        outgoing.length >= 2 && outgoing.every((e) => e.label),
        "Decision exits need conditions / 判断出口需要条件",
      );
    }
  if (family === "loop") {
    need(
      d.hub && d.nodes.length >= 2,
      "Loop needs an accumulating hub / 循环需要共同汇总状态",
    );
    const remaining = new Set(d.nodes.map((n) => n.id));
    let current = d.nodes[0]!.id;
    for (let i = 0; i < d.nodes.length; i++) {
      need(
        remaining.delete(current),
        "Loop must visit each step / 循环步骤不连贯",
      );
      const out = d.edges.filter((e) => e.from === current);
      need(out.length === 1, "Loop needs one next step / 循环步骤需要唯一后继");
      current = out[0]!.to;
    }
    need(
      !remaining.size && current === d.nodes[0]!.id,
      "Loop must return to start / 循环须返回起点",
    );
  }
  if (["grouped", "swimlane", "kanban", "story"].includes(family)) {
    need(
      d.groups.length && d.nodes.length,
      "Missing groups or steps / 缺少分组或步骤",
    );
    unique(d.nodes.map((n) => n.id));
    for (const n of d.nodes)
      need(
        d.groups.some((g) => g.id === n.group),
        "Unknown group / 节点分组不存在",
      );
  }
  if (family === "kanban")
    need(
      d.groups.every(
        (g) =>
          g.limit === undefined || (g.limit >= 0 && Number.isInteger(g.limit)),
      ),
      "WIP must be a nonnegative integer / WIP 需要非负整数",
    );
  if (family === "story") {
    need(d.rows.length, "Missing release rows / 缺少发布批次");
    for (const n of d.nodes)
      need(d.rows.includes(n.row || ""), "Unknown release / 发布批次不存在");
  }
  if (family === "matrix") {
    need(
      d.rows.length &&
        d.columns.length &&
        d.values.length === d.rows.length &&
        d.values.every((row) => row.length === d.columns.length),
      "Matrix dimensions disagree / 矩阵行列不一致",
    );
    if (type === "heatmap") {
      need(d.unit, "Unit required / 需要单位");
      need(
        d.values.flat().every((v) => v === null || typeof v === "number"),
        "Heatmap requires numeric values / 热力图需要数值",
      );
    }
  }
  if (
    [
      "layers",
      "exploded",
      "plan",
      "timeline",
      "gantt",
      "pyramid",
      "bar",
      "waterfall",
      "treemap",
      "polar",
      "journey",
      "scatter",
    ].includes(family)
  )
    need(d.items.length, "Missing data items / 缺少数据项");
  if (
    [
      "timeline",
      "gantt",
      "pyramid",
      "bar",
      "waterfall",
      "treemap",
      "polar",
      "radar",
      "line",
      "scatter",
      "sankey",
      "journey",
      "exploded",
      "plan",
    ].includes(family)
  )
    need(
      d.unit || ["quadrant"].includes(type),
      "Unit or common scale required / 需要单位或共同量规",
    );
  if (
    [
      "timeline",
      "pyramid",
      "bar",
      "waterfall",
      "treemap",
      "polar",
      "journey",
    ].includes(family)
  )
    d.items.forEach((i) => number(i.value));
  if (["pyramid", "polar", "treemap"].includes(family))
    need(
      d.items.every((i) => i.value! >= 0) && d.items.some((i) => i.value! > 0),
      "Positive total required / 总量需要大于零",
    );
  if (family === "pyramid")
    need(
      d.items.every(
        (i, index) => !index || i.value! <= d.items[index - 1]!.value!,
      ),
      "Funnel stages must not grow / 漏斗阶段不能递增",
    );
  if (family === "waterfall") number(d.start);
  if (family === "gantt")
    d.items.forEach((i) =>
      need(
        number(i.end) >= number(i.start),
        "Task end precedes start / 任务结束早于开始",
      ),
    );
  if (["scatter", "plan"].includes(family))
    d.items.forEach((i) => {
      number(i.x);
      number(i.y);
    });
  if (type === "quadrant")
    need(
      d.x_domain && d.y_domain && d.x_label && d.y_label,
      "Quadrant needs axes and domains / 象限需要双轴和范围",
    );
  if (["scatter", "line", "wardley"].includes(family))
    need(d.x_label && d.y_label, "Axis labels required / 需要轴含义");
  if (family === "wardley")
    d.nodes.forEach((n) =>
      need(
        n.x !== undefined &&
          n.y !== undefined &&
          n.x >= 0 &&
          n.x <= 1 &&
          n.y >= 0 &&
          n.y <= 1,
        "Wardley coordinates must be in 0..1 / 演化坐标需在0..1内",
      ),
    );
  if (["exploded", "plan"].includes(family))
    d.items.forEach((i) => {
      for (const k of (family === "exploded"
        ? ["width", "height", "depth"]
        : ["width", "height"]) as ("width" | "height" | "depth")[])
        need(
          number(i[k]!) > 0,
          "Spatial dimensions must be positive / 空间尺寸须为正数",
        );
    });
  if (family === "line") {
    need(d.series.length, "Missing series / 缺少序列");
    for (const s of d.series) {
      need(s.points?.length, "Missing points / 缺少数据点");
      need(
        s.points!.every((p, i) => !i || p.x > s.points![i - 1]!.x),
        "Line x values must increase / 折线横坐标须递增",
      );
      need(
        s.points!.some((p) => p.y !== null),
        "No observed values / 没有实测值",
      );
    }
  }
  if (family === "radar") {
    unique(d.axes);
    need(
      d.axes.length >= 3 && d.scale && d.scale[0]! === 0 && d.series.length,
      "Radar needs axes and a common zero scale / 雷达需要维度及共同零起点量规",
    );
    for (const s of d.series)
      need(
        s.values?.length === d.axes.length &&
          s.values.every((v) => v >= 0 && v <= d.scale![1]!),
        "Radar values exceed the scale / 雷达数值与量规不一致",
      );
  }
  if (family === "venn") {
    need(d.sets.length >= 2, "Venn needs 2–3 sets / 交集图需要2–3个集合");
    unique(d.sets.map((s) => s.label));
    if (d.universe) unique(d.universe);
    for (const s of d.sets) {
      unique(s.items);
      if (d.universe)
        need(
          s.items.every((i) => d.universe!.includes(i)),
          "Member outside universe / 成员超出全集",
        );
    }
  }
  if (family === "fishbone") {
    need(
      d.effect && d.groups.length && d.items.length,
      "Missing effect or causes / 缺少结果或原因",
    );
    d.items.forEach((i) =>
      need(
        d.groups.some((g) => g.id === i.group),
        "Unknown cause group / 原因分组不存在",
      ),
    );
  }
  if (family === "treemap") {
    need(
      d.items.every((i) => i.value! > 0 && (!i.parent || i.id)),
      "Parts need positive values and child identities / 部分需要正数值及子项身份",
    );
    unique(d.items.map((i, index) => i.id || String(index)));
    for (const i of d.items.filter((i) => i.parent))
      need(
        d.items.some((p) => p.id === i.parent),
        "Unknown part parent / 部分的父节点不存在",
      );
    const ns = d.items.map((i, index) => ({
      id: i.id || String(index),
      label: i.label,
    }));
    const es = d.items
      .filter((i) => i.parent)
      .map((i) => ({ from: i.parent!, to: i.id! }));
    graphCheck(ns, es);
    need(
      diagramRanks(ns, es).length,
      "Part hierarchy cannot cycle / 部分层级不能成环",
    );
    for (const i of d.items) {
      const children = d.items.filter((c) => c.parent === i.id && i.id);
      if (children.length)
        need(
          Math.abs(children.reduce((sum, c) => sum + c.value!, 0) - i.value!) <=
            Math.max(1, i.value!) * 1e-8,
          "Parts do not sum to parent / 子项之和与父项不一致",
        );
    }
  }
  if (family === "sankey") {
    need(
      diagramRanks(d.nodes, d.edges).length,
      "Sankey must be acyclic / 桑基流量不能成环",
    );
    d.edges.forEach((e) =>
      need(number(e.value) > 0, "Flow must be positive / 流量须为正数"),
    );
    for (const n of d.nodes) {
      const incoming = d.edges.filter((e) => e.to === n.id),
        outgoing = d.edges.filter((e) => e.from === n.id);
      const total = (es: DiagramEdge[]) =>
        es.reduce((sum, e) => sum + e.value!, 0);
      if (incoming.length && outgoing.length)
        need(
          Math.abs(total(incoming) - total(outgoing)) <=
            Math.max(1, total(incoming)) * 1e-8,
          "Flow is not conserved / 中间节点流量不守恒",
        );
    }
  }
  const points =
    family === "line"
      ? d.series.flatMap((s) => s.points || [])
      : family === "scatter"
        ? d.items
        : [];
  for (const p of points) {
    if (d.x_domain)
      need(
        p.x! >= d.x_domain[0]! && p.x! <= d.x_domain[1]!,
        "Point outside x domain / 数据点超出横轴范围",
      );
    if (d.y_domain && p.y !== null)
      need(
        p.y! >= d.y_domain[0]! && p.y! <= d.y_domain[1]!,
        "Point outside y domain / 数据点超出纵轴范围",
      );
  }
  return d;
}

export const escapeDiagramText = (s: unknown) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ]!,
  );
const e = escapeDiagramText;
const colors = [
  "#4338ca",
  "#126d9b",
  "#17815a",
  "#9a531d",
  "#6e4a9c",
  "#a64355",
  "#64748b",
  "#0d9488",
];
export function diagramTextLines(value: string, width = 200): string[] {
  const result: string[] = [];
  for (const paragraph of value.split("\n")) {
    let line = "",
      used = 0;
    for (const token of paragraph.match(/[^\x00-\xff]|[a-zA-Z0-9_]+|\s+|./g) ||
      []) {
      const size = [...token].reduce(
        (sum, char) => sum + (/[^\x00-\xff]/.test(char) ? 16 : 8),
        0,
      );
      if (used + size > width && line) {
        result.push(line);
        line = "";
        used = 0;
      }
      if (size > width) {
        for (const char of token) {
          if (used + 8 > width && line) {
            result.push(line);
            line = "";
            used = 0;
          }
          line += char;
          used += 8;
        }
      } else {
        line += token;
        used += size;
      }
    }
    result.push(line);
  }
  return result;
}
const txt = (
  x: number,
  y: number,
  value: unknown,
  width = 200,
  anchor = "middle",
  color = "#172033",
) =>
  `<text x="${x}" y="${y}" fill="${color}" text-anchor="${anchor}" font-size="16">${diagramTextLines(
    String(value ?? ""),
    width,
  )
    .map((line, i) => `<tspan x="${x}" dy="${i ? 21 : 0}">${e(line)}</tspan>`)
    .join("")}</text>`;
const rect = (
  x: number,
  y: number,
  w: number,
  h: number,
  fill = "#fff",
  stroke = "#94a3b8",
) =>
  `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="3" fill="${fill}" stroke="${stroke}"/>`;
const path = (d: string, color = "#64748b", width = 1.7, marker = "") =>
  `<path d="${d}" fill="none" stroke="${color}" stroke-width="${width}"${marker ? ` marker-end="url(#${marker})"` : ""}/>`;
const line = (
  x: number,
  y: number,
  x2: number,
  y2: number,
  color = "#e2e8f0",
) => path(`M${x} ${y} L${x2} ${y2}`, color);
const label = (x: number, y: number, text: string, width = 160) => {
  const ls = diagramTextLines(text, width);
  const actual = Math.max(
    ...ls.map((line) =>
      [...line].reduce(
        (sum, char) => sum + (/[^\x00-\xff]/.test(char) ? 16 : 8),
        0,
      ),
    ),
  );
  return (
    rect(
      x - actual / 2 - 4,
      y - 17,
      actual + 8,
      ls.length * 21 + 4,
      "#fff",
      "#fff",
    ) + txt(x, y, text, width)
  );
};
type Box = { x: number; y: number; w: number; h: number };
const nodeHeight = (n: DiagramNode, width = 216) => {
  const textWidth = n.kind === 'decision' ? (width + 24) / 2 : width;
  const height = 30 + (diagramTextLines(n.label, textWidth).length +
    (n.detail ? diagramTextLines(n.detail, textWidth).length + 1 : 0)) * 21;
  return n.kind === 'decision' ? height * 2 : height;
};
const boxNode = (n: DiagramNode, b: Box, focal = false) => {
  const headingHeight = diagramTextLines(n.label, b.w - 24).length * 21;
  const shape =
    n.kind === "decision"
      ? `<polygon points="${b.x + b.w / 2},${b.y - 16} ${b.x + b.w + 16},${b.y + b.h / 2} ${b.x + b.w / 2},${b.y + b.h + 16} ${b.x - 16},${b.y + b.h / 2}" fill="#eef2ff" stroke="#4338ca"/>`
      : rect(
          b.x,
          b.y,
          b.w,
          b.h,
          focal ? "#eef2ff" : "#fff",
          focal ? "#4338ca" : "#94a3b8",
        );
  if (n.kind === 'decision') {
    // Text stays inside the diamond's central rectangle, rather than using
    // the full width near its narrow top and bottom corners.
    const width = b.w / 2, heading = diagramTextLines(n.label, width).length * 21;
    const total = heading + (n.detail ? 21 + diagramTextLines(n.detail, width).length * 21 : 0);
    const x = b.x + b.w / 2, y = b.y + b.h / 2 - total / 2 + 16;
    return `<g data-node-id="${e(n.id)}">${shape}${txt(x, y, n.label, width)}${n.detail ? line(x - width / 2, y + heading - 7, x + width / 2, y + heading - 7) + txt(x, y + heading + 21, n.detail, width, 'middle', '#475569') : ''}</g>`;
  }
  return `<g data-node-id="${e(n.id)}">${shape}${txt(b.x + b.w / 2, b.y + 25, n.label, b.w - 24)}${n.detail ? line(b.x, b.y + headingHeight + 17, b.x + b.w, b.y + headingHeight + 17) + txt(b.x + 12, b.y + headingHeight + 39, n.detail, b.w - 24, "start", "#475569") : ""}</g>`;
};
const connect = (
  a: Box,
  b: Box,
  edge: DiagramEdge,
  marker: string,
  index: number,
  outerX?: number,
) => {
  let d: string, x: number, y: number;
  if (b.y > a.y + a.h) {
    const sx = a.x + a.w / 2,
      tx = b.x + b.w / 2,
      mid = (a.y + a.h + b.y) / 2;
    d = `M${sx} ${a.y + a.h} V${mid} H${tx} V${b.y}`;
    x = (sx + tx) / 2;
    y = mid - 7;
  } else if (
    Math.abs(a.y - b.y) < 1 &&
    b.x > a.x + a.w &&
    b.x - a.x - a.w <= 120
  ) {
    d = `M${a.x + a.w} ${a.y + a.h / 2} H${b.x}`;
    x = (a.x + a.w + b.x) / 2;
    y = a.y + a.h / 2 - 12;
  } else if (Math.abs(a.y - b.y) < 1) {
    const bottom = Math.max(a.y + a.h, b.y + b.h) + 45 + index * 30;
    d = `M${a.x + a.w / 2} ${a.y + a.h} V${bottom} H${b.x + b.w / 2} V${b.y + b.h}`;
    x = (a.x + b.x + a.w / 2 + b.w / 2) / 2;
    y = bottom - 9;
  } else {
    const right = (outerX ?? Math.max(a.x + a.w, b.x + b.w)) + 24 + index * 14;
    d = `M${a.x + a.w} ${a.y + a.h / 2} H${right} V${b.y + b.h / 2} H${b.x + b.w}`;
    x = right;
    y = (a.y + b.y) / 2 - 7;
  }
  const color = edge.kind === "return" ? "#94a3b8" : "#64748b";
  const actualMarker =
    edge.kind === "inheritance"
      ? `${marker}-inheritance`
      : edge.kind === "composition"
        ? `${marker}-composition`
        : marker;
  return `<g data-from="${e(edge.from)}" data-to="${e(edge.to)}">${path(d, color, 1.7, actualMarker)}${edge.label ? label(x, y, edge.label) : ""}</g>`;
};

function graphScene(d: TeachingDiagram, marker: string): DiagramScene {
  // Back edges still render, but should not collapse an algorithm with a
  // repeat step into an arbitrary input-order grid. Lay out its forward DAG.
  const colors = new Map<string, number>(),
    forward: DiagramEdge[] = [];
  const visit = (id: string) => {
    colors.set(id, 1);
    for (const edge of d.edges.filter((e) => e.from === id)) {
      if (colors.get(edge.to) === 1) continue;
      forward.push(edge);
      if (!colors.has(edge.to)) visit(edge.to);
    }
    colors.set(id, 2);
  };
  const roots = d.nodes.filter((n) => !d.edges.some((e) => e.to === n.id));
  for (const n of [...roots, ...d.nodes]) if (!colors.has(n.id)) visit(n.id);
  const levels = diagramRanks(d.nodes, forward),
    cyclic = forward.length !== d.edges.length;
  const counts = levels.map(
    (level) => levels.filter((r) => r === level).length,
  );
  const width = Math.max(
    900,
    Math.max(...counts) * 280 + 160 + d.edges.length * 14,
  );
  const rowHeight =
    Math.max(80, ...d.nodes.map((n) => nodeHeight(n))) +
    Math.max(
      135,
      ...d.edges.map(
        (edge) => diagramTextLines(edge.label || "", 160).length * 21 + 60,
      ),
    );
  const height =
    (Math.max(...levels) + 1) * rowHeight +
    90 +
    (cyclic ? d.edges.length * 30 : 0);
  const boxes = d.nodes.map((n, i) => {
    const same = levels
      .map((r, j) => (r === levels[i]! ? j : -1))
      .filter((j) => j >= 0);
    return {
      x: 60 + same.indexOf(i) * 280,
      y: 50 + levels[i]! * rowHeight,
      w: 240,
      h: Math.max(70, nodeHeight(n)),
    };
  });
  const ports = boxes.map((box, i) =>
    d.nodes[i]!.kind === "decision"
      ? { x: box.x - 16, y: box.y - 16, w: box.w + 32, h: box.h + 32 }
      : box,
  );
  const outerX = Math.max(...ports.map((box) => box.x + box.w));
  const edgeSvg = d.edges
    .map((edge, i) =>
      connect(
        ports[d.nodes.findIndex((n) => n.id === edge.from)]!,
        ports[d.nodes.findIndex((n) => n.id === edge.to)]!,
        edge,
        marker,
        i,
        outerX,
      ),
    )
    .join("");
  return {
    width,
    height,
    body:
      edgeSvg + d.nodes.map((n, i) => boxNode(n, boxes[i]!, i === 0)).join(""),
  };
}

function groupedScene(
  d: TeachingDiagram,
  marker: string,
  sequential = false,
): DiagramScene {
  const columnWidth = 286,
    width = Math.max(900, d.groups.length * columnWidth + 80);
  const displayNodes = d.nodes.map((n) => ({
    ...n,
    detail: [n.detail, n.status].filter(Boolean).join("\n") || undefined,
  }));
  const cardHeight = Math.max(72, ...displayNodes.map((n) => nodeHeight(n)));
  const grouped = d.groups.map((g) => d.nodes.filter((n) => n.group === g.id));
  const rowCount = sequential
    ? d.nodes.length
    : Math.max(...grouped.map((ns) => ns.length));
  const headerHeight =
    Math.max(...d.groups.map((g) => diagramTextLines(g.label, 230).length)) *
      21 +
    (d.groups.some((g) => g.limit !== undefined) ? 74 : 40);
  const height = headerHeight + rowCount * (cardHeight + 95) + 70;
  const boxes = d.nodes.map((n, i) => ({
    x: 50 + d.groups.findIndex((g) => g.id === n.group) * columnWidth,
    y:
      headerHeight +
      30 +
      (sequential
        ? i
        : grouped[d.groups.findIndex((g) => g.id === n.group)]!.indexOf(n)) *
        (cardHeight + 95),
    w: 236,
    h: cardHeight,
  }));
  let body = d.groups
    .map(
      (g, i) =>
        rect(
          30 + i * columnWidth,
          20,
          columnWidth - 14,
          height - 40,
          i % 2 ? "#fafbfd" : "#f8fafc",
        ) +
        txt(168 + i * columnWidth, 47, g.label, 230) +
        (g.limit === undefined
          ? ""
          : txt(
              168 + i * columnWidth,
              headerHeight - 3,
              `${grouped[i]!.length}/${g.limit} WIP`,
              230,
              "middle",
              grouped[i]!.length > g.limit ? "#a64355" : "#475569",
            )),
    )
    .join("");
  body += d.edges
    .map((edge, i) =>
      connect(
        boxes[d.nodes.findIndex((n) => n.id === edge.from)]!,
        boxes[d.nodes.findIndex((n) => n.id === edge.to)]!,
        edge,
        marker,
        i,
      ),
    )
    .join("");
  body += displayNodes.map((n, i) => boxNode(n, boxes[i]!)).join("");
  return { width, height, body };
}

const extent = (values: number[], zero = false): [number, number] => {
  let lo = Math.min(...values),
    hi = Math.max(...values);
  if (zero) {
    lo = Math.min(0, lo);
    hi = Math.max(0, hi);
  }
  if (lo === hi) {
    const padding = Math.max(1, Math.abs(lo) * 0.1);
    lo -= padding;
    hi += padding;
  }
  return [lo, hi];
};
const map = (v: number, domain: number[], a: number, b: number) =>
  a + ((v - domain[0]!) / (domain[1]! - domain[0]!)) * (b - a);
const fmt = (v: number) => Number(v.toPrecision(6)).toString();

export function teachingDiagramSvg(d: TeachingDiagram, id: string): string {
  const marker = `td-${id.replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const scene = buildTeachingDiagramScene(d, marker);
  return `<svg class="teaching-diagram-svg" xmlns="http://www.w3.org/2000/svg" width="${scene.width}" height="${scene.height}" viewBox="0 0 ${scene.width} ${scene.height}" role="img" aria-labelledby="${marker}-title ${marker}-desc"><title id="${marker}-title">${e(d.title)}</title><desc id="${marker}-desc">${e(d.summary + "\n" + d.source)}</desc><style>${teachingDiagramStyle}</style><defs>${teachingDiagramMarkers(marker)}</defs>${scene.body}</svg>`;
}

export function buildTeachingDiagramScene(
  d: TeachingDiagram,
  marker = "td-arrow",
): DiagramScene {
  const family = catalog.types.find((t) => t.id === d.type)!.family;
  if (family === 'vectors') return vectorScene(d, marker);
  if (family === 'matrix_steps') return matrixStepsScene(d);
  if (["graph", "flow", "entity", "tree", "process"].includes(family))
    return graphScene(d, marker);
  if (["grouped", "kanban"].includes(family)) return groupedScene(d, marker);
  if (family === "swimlane") return groupedScene(d, marker, true);
  return specializedScene(d, family, marker);
}

function specializedScene(
  d: TeachingDiagram,
  family: string,
  marker: string,
): DiagramScene {
  if (family === "sequence") {
    const width = Math.max(900, d.nodes.length * 270 + 100),
      headHeight = Math.max(70, ...d.nodes.map((n) => nodeHeight(n)));
    const messageHeights = d.edges.map((edge) =>
      Math.max(
        85,
        diagramTextLines(edge.label || `${edge.from} → ${edge.to}`, 230)
          .length *
          21 +
          50,
      ),
    );
    const height = headHeight + messageHeights.reduce((a, b) => a + b, 0) + 100;
    const x = (id: string) => 160 + d.nodes.findIndex((n) => n.id === id) * 270;
    let body = d.nodes
        .map(
          (n) =>
            boxNode(n, { x: x(n.id) - 110, y: 25, w: 220, h: headHeight }) +
            `<path d="M${x(n.id)} ${headHeight + 25} V${height - 30}" stroke="#94a3b8" stroke-dasharray="6 6" fill="none"/>`,
        )
        .join(""),
      y = headHeight + 75;
    d.edges.forEach((edge, i) => {
      const from = x(edge.from),
        to = x(edge.to),
        self = from === to;
      body += `<g data-from="${e(edge.from)}" data-to="${e(edge.to)}"${edge.kind === "return" ? ' stroke-dasharray="5 5"' : ""}>${path(self ? `M${from} ${y} h85 v35 h-85` : `M${from} ${y} H${to}`, "#64748b", 1.7, marker)}</g>`;
      body += label(
        self ? from + 100 : (from + to) / 2,
        y - 12,
        `${i + 1}. ${edge.label || `${edge.from} → ${edge.to}`}`,
        230,
      );
      y += messageHeights[i]!;
    });
    return { width, height, body };
  }
  if (family === "delta") {
    const ns = [
      ...d.before!.nodes,
      ...d.after!.nodes.filter(
        (n) => !d.before!.nodes.some((b) => b.id === n.id),
      ),
    ];
    const allEdges = [
      ...d.before!.edges,
      ...d.after!.edges.filter(
        (edge) =>
          !d.before!.edges.some(
            (b) => b.from === edge.from && b.to === edge.to,
          ),
      ),
    ];
    const ranks = diagramRanks(ns, allEdges),
      levels = ranks.length ? ranks : ns.map((_, i) => Math.floor(i / 3));
    const w = Math.max(
        900,
        Math.max(
          ...levels.map((level) => levels.filter((r) => r === level).length),
        ) *
          290 +
          170 +
          allEdges.length * 14,
      ),
      cardHeight = Math.max(
        80,
        ...[...d.before!.nodes, ...d.after!.nodes].map((n) => nodeHeight(n)),
      );
    const h =
      (Math.max(...levels) + 1) * (cardHeight + 140) +
      120 +
      allEdges.length * 30;
    const boxes = ns.map((_, i) => {
      const peers = ns
        .map((_, j) => j)
        .filter((j) => levels[j]! === levels[i]!);
      return {
        x: 50 + peers.indexOf(i) * 290,
        y: 90 + levels[i]! * (cardHeight + 140),
        w: 240,
        h: cardHeight,
      };
    });
    const snapshot = (
      part: NonNullable<TeachingDiagram["before"]>,
      offset: number,
      title: string,
    ) =>
      `<g transform="translate(${offset},0)">${rect(10, 10, w - 20, h - 20, "#fafbfd")}${txt(w / 2, 45, title)}${part.edges.map((edge, i) => connect(boxes[ns.findIndex((n) => n.id === edge.from)]!, boxes[ns.findIndex((n) => n.id === edge.to)]!, edge, marker, i)).join("")}${part.nodes.map((n) => boxNode(n, boxes[ns.findIndex((u) => u.id === n.id)]!, !d.before!.nodes.some((b) => b.id === n.id))).join("")}</g>`;
    return {
      width: w * 2,
      height: h,
      body:
        snapshot(d.before!, 0, "Before / 之前") +
        snapshot(d.after!, w, "After / 之后"),
    };
  }
  if (family === "layers") {
    const heights = d.items.map((i) =>
      Math.max(
        75,
        35 +
          diagramTextLines(i.label + (i.detail ? "\n" + i.detail : ""), 720)
            .length *
            21,
      ),
    );
    let y = 25,
      body = "";
    d.items.forEach((item, index) => {
      const h = heights[index]!;
      body +=
        rect(80, y, 740, h, index % 2 ? "#eef2ff" : "#f8fafc") +
        txt(110, y + 27, `${index + 1}`, 30) +
        txt(
          465,
          y + 27,
          item.label + (item.detail ? "\n" + item.detail : ""),
          650,
        );
      y += h + 30;
    });
    return { width: 900, height: y + 15, body };
  }
  if (family === "nested") {
    const children = (id?: string) =>
      d.nodes.filter((n) =>
        id
          ? d.edges.some((edge) => edge.from === id && edge.to === n.id)
          : !d.edges.some((edge) => edge.to === n.id),
      );
    const depth = (n: DiagramNode): number =>
      1 + Math.max(0, ...children(n.id).map(depth));
    const width = Math.max(900, ...children().map((n) => depth(n) * 58 + 360));
    const size = (n: DiagramNode): number =>
      60 +
      nodeHeight(n, width - depth(n) * 58 - 100) +
      children(n.id).reduce((sum, c) => sum + size(c) + 12, 0);
    const draw = (
      n: DiagramNode,
      x: number,
      y: number,
      w: number,
      level: number,
    ): string => {
      const heading = nodeHeight(n, w - 24),
        height = size(n);
      let body =
        rect(x, y, w, height, level % 2 ? "#eef2ff" : "#f8fafc") +
        txt(
          x + 14,
          y + 27,
          n.label + (n.detail ? "\n" + n.detail : ""),
          w - 28,
          "start",
        );
      let nextY = y + heading + 25;
      for (const child of children(n.id)) {
        body += draw(child, x + 24, nextY, w - 48, level + 1);
        nextY += size(child) + 12;
      }
      return body;
    };
    let y = 20,
      body = "";
    children().forEach((n) => {
      body += draw(n, 25, y, width - 50, 0);
      y += size(n) + 20;
    });
    return { width, height: y + 10, body };
  }
  if (family === "loop") {
    const ns: DiagramNode[] = [];
    let id = d.nodes[0]!.id;
    for (let i = 0; i < d.nodes.length; i++) {
      ns.push(d.nodes.find((n) => n.id === id)!);
      id = d.edges.find((edge) => edge.from === id)!.to;
    }
    const r = Math.max(330, ns.length * 75),
      width = r * 2 + 360,
      height = r * 2 + 330,
      cx = width / 2,
      cy = height / 2;
    const boxes = ns.map((n, i) => ({
      x: cx + r * Math.cos((i * 2 * Math.PI) / ns.length - Math.PI / 2) - 120,
      y:
        cy +
        r * Math.sin((i * 2 * Math.PI) / ns.length - Math.PI / 2) -
        nodeHeight(n) / 2,
      w: 240,
      h: Math.max(70, nodeHeight(n)),
    }));
    let body =
      rect(cx - 150, cy - 65, 300, 130, "#eef2ff", "#4338ca") +
      txt(cx, cy - 20, d.hub, 270);
    boxes.forEach((b, i) => {
      const next = boxes[(i + 1) % boxes.length]!;
      const sx = b.x + 120,
        sy = b.y + b.h / 2,
        tx = next.x + 120,
        ty = next.y + next.h / 2;
      const distance = Math.hypot(tx - sx, ty - sy);
      const ux = (tx - sx) / distance,
        uy = (ty - sy) / distance;
      const offset = Math.min(135, distance / 3);
      body +=
        path(
          `M${sx + ux * offset} ${sy + uy * offset} L${tx - ux * offset} ${ty - uy * offset}`,
          "#64748b",
          1.7,
          marker,
        ) + path(`M${sx} ${sy} L${cx} ${cy}`, "#cbd5e1", 1);
    });
    body += ns.map((n, i) => boxNode(n, boxes[i]!)).join("");
    return { width, height, body };
  }
  if (family === "timeline") {
    const domain = extent(d.items.map((i) => i.value!)),
      width = Math.max(900, d.items.length * 230 + 100),
      labelHeight =
        Math.max(
          ...d.items.map(
            (i) =>
              diagramTextLines(i.label + (i.detail ? "\n" + i.detail : ""), 200)
                .length,
          ),
        ) * 21;
    const spacing = labelHeight + 75,
      height = d.items.length * spacing + 120;
    let body = line(70, 55, width - 70, 55, "#64748b");
    for (let k = 0; k <= 4; k++) {
      const v = domain[0]! + ((domain[1]! - domain[0]!) * k) / 4,
        x = map(v, domain, 70, width - 70);
      body += line(x, 50, x, 60, "#64748b") + txt(x, 35, fmt(v), 100);
    }
    d.items.forEach((item, i) => {
      const x = map(item.value!, domain, 70, width - 70),
        y = 105 + i * spacing;
      body +=
        `<circle data-time="${item.value}" cx="${x}" cy="55" r="5" fill="#4338ca"/>` +
        line(x, 62, x, y - 12, "#cbd5e1") +
        label(
          Math.max(135, Math.min(width - 135, x)),
          y,
          `${item.label}\n${fmt(item.value!)} ${d.unit}${item.detail ? "\n" + item.detail : ""}`,
          220,
        );
    });
    return { width, height, body };
  }
  if (family === "bar") {
    const domain = extent(
        d.items.map((i) => i.value!),
        true,
      ),
      plot = [280, 780],
      baseline = map(0, domain, ...(plot as [number, number])),
      rowHeight = Math.max(
        62,
        ...d.items.map((i) => diagramTextLines(i.label, 220).length * 21 + 20),
      ),
      height = d.items.length * rowHeight + 150;
    let body = axesGrid(
      domain,
      [0, 1],
      280,
      30,
      500,
      height - 140,
      d.unit || "",
      "",
      true,
    );
    d.items.forEach((item, i) => {
      const endpoint = map(item.value!, domain, ...(plot as [number, number])),
        y = 35 + i * rowHeight;
      body +=
        txt(250, y + 21, item.label, 220, "end") +
        `<rect data-value="${item.value}" x="${Math.min(baseline, endpoint)}" y="${y}" width="${Math.abs(endpoint - baseline)}" height="34" fill="${colors[i % colors.length]!}"/>` +
        txt(
          item.value! >= 0 ? endpoint + 8 : endpoint - 8,
          y + 22,
          fmt(item.value!),
          110,
          item.value! >= 0 ? "start" : "end",
        );
    });
    return { width: 950, height, body };
  }
  if (family === "gantt") {
    const domain = extent(d.items.flatMap((i) => [i.start!, i.end!])),
      rowHeight = Math.max(
        65,
        ...d.items.map((i) => diagramTextLines(i.label, 220).length * 21 + 20),
      ),
      height = rowHeight * d.items.length + 150;
    let body = axesGrid(
      domain,
      [0, 1],
      290,
      30,
      560,
      height - 140,
      d.unit || "",
      "",
      true,
    );
    d.items.forEach((item, i) => {
      const x = map(item.start!, domain, 290, 850),
        x2 = map(item.end!, domain, 290, 850),
        y = 38 + i * rowHeight;
      body +=
        txt(265, y + 20, item.label, 220, "end") +
        `<rect data-start="${item.start}" data-end="${item.end}" x="${x}" y="${y}" width="${Math.max(1, x2 - x)}" height="28" fill="${colors[i % colors.length]!}"/>` +
        txt(
          (x + x2) / 2,
          y + 50,
          `${fmt(item.start!)} → ${fmt(item.end!)}`,
          200,
        );
    });
    return { width: 960, height, body };
  }
  if (family === "pyramid") {
    const max = Math.max(...d.items.map((i) => i.value!)),
      rowHeight = Math.max(
        85,
        ...d.items.map((i) => diagramTextLines(i.label, 220).length * 21 + 35),
      ),
      height = rowHeight * d.items.length + 55;
    const body = d.items
      .map((item, i) => {
        const w = (item.value! / max) * 560,
          y = 20 + i * rowHeight;
        return (
          `<rect data-value="${item.value}" x="${330 + (560 - w) / 2}" y="${y}" width="${w}" height="${rowHeight - 22}" fill="${colors[i % colors.length]!}" opacity="0.75"/>` +
          txt(
            290,
            y + 27,
            `${item.label}\n${fmt(item.value!)} ${d.unit}`,
            250,
            "end",
          )
        );
      })
      .join("");
    return { width: 930, height, body };
  }
  if (family === "waterfall") {
    let running = d.start!,
      segments = [
        { label: "Start / 起点", from: 0, to: running, value: running },
      ];
    for (const item of d.items) {
      segments.push({
        label: item.label,
        from: running,
        to: running + item.value!,
        value: item.value!,
      });
      running += item.value!;
    }
    segments.push({
      label: "End / 终点",
      from: 0,
      to: running,
      value: running,
    });
    const domain = extent(
        segments.flatMap((i) => [i.from, i.to]),
        true,
      ),
      width = Math.max(900, segments.length * 180 + 180),
      chartHeight = 380,
      labelHeight =
        Math.max(
          ...segments.map((i) => diagramTextLines(i.label, 150).length),
        ) * 21;
    let body = axesGrid(
      [0, segments.length],
      domain,
      110,
      35,
      width - 200,
      chartHeight,
      "",
      d.unit || "",
    );
    segments.forEach((item, i) => {
      const x = 135 + (i * (width - 210)) / segments.length,
        y = map(Math.max(item.from, item.to), domain, 415, 35),
        bottom = map(Math.min(item.from, item.to), domain, 415, 35);
      body +=
        `<rect data-from="${item.from}" data-to="${item.to}" x="${x}" y="${y}" width="90" height="${Math.max(1, bottom - y)}" fill="${i === 0 || i === segments.length - 1 ? "#4338ca" : item.value >= 0 ? "#17815a" : "#a64355"}"/>` +
        txt(x + 45, y - 10, fmt(item.value), 120) +
        txt(x + 45, 450, item.label, 150);
      if (i < segments.length - 1)
        body += line(
          x + 90,
          map(item.to, domain, 415, 35),
          x + (width - 210) / segments.length,
          map(item.to, domain, 415, 35),
          "#94a3b8",
        );
    });
    return { width, height: 485 + labelHeight, body };
  }
  if (["scatter", "line", "wardley", "journey"].includes(family))
    return plotScene(d, family, marker);
  if (family === "matrix") return matrixScene(d);
  if (family === "venn") return vennScene(d);
  if (family === "radar" || family === "polar") return radialScene(d, family);
  if (family === "treemap") return treemapScene(d);
  if (family === "sankey") return sankeyScene(d);
  if (family === "fishbone") return fishboneScene(d);
  if (family === "story") return storyScene(d);
  if (family === "exploded" || family === "plan")
    return spatialScene(d, family);
  throw new Error(`Unsupported layout: ${family}`);
}

function vectorScene(d: TeachingDiagram, marker: string): DiagramScene {
  const vectors = d.vectors!, points = vectors.flatMap(v => [v.from, v.to]);
  const xd = extent([0, ...points.map(p => p[0]!)]), yd = extent([0, ...points.map(p => p[1]!)]);
  const span = Math.max(xd[1]! - xd[0]!, yd[1]! - yd[0]!) * 1.15;
  const domain = (v: number[]) => { const c = (v[0]! + v[1]!) / 2; return [c - span / 2, c + span / 2]; };
  const xDomain = domain(xd), yDomain = domain(yd), size = 430;
  const x = (n: number) => map(n, xDomain, 85, 85 + size), y = (n: number) => map(n, yDomain, 35 + size, 35);
  let body = axesGrid(xDomain, yDomain, 85, 35, size, size, d.x_label || 'x', d.y_label || 'y');
  body += `<path data-axis="x" d="M85,${y(0)} H${85 + size}" stroke="#64748b"/><path data-axis="y" d="M${x(0)},35 V${35 + size}" stroke="#64748b"/>`;
  let legendY = 55;
  vectors.forEach((v, i) => {
    const color = colors[i % colors.length]!;
    body += `<g data-vector="${escapeDiagramText(v.label)}" data-from="${v.from.join(',')}" data-to="${v.to.join(',')}">`;
    if (v.from[0] === v.to[0] && v.from[1] === v.to[1]) body += `<circle cx="${x(v.from[0]!)}" cy="${y(v.from[1]!)}" r="5" fill="${color}"/>`;
    else body += `<path d="M${x(v.from[0]!)},${y(v.from[1]!)} L${x(v.to[0]!)},${y(v.to[1]!)}" stroke="${color}" stroke-width="3" fill="none" marker-end="url(#${marker})"/>`;
    body += '</g>';
    const label = `${v.label}\n(${v.from.join(', ')}) → (${v.to.join(', ')})`;
    body += line(565, legendY - 6, 595, legendY - 6, color) + txt(610, legendY, label, 250, 'start');
    legendY += diagramTextLines(label, 250).length * 21 + 30;
  });
  return { width: 920, height: Math.max(555, legendY + 30), body };
}

function matrixStepsScene(d: TeachingDiagram): DiagramScene {
  let y = 15, body = '';
  for (const [index, step] of d.steps!.entries()) {
    const rows = step.values.length, cols = step.values[0]!.length;
    const label = `${index + 1}. ${step.label}${step.operation ? '\n' + step.operation : ''}`;
    const labelHeight = diagramTextLines(label, 265).length * 21 + 24;
    const rowHeight = Math.max(49, ...step.values.flat().map(v => diagramTextLines(String(v), 65).length * 21 + 15));
    const height = Math.max(rows * rowHeight + 44, labelHeight + 26), left = 360, top = y + (height - rows * rowHeight) / 2;
    body += rect(10, y, 850, height, index % 2 ? '#f4f1fb' : '#f8fafc');
    body += txt(30, y + 31, label, 280, 'start');
    body += `<path d="M${left + 12},${top - 8} H${left} V${top + rows * rowHeight + 8} H${left + 12}" stroke="#64748b" fill="none"/>`;
    const right = left + cols * 74 + 12;
    body += `<path d="M${right - 12},${top - 8} H${right} V${top + rows * rowHeight + 8} H${right - 12}" stroke="#64748b" fill="none"/>`;
    step.values.forEach((row, r) => row.forEach((value, c) => { body += `<g data-step="${index}" data-row="${r}" data-column="${c}">${txt(left + 38 + c * 74, top + 30 + r * rowHeight, String(value), 65)}</g>`; }));
    y += height + 20;
  }
  return { width: 880, height: y + 5, body };
}

function axesGrid(
  xd: number[],
  yd: number[],
  x: number,
  y: number,
  w: number,
  h: number,
  xLabel: string,
  yLabel: string,
  horizontalOnly = false,
): string {
  let body = rect(x, y, w, h, "#fff", "#cbd5e1");
  for (let k = 0; k <= 4; k++) {
    const xv = xd[0]! + ((xd[1]! - xd[0]!) * k) / 4,
      yv = yd[0]! + ((yd[1]! - yd[0]!) * k) / 4;
    body +=
      line(x + (w * k) / 4, y, x + (w * k) / 4, y + h) +
      txt(x + (w * k) / 4, y + h + 28, fmt(xv), 100);
    if (!horizontalOnly)
      body +=
        line(x, y + h - (h * k) / 4, x + w, y + h - (h * k) / 4) +
        txt(x - 12, y + h - (h * k) / 4 + 6, fmt(yv), 100, "end");
  }
  body +=
    txt(x + w / 2, y + h + 65, xLabel, 500) +
    txt(x, Math.max(18, y - 12), yLabel, 350, "start");
  return body;
}

function plotScene(
  d: TeachingDiagram,
  family: string,
  marker: string,
): DiagramScene {
  const scatter = family === "scatter",
    wardley = family === "wardley",
    journey = family === "journey";
  const series = journey
    ? [
        {
          label: d.title,
          points: d.items.map((i, x) => ({ x, y: i.value!, label: i.label })),
        },
      ]
    : d.series;
  const points = wardley
    ? d.nodes.map((n) => ({ x: n.x!, y: n.y!, label: n.label }))
    : scatter
      ? d.items.map((i) => ({ x: i.x!, y: i.y!, label: i.label }))
      : series.flatMap((s) => s.points!);
  const xd = wardley ? [0, 1] : d.x_domain || extent(points.map((p) => p.x)),
    yd = wardley
      ? [0, 1]
      : d.y_domain ||
        extent(points.filter((p) => p.y !== null).map((p) => p.y!));
  need(
    points.every(
      (p) =>
        p.x >= xd[0]! &&
        p.x <= xd[1]! &&
        (p.y === null || (p.y >= yd[0]! && p.y <= yd[1]!)),
    ),
    "Point outside axes / 数据超出坐标范围",
  );
  const width = journey ? Math.max(950, d.items.length * 220 + 160) : 1000,
    pw = width - 230,
    px = (v: number) => map(v, xd, 130, 130 + pw),
    py = (v: number) => map(v, yd, 425, 55);
  let body = axesGrid(
    xd,
    yd,
    130,
    55,
    pw,
    370,
    d.x_label || (journey ? "Stage / 阶段" : ""),
    `${d.y_label || (journey ? "Feeling / 感受" : "")}${d.unit ? ` (${d.unit})` : ""}`,
  );
  if (d.type === "quadrant")
    body +=
      line(
        px((xd[0]! + xd[1]!) / 2),
        55,
        px((xd[0]! + xd[1]!) / 2),
        425,
        "#64748b",
      ) +
      line(
        130,
        py((yd[0]! + yd[1]!) / 2),
        130 + pw,
        py((yd[0]! + yd[1]!) / 2),
        "#64748b",
      );
  if (wardley)
    body += d.edges
      .map((edge) =>
        path(
          `M${px(d.nodes.find((n) => n.id === edge.from)!.x!)} ${py(d.nodes.find((n) => n.id === edge.from)!.y!)} L${px(d.nodes.find((n) => n.id === edge.to)!.x!)} ${py(d.nodes.find((n) => n.id === edge.to)!.y!)}`,
          "#94a3b8",
          1.7,
          marker,
        ),
      )
      .join("");
  if (!scatter && !wardley)
    series.forEach((s, index) => {
      let segment: string[] = [];
      const finish = () => {
        if (segment.length)
          body += path(segment.join(" "), colors[index]!, 2.5);
        segment = [];
      };
      s.points!.forEach((p) => {
        if (p.y === null) {
          finish();
          return;
        }
        segment.push(`${segment.length ? "L" : "M"}${px(p.x)} ${py(p.y)}`);
      });
      finish();
    });
  points.forEach((p, index) => {
    if (p.y !== null)
      body += `<circle data-x="${p.x}" data-y="${p.y}" cx="${px(p.x)}" cy="${py(p.y)}" r="5" fill="#4338ca"><title>${e(`${p.label || index + 1}: ${p.x}, ${p.y}`)}</title></circle>`;
  });
  let y = 520;
  if (!scatter && !wardley)
    series.forEach((s, index) => {
      body +=
        line(35, y - 5, 70, y - 5, colors[index]!) +
        txt(90, y, s.label, width - 150, "start");
      y += diagramTextLines(s.label, width - 150).length * 21 + 12;
    });
  const entries = journey
    ? d.items.map(
        (i, index) =>
          `${index}: ${i.label} · ${i.value} ${d.unit}${i.detail ? "\n" + i.detail : ""}`,
      )
    : points.map(
        (p) =>
          `${p.label || ""} (${fmt(p.x)}, ${p.y === null ? "∅ / 缺测" : fmt(p.y)})`,
      );
  entries.forEach((text) => {
    body += txt(40, y, text, width - 80, "start", "#475569");
    y += diagramTextLines(text, width - 80).length * 21 + 10;
  });
  return { width, height: y + 20, body };
}

function matrixScene(d: TeachingDiagram): DiagramScene {
  const rowWidth = Math.max(
      180,
      Math.min(380, ...d.rows.map((v) => v.length * 16 + 24)),
    ),
    cw = 200;
  const headerHeight =
    Math.max(...d.columns.map((v) => diagramTextLines(v, cw - 20).length)) *
      21 +
    45;
  const rh = Math.max(
    62,
    ...d.values
      .flat()
      .map(
        (v) =>
          diagramTextLines(v === null ? "∅" : String(v), cw - 20).length * 21 +
          20,
      ),
  );
  const width = Math.max(900, rowWidth + d.columns.length * cw + 50),
    height = headerHeight + d.rows.length * rh + 75;
  const nums = d.values
      .flat()
      .filter((v): v is number => typeof v === "number"),
    domain = nums.length ? extent(nums) : [0, 1];
  let body = d.columns
    .map((v, i) => txt(rowWidth + i * cw + cw / 2, 30, v, cw - 20))
    .join("");
  d.rows.forEach((row, i) => {
    body += txt(
      rowWidth - 20,
      headerHeight + i * rh + 28,
      row,
      rowWidth - 30,
      "end",
    );
    d.values[i]!.forEach((v, j) => {
      const magnitude =
        typeof v === "number"
          ? (v - domain[0]!) / (domain[1]! - domain[0]!)
          : 0;
      const fill =
        typeof v === "number"
          ? `hsl(242 65% ${96 - magnitude * 35}%)`
          : v === null
            ? "#f1f5f9"
            : "#fafbfd";
      body += `<g data-row="${i}" data-column="${j}">${rect(rowWidth + j * cw, headerHeight + i * rh, cw, rh, fill)}${txt(rowWidth + j * cw + cw / 2, headerHeight + i * rh + 28, v === null ? "∅ / 缺测" : v, cw - 20)}</g>`;
    });
  });
  if (d.type === "heatmap")
    body += txt(
      width / 2,
      height - 25,
      `${fmt(domain[0]!)} → ${fmt(domain[1]!)} ${d.unit} · ∅ = missing / 缺测`,
      width - 60,
    );
  return { width, height, body };
}

function vennScene(d: TeachingDiagram): DiagramScene {
  const three = d.sets.length === 3,
    centers = three
      ? [
          [330, 220],
          [530, 220],
          [430, 360],
        ]
      : [
          [320, 235],
          [560, 235],
        ],
    r = 165;
  let body = rect(20, 20, 850, three ? 520 : 405, "#fff", "#cbd5e1");
  d.sets.forEach((s, i) => {
    const [x, y] = centers[i]!;
    body +=
      `<circle cx="${x}" cy="${y}" r="${r}" fill="${colors[i]!}" fill-opacity="0.08" stroke="${colors[i]!}"/>` +
      txt(i === 0 ? 165 : i === 1 ? 700 : 430, i < 2 ? 55 : 525, s.label, 230);
  });
  const union = [...new Set(d.sets.flatMap((s) => s.items))],
    universe = d.universe || union;
  const regions = new Map<number, string[]>();
  for (const item of universe) {
    const bits = d.sets.reduce(
      (mask, s, i) => mask | (s.items.includes(item) ? 1 << i : 0),
      0,
    );
    regions.set(bits, [...(regions.get(bits) || []), item]);
  }
  const positions: Record<number, [number, number]> = three
    ? {
        0: [75, 410],
        1: [260, 190],
        2: [600, 190],
        3: [430, 150],
        4: [430, 445],
        5: [330, 325],
        6: [530, 325],
        7: [430, 270],
      }
    : { 0: [70, 390], 1: [235, 235], 2: [645, 235], 3: [440, 235] };
  let y = three ? 575 : 470;
  for (let bits = 0; bits < 1 << d.sets.length; bits++) {
    const members = regions.get(bits) || [],
      [x, yy] = positions[bits]!;
    body += txt(x, yy, `${bits}: ${members.length}`, 110);
    const name = bits
      ? d.sets
          .map((s, i) => (bits & (1 << i) ? s.label : `¬${s.label}`))
          .join(" ∩ ")
      : "Outside / 全集内集合外";
    const text = `${bits}. ${name}: {${members.join(", ")}}`;
    body += txt(30, y, text, 830, "start");
    y += diagramTextLines(text, 830).length * 21 + 15;
  }
  body += txt(
    450,
    y + 10,
    "Areas do not encode counts / 圆面积不表示数量",
    850,
  );
  return { width: 900, height: y + 45, body };
}

function radialScene(d: TeachingDiagram, family: string): DiagramScene {
  const axes = family === "radar" ? d.axes : d.items.map((i) => i.label),
    count = axes.length,
    max =
      family === "radar"
        ? d.scale![1]!
        : Math.max(...d.items.map((i) => i.value!)),
    cx = 460,
    cy = 370,
    radius = 240;
  const point = (angle: number, value: number): [number, number] => [
    cx + (Math.cos(angle) * radius * value) / max,
    cy + (Math.sin(angle) * radius * value) / max,
  ];
  let body = "";
  for (let level = 1; level <= 4; level++) {
    const p = axes.map((_, i) =>
      point((i * 2 * Math.PI) / count - Math.PI / 2, (max * level) / 4),
    );
    body +=
      family === "radar"
        ? `<polygon points="${p.map((p) => p.join(",")).join(" ")}" fill="none" stroke="#cbd5e1"/>`
        : `<circle cx="${cx}" cy="${cy}" r="${(radius * level) / 4}" fill="none" stroke="#cbd5e1"/>`;
    body += txt(
      cx + 12,
      cy - (radius * level) / 4 + 17,
      fmt((max * level) / 4),
      100,
      "start",
      "#64748b",
    );
  }
  axes.forEach((name, i) => {
    const angle = (i * 2 * Math.PI) / count - Math.PI / 2,
      [x, y] = point(angle, max);
    body +=
      line(cx, cy, x, y) +
      txt(
        cx + Math.cos(angle) * 320,
        cy + Math.sin(angle) * 285,
        count > 8 || diagramTextLines(name, 170).length > 1
          ? `${i + 1}`
          : `${i + 1}. ${name}`,
        170,
      );
  });
  if (family === "radar")
    d.series.forEach((s, index) => {
      const points = s.values!.map((v, i) =>
        point((i * 2 * Math.PI) / count - Math.PI / 2, v),
      );
      body += `<polygon data-series="${index}" points="${points.map((p) => p.join(",")).join(" ")}" fill="${colors[index]!}" fill-opacity="0.08" stroke="${colors[index]!}" stroke-width="2"/>`;
    });
  else
    d.items.forEach((item, index) => {
      const angle = (index * 2 * Math.PI) / count - Math.PI / 2,
        [x, y] = point(angle, item.value!);
      body +=
        path(
          `M${cx} ${cy} L${x} ${y}`,
          colors[index % colors.length]!,
          Math.max(2, Math.min(30, 100 / count)),
        ) +
        `<circle data-value="${item.value}" cx="${x}" cy="${y}" r="5" fill="${colors[index % colors.length]!}"/>`;
    });
  let y = 745;
  const entries =
    family === "radar"
      ? d.series.map((s, i) => ({
          text: `${s.label}: ${d.axes.map((axis, j) => `${j + 1}. ${axis}=${s.values![j]!}`).join("; ")} (${d.unit}, 0…${max})`,
          color: colors[i]!,
        }))
      : d.items.map((i, index) => ({
          text: `${index + 1}. ${i.label}: ${i.value} ${d.unit}`,
          color: colors[index % colors.length]!,
        }));
  entries.forEach((row) => {
    body += txt(30, y, row.text, 860, "start", row.color);
    y += diagramTextLines(row.text, 860).length * 21 + 14;
  });
  return { width: 950, height: y + 25, body };
}

function treemapScene(d: TeachingDiagram): DiagramScene {
  let body = "",
    labelY = 610;
  const roots = d.items.filter((i) => !i.parent);
  const draw = (
    part: DiagramItem[],
    x: number,
    y: number,
    w: number,
    h: number,
    depth: number,
  ) => {
    const total = part.reduce((sum, i) => sum + i.value!, 0);
    let cursor = depth % 2 ? y : x;
    part.forEach((item) => {
      const span = ((depth % 2 ? h : w) * item.value!) / total,
        xx = depth % 2 ? x : cursor,
        yy = depth % 2 ? cursor : y,
        ww = depth % 2 ? w : span,
        hh = depth % 2 ? span : h,
        index = d.items.indexOf(item);
      const children = d.items.filter((c) => item.id && c.parent === item.id);
      body += `<g data-value="${item.value}" data-id="${e(item.id || index)}">${rect(xx, yy, ww, hh, colors[index % colors.length]!, "#fff")}<title>${e(`${item.label}: ${item.value} ${d.unit}`)}</title>${ww > 35 && hh > 30 && !children.length ? txt(xx + ww / 2, yy + 23, String(index + 1), 40, "middle", "#fff") : ""}</g>`;
      if (children.length) draw(children, xx, yy, ww, hh, depth + 1);
      cursor += span;
    });
  };
  draw(roots, 30, 25, 840, 530, 0);
  d.items.forEach((i, index) => {
    const text = `${index + 1}. ${i.label}: ${i.value} ${d.unit}${i.parent ? ` (parent / 父项: ${i.parent})` : ""}`;
    body += txt(30, labelY, text, 840, "start");
    labelY += diagramTextLines(text, 840).length * 21 + 12;
  });
  return { width: 900, height: labelY + 20, body };
}

function sankeyScene(d: TeachingDiagram): DiagramScene {
  const ranks = diagramRanks(d.nodes, d.edges),
    maxRank = Math.max(...ranks);
  const sum = (id: string, incoming: boolean) =>
    d.edges
      .filter((e) => (incoming ? e.to === id : e.from === id))
      .reduce((total, e) => total + e.value!, 0);
  const quantities = d.nodes.map((n) =>
    Math.max(sum(n.id, true), sum(n.id, false)),
  );
  need(
    quantities.every((q) => q > 0),
    "Isolated flow node / 流量节点不能孤立",
  );
  const levelTotals = ranks.map((rank) =>
      quantities.reduce(
        (total, q, index) => total + (ranks[index]! === rank ? q : 0),
        0,
      ),
    ),
    factor = 450 / Math.max(...levelTotals);
  const width = Math.max(1000, (maxRank + 1) * 330 + 180),
    columnTops = new Map<number, number>();
  const boxes = d.nodes.map((_, index) => {
    const rank = ranks[index]!,
      y = columnTops.get(rank) || 50,
      h = quantities[index]! * factor;
    columnTops.set(rank, y + h + 100);
    return { x: 130 + rank * 330, y, w: 25, h };
  });
  const height = Math.max(...boxes.map((b) => b.y + b.h)) + 140;
  const fromOffsets = d.nodes.map(() => 0),
    toOffsets = d.nodes.map(() => 0);
  let body = "";
  d.edges.forEach((edge) => {
    const a = d.nodes.findIndex((n) => n.id === edge.from),
      b = d.nodes.findIndex((n) => n.id === edge.to),
      thickness = edge.value! * factor,
      from = boxes[a]!,
      to = boxes[b]!,
      sy = from.y + fromOffsets[a]! + thickness / 2,
      ty = to.y + toOffsets[b]! + thickness / 2;
    fromOffsets[a]! += thickness;
    toOffsets[b]! += thickness;
    const sx = from.x + from.w,
      tx = to.x,
      mid = (sx + tx) / 2;
    body += `<path data-value="${edge.value}" d="M${sx} ${sy} C${mid} ${sy},${mid} ${ty},${tx} ${ty}" fill="none" stroke="${colors[a % colors.length]!}" stroke-opacity="0.25" stroke-width="${thickness}"><title>${e(`${edge.from} → ${edge.to}: ${edge.value} ${d.unit}${edge.label ? " · " + edge.label : ""}`)}</title></path>`;
  });
  d.nodes.forEach((n, i) => {
    const b = boxes[i]!;
    body +=
      rect(b.x, b.y, b.w, b.h, colors[i % colors.length]!) +
      txt(
        b.x + 12,
        b.y + b.h + 25,
        `${n.label}\n${fmt(quantities[i]!)} ${d.unit}`,
        245,
      );
  });
  // The band itself encodes amount; explicit edge records remain available below the figure.
  return { width, height, body };
}

function fishboneScene(d: TeachingDiagram): DiagramScene {
  const width = Math.max(1000, Math.ceil(d.groups.length / 2) * 300 + 400),
    groupTexts = d.groups.map(
      (g) =>
        `${g.label}\n${d.items
          .filter((i) => i.group === g.id)
          .map((i) => "• " + i.label)
          .join("\n")}`,
    ),
    groupHeight =
      Math.max(...groupTexts.map((t) => diagramTextLines(t, 260).length)) * 21 +
      40,
    cy = groupHeight + 60,
    height = groupHeight * 2 + 140;
  let body =
    line(70, cy, width - 220, cy, "#64748b") +
    rect(width - 230, cy - 45, 215, 90, "#eef2ff") +
    txt(width - 120, cy - 12, d.effect, 195);
  d.groups.forEach((_, index) => {
    const x = 110 + Math.floor(index / 2) * 300,
      above = index % 2 === 0,
      y = above ? 32 : cy + 70;
    body +=
      path(
        `M${x + 120} ${above ? groupHeight : cy + 55} L${x + 225} ${cy}`,
        "#94a3b8",
      ) + txt(x, y, groupTexts[index]!, 260, "start");
  });
  return { width, height, body };
}

function storyScene(d: TeachingDiagram): DiagramScene {
  const cw = 275,
    width = Math.max(900, d.groups.length * cw + 210),
    cellHeight = Math.max(90, ...d.nodes.map((n) => nodeHeight(n)));
  const rows = d.rows.map((row) =>
    Math.max(
      1,
      ...d.groups.map(
        (g) => d.nodes.filter((n) => n.row === row && n.group === g.id).length,
      ),
    ),
  );
  let y = 100,
    body = d.groups
      .map((g, i) => txt(200 + i * cw + cw / 2, 35, g.label, 245))
      .join("");
  d.rows.forEach((row, index) => {
    const h = rows[index]! * (cellHeight + 20) + 20;
    body +=
      txt(160, y + 30, row, 140, "end") +
      line(180, y - 10, width - 15, y - 10, "#64748b");
    d.groups.forEach((g, col) => {
      const ns = d.nodes.filter((n) => n.row === row && n.group === g.id);
      body += rect(195 + col * cw, y, cw - 10, h, "#fafbfd");
      ns.forEach((n, i) => {
        body += boxNode(n, {
          x: 205 + col * cw,
          y: y + 10 + i * (cellHeight + 20),
          w: cw - 30,
          h: cellHeight,
        });
      });
    });
    y += h + 25;
  });
  return { width, height: y + 20, body };
}

function spatialScene(d: TeachingDiagram, family: string): DiagramScene {
  const project = (x: number, y: number, z = 0): [number, number] => [
    x - y * 0.65,
    (x + y) * 0.32 - z,
  ];
  const rawPolygons = d.items.map((i, index) => {
    const x = family === "plan" ? i.x! : 0,
      y = family === "plan" ? i.y! : 0,
      z =
        family === "plan"
          ? 0
          : index * (Math.max(...d.items.map((i) => i.depth!)) + 25);
    const top = [
      [x, y],
      [x + i.width!, y],
      [x + i.width!, y + i.height!],
      [x, y + i.height!],
    ].map((p) => project(p[0]!, p[1]!, z));
    const side =
      family === "plan"
        ? []
        : [
            [x, y],
            [x + i.width!, y],
            [x + i.width!, y],
            [x, y],
          ].map((p, j) => project(p[0]!, p[1]!, z - (j >= 2 ? i.depth! : 0)));
    return { top, side };
  });
  const points = rawPolygons.flatMap((p) => [...p.top, ...p.side]),
    xd = extent(points.map((p) => p[0]!)),
    yd = extent(points.map((p) => p[1]!)),
    scale = Math.min(700 / (xd[1]! - xd[0]!), 550 / (yd[1]! - yd[0]!));
  const transform = (p: number[]) => [
    80 + (p[0]! - xd[0]!) * scale,
    40 + (p[1]! - yd[0]!) * scale,
  ];
  let body = "";
  rawPolygons.forEach((polygon, index) => {
    const top = polygon.top.map(transform),
      side = polygon.side.map(transform);
    body += `${side.length ? `<polygon points="${side.map((p) => p.join(",")).join(" ")}" fill="${colors[index % colors.length]!}" fill-opacity="0.35" stroke="#64748b"/>` : ""}<polygon points="${top.map((p) => p.join(",")).join(" ")}" fill="${colors[index % colors.length]!}" fill-opacity="0.1" stroke="${colors[index % colors.length]!}"/><text x="${top.reduce((v, p) => v + p[0]!, 0) / 4}" y="${top.reduce((v, p) => v + p[1]!, 0) / 4}" text-anchor="middle" font-size="16">${index + 1}</text>`;
  });
  let y = 650;
  d.items.forEach((i, index) => {
    const text = `${index + 1}. ${i.label} · ${i.width}×${i.height}${family === "exploded" ? `×${i.depth}` : ` · (${i.x},${i.y})`} ${d.unit}${i.detail ? "\n" + i.detail : ""}`;
    body += txt(30, y, text, 830, "start");
    y += diagramTextLines(text, 830).length * 21 + 12;
  });
  body += txt(450, y + 15, "Schematic projection / 示意投影", 830);
  return { width: 900, height: y + 50, body };
}
