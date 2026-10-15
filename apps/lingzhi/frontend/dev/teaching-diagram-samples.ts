import { teachingDiagramCatalog } from "../src/utils/teaching-diagrams";

// Hand-authored public teaching examples, never course or learner records.
const node = (id: string, label: string, extra = {}) => ({
  id,
  label,
  ...extra,
});
const edge = (from: string, to: string, extra = {}) => ({ from, to, ...extra });
const graph = {
  nodes: [
    node("a", "输入 Input"),
    node("b", "处理 Process"),
    node("c", "输出 Output"),
  ],
  edges: [
    edge("a", "b", { label: "数据 Data" }),
    edge("b", "c", { label: "结果 Result" }),
  ],
};
const grouped = {
  groups: [
    node("g1", "来源 Sources"),
    node("g2", "服务 Services"),
    node("g3", "消费者 Consumers"),
  ],
  nodes: [
    node("a", "输入 Input", { group: "g1" }),
    node("b", "处理 Process", { group: "g2" }),
    node("c", "输出 Output", { group: "g3" }),
  ],
  edges: graph.edges,
};
const data: Record<string, object> = {
  vector_plot: { vectors: [{ label: 'u', from: [0, 0], to: [1, 2] }, { label: '2v', from: [1, 2], to: [5, 4] }, { label: 'w = u + 2v', from: [0, 0], to: [5, 4] }], x_label: 'x', y_label: 'y' },
  matrix_steps: { steps: [{ label: '原增广矩阵 / Original', values: [[1, 2, 5], [2, 1, 4]] }, { label: '行阶梯形 / Echelon', operation: 'R₂ ← R₂ − 2R₁', values: [[1, 2, 5], [0, -3, -6]] }] },
  architecture: graph,
  architecture_delta: {
    before: {
      nodes: graph.nodes.slice(0, 2),
      edges: [edge("a", "b", { label: "调用 Call" })],
    },
    after: graph,
  },
  it_current_state: grouped,
  flowchart: {
    nodes: [
      node("check", "索引是否在范围内？ In bounds?", { kind: "decision" }),
      node("read", "读取 Read"),
      node("stop", "结束 Stop"),
    ],
    edges: [
      edge("check", "read", { label: "是 Yes" }),
      edge("check", "stop", { label: "否 No" }),
    ],
  },
  sequence: {
    nodes: [
      node("page", "页面 Page"),
      node("service", "服务 Service"),
      node("store", "存储 Store"),
    ],
    edges: [
      edge("page", "service", { label: "读取请求 Read request" }),
      edge("service", "store", { label: "查询 Query" }),
      edge("store", "service", { label: "返回数据 Data", kind: "return" }),
      edge("service", "page", { label: "返回结果 Result", kind: "return" }),
    ],
  },
  state_machine: {
    nodes: [
      node("idle", "空闲 Idle"),
      node("running", "运行 Running"),
      node("done", "完成 Done"),
    ],
    edges: [
      edge("idle", "running", { label: "启动 Start" }),
      edge("running", "done", { label: "完成 Finish" }),
      edge("running", "idle", { label: "取消 Cancel" }),
    ],
  },
  er_model: {
    nodes: [
      node("student", "Student 学生", {
        detail: "student_id (PK)\nname: string",
      }),
      node("enrollment", "Enrollment 选课", {
        detail: "student_id (FK)\ncourse_id (FK)",
      }),
    ],
    edges: [edge("student", "enrollment", { label: "1 → 0..N" })],
  },
  timeline: {
    items: [
      { label: "开始 Start", value: 0 },
      { label: "记录 Record", value: 1 },
      { label: "再次记录 Record", value: 3 },
      { label: "结束 End", value: 6 },
    ],
    unit: "秒 s",
  },
  swimlane: grouped,
  quadrant: {
    items: [
      { label: "方案 A", x: 2, y: 8 },
      { label: "方案 B", x: 7, y: 3 },
    ],
    x_label: "成本 Cost",
    y_label: "收益 Benefit",
    x_domain: [0, 10],
    y_domain: [0, 10],
    unit: "假设评分 Example score",
  },
  radar: {
    axes: ["维度 A", "维度 B", "维度 C", "维度 D"],
    series: [{ label: "假设设计 Example", values: [2, 4, 3, 5] }],
    scale: [0, 5],
    unit: "公开量规 Rubric",
  },
  polar: {
    items: [
      { label: "春 Spring", value: 2 },
      { label: "夏 Summer", value: 5 },
      { label: "秋 Autumn", value: 3 },
      { label: "冬 Winter", value: 1 },
    ],
    unit: "次 Count",
  },
  loop: {
    nodes: [
      node("observe", "观察 Observe"),
      node("test", "检验 Test"),
      node("revise", "修订 Revise"),
    ],
    edges: [
      edge("observe", "test"),
      edge("test", "revise"),
      edge("revise", "observe"),
    ],
    hub: "积累证据 Accumulated evidence",
  },
  nested: {
    nodes: [
      node("real", "实数 ℝ"),
      node("rational", "有理数 ℚ", { parent: "real" }),
      node("integer", "整数 ℤ", { parent: "rational", detail: "-2, 0, 3" }),
    ],
  },
  tree: {
    nodes: [
      node("list", "线性表 Linear list"),
      node("array", "顺序存储 Sequential", { parent: "list" }),
      node("linked", "链式存储 Linked", { parent: "list" }),
    ],
  },
  org_chart: {
    nodes: [
      node("lead", "组长 Lead", { detail: "协调 Coordination" }),
      node("member", "成员 Member", {
        parent: "lead",
        detail: "实现 Implementation",
      }),
    ],
  },
  layer_stack: {
    items: [
      { label: "界面 Interface", detail: "展示与接收操作 Display and actions" },
      { label: "应用 Application", detail: "编排用例 Coordinate use cases" },
      { label: "领域 Domain", detail: "业务规则 Business rules" },
      { label: "存储 Persistence", detail: "保存数据 Store data" },
    ],
  },
  exploded_axonometric: {
    items: [
      { label: "底板 Base", width: 120, height: 80, depth: 10 },
      { label: "隔片 Spacer", width: 100, height: 60, depth: 5 },
      { label: "上盖 Cover", width: 120, height: 80, depth: 8 },
    ],
    unit: "假设毫米 Example mm",
  },
  axonometric_plan: {
    items: [
      { label: "房间 A", x: 0, y: 0, width: 4, height: 3 },
      { label: "房间 B", x: 4, y: 0, width: 3, height: 3 },
    ],
    unit: "假设米 Example m",
  },
  venn: {
    sets: [
      { label: "A", items: ["1", "2", "3", "4"] },
      { label: "B", items: ["3", "4", "5", "6"] },
    ],
    universe: ["1", "2", "3", "4", "5", "6"],
  },
  pyramid_funnel: {
    items: [
      { label: "进入 Entered", value: 100 },
      { label: "完成 Completed", value: 60 },
      { label: "复核 Reviewed", value: 30 },
    ],
    unit: "假设任务 Example tasks",
  },
  bar_chart: {
    items: [
      { label: "甲 A", value: 12 },
      { label: "乙 B", value: 18 },
      { label: "丙 C", value: 9 },
      { label: "丁 D", value: 24 },
    ],
    unit: "个 Count",
  },
  waterfall: {
    start: 100,
    items: [
      { label: "收入 Income", value: 30 },
      { label: "支出 Expense", value: -20 },
    ],
    unit: "假设元 Example CNY",
  },
  treemap: {
    items: [
      { id: "a", label: "A", value: 60 },
      { id: "b", label: "B", value: 40 },
      { id: "a1", parent: "a", label: "A1", value: 20 },
      { id: "a2", parent: "a", label: "A2", value: 40 },
    ],
    unit: "个 Count",
  },
  heatmap: {
    rows: ["甲 A", "乙 B"],
    columns: ["周一 Mon", "周二 Tue"],
    values: [
      [1, null],
      [2, 0],
    ],
    unit: "次 Count",
  },
  line_chart: {
    series: [
      {
        label: "观察 Observation",
        points: [
          { x: 0, y: 0 },
          { x: 1, y: 2 },
          { x: 2, y: null },
          { x: 3, y: 6 },
        ],
      },
    ],
    x_label: "时间 Time (s)",
    y_label: "位移 Displacement",
    unit: "米 m",
  },
  gantt: {
    items: [
      { label: "准备 Prepare", start: 0, end: 2 },
      { label: "实验 Experiment", start: 2, end: 5 },
      { label: "分析 Analyze", start: 5, end: 7 },
    ],
    unit: "天 Days",
  },
  scatter_plot: {
    items: [
      { label: "甲 A", x: 1, y: 2 },
      { label: "乙 B", x: 3, y: 5 },
      { label: "丙 C", x: 4, y: 3 },
    ],
    x_label: "变量 X",
    y_label: "变量 Y",
    unit: "测量单位 Units",
  },
  high_level: {
    ...grouped,
    groups: [
      node("g1", "入口 Ingress"),
      node("g2", "容器集群 Cluster"),
      node("g3", "存储 Storage"),
    ],
  },
  process: graph,
  medallion: {
    items: [
      { label: "Bronze 原始层", detail: "保留原始记录 Raw records" },
      { label: "Silver 清洗层", detail: "已清洗数据 Clean data" },
      { label: "Gold 聚合层", detail: "用途聚合 Aggregates" },
    ],
  },
  data_flow: grouped,
  dp_integration: grouped,
  dp_security_matrix: {
    rows: ["读取者 Reader", "编辑者 Editor"],
    columns: ["资料 Data", "设置 Settings"],
    values: [
      ["read", "none"],
      ["read/write", "read"],
    ],
  },
  sankey: {
    nodes: [
      node("a", "总量 Total"),
      node("b", "甲 A"),
      node("c", "乙 B"),
      node("d", "汇总 Sum"),
    ],
    edges: [
      edge("a", "b", { value: 60 }),
      edge("a", "c", { value: 40 }),
      edge("b", "d", { value: 60 }),
      edge("c", "d", { value: 40 }),
    ],
    unit: "个 Count",
  },
  fishbone: {
    effect: "测量偏差 Measurement error",
    groups: [node("g1", "设备 Equipment"), node("g2", "操作 Operation")],
    items: [
      { label: "校准缺失 Missing calibration", group: "g1" },
      { label: "读数角度 Viewing angle", group: "g2" },
    ],
  },
  wardley_map: {
    nodes: [
      node("need", "用户需要 User need", { x: 0.2, y: 0.9 }),
      node("service", "服务 Service", { x: 0.5, y: 0.6 }),
      node("utility", "通用设施 Utility", { x: 0.9, y: 0.2 }),
    ],
    edges: [edge("need", "service"), edge("service", "utility")],
    x_label: "演化 Evolution",
    y_label: "可见性 Visibility",
  },
  kanban: {
    groups: [
      node("todo", "待做 Todo", { limit: 3 }),
      node("doing", "进行中 Doing", { limit: 1 }),
      node("done", "完成 Done"),
    ],
    nodes: [
      node("a", "准备样本 Prepare", { group: "todo" }),
      node("b", "采集数据 Collect", { group: "doing", status: "阻塞 Blocked" }),
      node("c", "核对条件 Check", { group: "done" }),
    ],
  },
  user_journey: {
    items: [
      { label: "发现 Discover", detail: "找到资料 Find material", value: 1 },
      { label: "阅读 Read", detail: "理解概念 Understand", value: 3 },
      { label: "应用 Apply", detail: "完成任务 Complete task", value: 2 },
    ],
    unit: "假设感受量规 Example scale",
  },
  deployment: {
    ...grouped,
    groups: [
      node("g1", "浏览器 Browser"),
      node("g2", "服务区 Service zone"),
      node("g3", "数据区 Data zone"),
    ],
  },
  dependency_graph: {
    nodes: [node("a", "前提 A"), node("b", "前提 B"), node("c", "结论 C")],
    edges: [
      edge("a", "c", { label: "条件 Condition" }),
      edge("b", "c", { label: "条件 Condition" }),
    ],
  },
  uml_class: {
    nodes: [
      node("shape", "Shape", { detail: "+ area(): number" }),
      node("circle", "Circle", {
        detail: "- radius: number\n+ area(): number",
      }),
    ],
    edges: [edge("circle", "shape", { kind: "inheritance" })],
  },
  story_map: {
    groups: [node("find", "查找 Find"), node("read", "阅读 Read")],
    rows: ["初版 Release 1", "扩展 Release 2"],
    nodes: [
      node("a", "课程列表 List", { group: "find", row: "初版 Release 1" }),
      node("b", "正文 Content", { group: "read", row: "初版 Release 1" }),
      node("c", "筛选 Filter", { group: "find", row: "扩展 Release 2" }),
      node("d", "笔记 Notes", { group: "read", row: "扩展 Release 2" }),
    ],
  },
  database_schema: {
    nodes: [
      node("courses", "courses", {
        detail: "id UUID PRIMARY KEY\ntitle TEXT NOT NULL",
      }),
      node("lessons", "lessons", {
        detail:
          "id UUID PRIMARY KEY\ncourse_id UUID REFERENCES courses(id)\nINDEX(course_id)",
      }),
    ],
    edges: [
      edge("lessons", "courses", { label: "lessons.course_id → courses.id" }),
    ],
  },
};

export const teachingDiagramSamples = teachingDiagramCatalog.types.map(
  (entry) => ({
    schema_version: teachingDiagramCatalog.schema_version,
    type: entry.id,
    title: `${entry.zh} / ${entry.en}`,
    summary:
      "手写教学示例；保留条件与实际数值，不能当成真实课程或学习记录。 Hand-written example, not a course or learner record.",
    source: "自编假设示例 / Hand-authored hypothetical example",
    ...data[entry.id],
  }),
);
