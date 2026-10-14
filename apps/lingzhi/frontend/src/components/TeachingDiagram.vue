<template>
  <figure class="teaching-diagram" :data-diagram-type="spec?.type || undefined">
    <template v-if="pending"
      ><p class="diagram-pending" role="status">
        {{ tr("图表正在生成…", "Generating diagram…") }}
      </p></template
    >
    <template v-else>
      <header>
        <h5>{{ spec?.title || fallback.title }}</h5>
        <div v-if="svg" class="diagram-tools">
          <button type="button" @click="openLarge">
            {{ tr("放大查看", "Expand") }}
          </button>
          <button type="button" @click="download">
            {{ tr("下载 SVG", "Download SVG") }}
          </button>
        </div>
      </header>
      <div
        v-if="svg"
        class="diagram-scroll"
        tabindex="0"
        :aria-label="spec?.title"
        v-html="svg"
      />
      <p v-else class="diagram-error" role="status">
        {{
          tr(
            "图表暂不可绘制，文字和原始数据已保留。",
            "The diagram cannot be drawn. Text and original data are preserved.",
          )
        }}
        <span>{{ error }}</span>
      </p>
      <section
        v-if="svg && readingRows.length"
        class="diagram-labels"
        :aria-label="tr('图例与数据', 'Labels and data')"
      >
        <h6>{{ tr("图例与数据", "Labels and data") }}</h6>
        <dl tabindex="0" :aria-label="tr('图例与数据', 'Labels and data')">
          <div v-for="(row, index) in readingRows" :key="index">
            <dt>{{ row.label }}</dt>
            <dd v-if="row.value">{{ row.value }}</dd>
          </div>
        </dl>
      </section>
      <figcaption>
        <p>{{ spec?.summary || fallback.summary }}</p>
        <p v-if="spec?.source || fallback.source" class="diagram-source">
          {{ tr("来源：", "Source: ") }}{{ spec?.source || fallback.source }}
        </p>
      </figcaption>
      <details class="diagram-data">
        <summary>
          {{ tr("查看完整数据与关系", "Read complete data and relationships") }}
        </summary>
        <table v-if="spec?.nodes.length">
          <thead>
            <tr>
              <th>{{ tr("对象", "Object") }}</th>
              <th>{{ tr("说明", "Details") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="node in spec.nodes" :key="node.id">
              <td>{{ node.label }}</td>
              <td>
                {{
                  [node.detail, node.parent, node.group, node.status]
                    .filter(Boolean)
                    .join(" · ")
                }}
              </td>
            </tr>
          </tbody>
        </table>
        <table v-if="spec?.edges.length">
          <thead>
            <tr>
              <th>{{ tr("关系", "Relationship") }}</th>
              <th>{{ tr("条件与数量", "Conditions and quantity") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(edge, i) in spec.edges" :key="i">
              <td>{{ nodeLabel(edge.from) }} → {{ nodeLabel(edge.to) }}</td>
              <td>
                {{
                  [
                    edge.label,
                    edge.kind,
                    edge.value === undefined
                      ? ""
                      : `${edge.value} ${spec.unit || ""}`,
                  ]
                    .filter(Boolean)
                    .join(" · ")
                }}
              </td>
            </tr>
          </tbody>
        </table>
        <pre>{{ raw }}</pre>
      </details>
      <dialog
        ref="largeDialog"
        class="diagram-dialog"
        :aria-label="spec?.title"
        @click="closeOnBackdrop"
        @close="onClose"
      >
        <header>
          <h5>{{ spec?.title }}</h5>
          <button type="button" @click="largeDialog?.close()">
            {{ tr("关闭", "Close") }}
          </button>
        </header>
        <div
          v-if="expanded"
          class="diagram-scroll"
          tabindex="0"
          v-html="largeSvg"
        />
        <p>{{ spec?.summary }}</p>
        <p class="diagram-source">
          {{ tr("来源：", "Source: ") }}{{ spec?.source }}
        </p>
      </dialog>
    </template>
  </figure>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useId } from "vue";
import { activeLocale } from "../shared/i18n";
import { diagramReadingRows } from "../utils/teaching-diagram-layout";
import {
  parseTeachingDiagram,
  teachingDiagramSvg,
} from "../utils/teaching-diagrams";

const props = defineProps<{
  raw: string;
  pending?: boolean;
  instanceId?: string;
}>();
const tr = (zh: string, en: string) => (activeLocale.value === "en" ? en : zh);
const localId = useId(),
  id = props.instanceId || localId,
  largeDialog = ref<HTMLDialogElement | null>(null);
const expanded = ref(false);
const result = computed(() => {
  if (props.pending) return { spec: null, svg: "", error: "" };
  try {
    const spec = parseTeachingDiagram(props.raw);
    return { spec, svg: teachingDiagramSvg(spec, id), error: "" };
  } catch (error) {
    return {
      spec: null,
      svg: "",
      error: error instanceof Error ? error.message : "",
    };
  }
});
const spec = computed(() => result.value.spec),
  svg = computed(() => result.value.svg),
  error = computed(() => result.value.error);
const largeSvg = computed(() =>
  spec.value ? teachingDiagramSvg(spec.value, id + "-large") : "",
);
const readingRows = computed(() =>
  spec.value ? diagramReadingRows(spec.value) : [],
);
const fallback = computed(() => {
  try {
    const r = JSON.parse(props.raw);
    return {
      title:
        typeof r.title === "string"
          ? r.title
          : tr("教学图表", "Teaching diagram"),
      summary: typeof r.summary === "string" ? r.summary : "",
      source: typeof r.source === "string" ? r.source : "",
    };
  } catch {
    return {
      title: tr("教学图表", "Teaching diagram"),
      summary: "",
      source: "",
    };
  }
});
const nodeLabel = (id: string) =>
  spec.value?.nodes.find((n) => n.id === id)?.label || id;
let trigger: HTMLElement | null = null,
  objectUrl = "";
async function openLarge(event: Event) {
  trigger = event.currentTarget as HTMLElement;
  expanded.value = true;
  await nextTick();
  if (largeDialog.value?.isConnected) largeDialog.value.showModal();
}
function onClose() {
  expanded.value = false;
  trigger?.focus();
}
function closeOnBackdrop(event: MouseEvent) {
  const dialog = largeDialog.value;
  if (!dialog || event.target !== dialog) return;
  const rect = dialog.getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
}
function download() {
  if (!svg.value) return;
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = URL.createObjectURL(
    new Blob([svg.value], { type: "image/svg+xml;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = `lingzhi-${spec.value!.type}.svg`;
  document.body.append(link);
  link.click();
  link.remove();
}
onBeforeUnmount(() => {
  if (objectUrl) URL.revokeObjectURL(objectUrl);
});
</script>

<style scoped>
.teaching-diagram {
  margin: 22px 0;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  container-type: inline-size;
  border: 1px solid #dbe3ed;
  background: white;
  min-width: 0;
  color: #172033;
  font:
    16px/1.75 system-ui,
    "Microsoft YaHei",
    sans-serif;
}
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 12px 18px;
  border-bottom: 1px solid #e2e8f0;
}
h5 {
  margin: 0;
  font-size: 17px;
  line-height: 1.6;
  font-weight: 650;
  color: #4338ca;
  overflow-wrap: anywhere;
}
.diagram-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
button {
  font: inherit;
  color: #4338ca;
  padding: 4px 9px;
  border: 1px solid #c7d2fe;
  background: #fff;
  border-radius: 3px;
  cursor: pointer;
}
button:focus-visible,
summary:focus-visible,
.diagram-labels dl:focus-visible,
.diagram-scroll:focus-visible {
  outline: 3px solid #328dcc;
  outline-offset: 2px;
}
.diagram-scroll {
  overflow: auto;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
  max-height: 700px;
  padding: 12px;
  overscroll-behavior: contain;
}
.diagram-scroll :deep(svg) {
  display: block;
  margin-inline: auto;
  max-width: 100%;
  height: auto;
  flex: none;
}
.diagram-labels {
  display: none;
  padding: 10px 16px;
  border-top: 1px solid #e2e8f0;
  font-size: 15px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.diagram-labels h6 {
  margin: 0 0 8px;
  font-size: 15px;
  color: #475569;
}
.diagram-labels dl {
  margin: 0;
  max-height: 240px;
  overflow: auto;
}
.diagram-labels dl > div {
  padding: 6px 0;
  border-top: 1px solid #eef2f7;
}
.diagram-labels dt {
  font-weight: 600;
}
.diagram-labels dd {
  margin: 2px 0 0;
  white-space: pre-wrap;
  color: #475569;
}
figcaption {
  padding: 10px 18px;
  border-top: 1px solid #e2e8f0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
figcaption p {
  margin: 0 0 6px;
}
.diagram-source {
  font-size: 15px;
  color: #475569;
}
.diagram-data {
  margin: 0 18px 14px;
  font-size: 15px;
}
.diagram-data summary {
  color: #4338ca;
  cursor: pointer;
}
.diagram-data pre {
  white-space: pre-wrap;
  word-break: break-word;
  background: #f8fafc;
  padding: 10px;
  max-height: 420px;
  overflow: auto;
  font-size: 14px;
}
.diagram-data table {
  width: 100%;
  border-collapse: collapse;
}
.diagram-data th,
.diagram-data td {
  padding: 6px;
  border-bottom: 1px solid #e2e8f0;
  text-align: left;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.diagram-pending,
.diagram-error {
  padding: 18px;
  margin: 0;
}
.diagram-error span {
  display: block;
  color: #64748b;
  font-size: 15px;
}
.diagram-dialog {
  width: calc(100vw - 64px);
  max-width: 1600px;
  max-height: calc(100vh - 64px);
  padding: 0;
  border: 1px solid #c7d2fe;
  border-radius: 5px;
  color: #172033;
  background: #fff;
}
.diagram-dialog::backdrop {
  background: #0f172a80;
}
.diagram-dialog > p {
  padding: 0 18px;
  white-space: pre-wrap;
}
.diagram-dialog .diagram-scroll {
  max-height: calc(100vh - 240px);
}
.diagram-dialog .diagram-scroll :deep(svg) {
  max-width: none;
}
@container (max-width: 600px) {
  header {
    gap: 10px;
    padding: 12px 14px;
  }
  h5 {
    font-size: 16px;
  }
  .diagram-tools {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    width: 100%;
  }
  button {
    padding: 6px 8px;
    font-size: 15px;
    line-height: 1.5;
    overflow-wrap: anywhere;
  }
  .diagram-scroll {
    padding: 8px;
  }
  .diagram-labels {
    display: block;
  }
  figcaption {
    padding: 10px 14px;
    font-size: 15px;
    line-height: 1.65;
  }
  .diagram-data {
    margin-inline: 14px;
  }
}
@media print {
  .diagram-tools,
  .diagram-data,
  .diagram-dialog {
    display: none;
  }
  .diagram-labels {
    display: none;
  }
  .diagram-scroll {
    overflow: visible;
    max-height: none;
    padding: 0;
  }
  .diagram-scroll :deep(svg) {
    width: 100%;
    max-width: 100%;
  }
  .teaching-diagram {
    break-inside: avoid;
  }
  figcaption {
    font-size: 11pt;
  }
}
</style>
