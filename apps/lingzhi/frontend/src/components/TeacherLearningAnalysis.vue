<template>
  <section class="teacher-learning-analysis">
    <header class="analysis-heading">
      <div>
        <h1>{{ t("workspaceUi.insights") }}</h1>
        <p>{{ t("workspaceUi.insightsHelp") }}</p>
      </div>
      <button type="button" :disabled="loading" @click="load">
        <RefreshCw :size="16" />{{ t("common.refresh") }}
      </button>
    </header>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">
      {{ copy("正在读取学习反馈…", "Loading learning feedback…") }}
    </p>
    <template v-if="items.length">
      <dl class="analysis-summary">
        <div>
          <dt>{{ copy("收到正式作答", "Formal attempts received") }}</dt>
          <dd>{{ attempts.length }}</dd>
        </div>
        <div>
          <dt>{{ copy("课程提问", "Course questions") }}</dt>
          <dd>{{ questions.length }}</dd>
        </div>
        <div>
          <dt>{{ copy("有反馈的学生", "Students with feedback") }}</dt>
          <dd>{{ studentCount }}</dd>
        </div>
      </dl>
      <div class="analysis-workspace">
        <aside
          class="analysis-filters"
          :aria-label="copy('反馈筛选', 'Feedback filters')"
        >
          <label
            >{{ copy("学生", "Student")
            }}<select v-model="actor">
              <option value="">{{ copy("全部学生", "All students") }}</option>
              <option v-for="id in actors" :key="id" :value="id">
                {{ id }}
              </option>
            </select></label
          >
          <label
            >{{ copy("反馈类型", "Feedback type")
            }}<select v-model="kind">
              <option value="">{{ copy("全部反馈", "All feedback") }}</option>
              <option value="practice_result">
                {{ copy("正式作答", "Formal attempt") }}
              </option>
              <option value="course_question">
                {{ copy("课程提问", "Course question") }}
              </option>
            </select></label
          >
          <label
            >{{ copy("起始日期", "From date")
            }}<input v-model="fromDate" type="date"
          /></label>
        </aside>
        <div class="analysis-list">
          <button
            v-for="item in filtered"
            :key="item.feedback_id"
            type="button"
            :aria-pressed="selected?.feedback_id === item.feedback_id"
            @click="selectedId = item.feedback_id"
          >
            <span>{{ item.actor_id }}</span
            ><strong>{{
              item.kind === "course_question"
                ? item.payload.text
                : resultLabel(item)
            }}</strong
            ><small>{{ dateLabel(item.received_at) }}</small>
          </button>
          <p v-if="!filtered.length">
            {{ copy("该范围内还没有反馈。", "No feedback in this range yet.") }}
          </p>
        </div>
        <article v-if="selected" class="analysis-evidence">
          <h2>{{ copy("对应依据", "Evidence") }}</h2>
          <p>{{ selected.actor_id }} · {{ dateLabel(selected.received_at) }}</p>
          <p>
            {{ copy("发布版本", "Published version") }}：{{
              selected.release_id
            }}
          </p>
          <template v-if="selected.assessment">
            <h3>{{ copy("题目", "Question") }}</h3>
            <p>{{ selected.assessment.task?.prompt }}</p>
            <h3>{{ copy("学生作答", "Student answer") }}</h3>
            <pre>{{ answerText(selected) }}</pre>
            <p>{{ resultLabel(selected) }}</p>
          </template>
          <p v-else>{{ selected.payload.text }}</p>
          <p v-if="selected.reply">
            {{ copy("教师回复", "Teacher reply") }}：{{ selected.reply }}
          </p>
          <button type="button" @click="emit('feedback')">
            {{ copy("查看反馈与回复", "Open feedback & replies") }}
          </button>
        </article>
      </div>
    </template>
    <div v-else-if="!loading && !error" class="analysis-empty">
      <BookOpenCheck :size="32" />
      <h2>{{ t("workspaceUi.insightsEmpty") }}</h2>
      <p>
        {{
          copy(
            "学生学习已发布课程并产生正式反馈后，记录会显示在这里。",
            "Records will appear after students use a published course and send formal feedback.",
          )
        }}
      </p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { BookOpenCheck, RefreshCw } from "lucide-vue-next";
import { activeLocale, t } from "../shared/i18n";
import http, { teacherReadRequestConfig } from "../utils/http";

interface Feedback {
  feedback_id: string;
  actor_id: string;
  kind: string;
  received_at: string;
  release_id: string;
  payload: { text?: string };
  reply?: string;
  assessment?: {
    answer_payload?: Record<string, unknown>;
    result: { passed?: boolean | null; score?: number };
    task?: { prompt?: string };
  };
}
const props = defineProps<{ courseId: string }>();
const emit = defineEmits<{ feedback: [] }>();
const copy = (zh: string, en: string) =>
  activeLocale.value === "en" ? en : zh;
const items = ref<Feedback[]>([]),
  loading = ref(false),
  error = ref("");
const actor = ref(""),
  kind = ref(""),
  fromDate = ref(""),
  selectedId = ref("");
const attempts = computed(() =>
  items.value.filter((item) => item.kind === "practice_result"),
);
const questions = computed(() =>
  items.value.filter((item) => item.kind === "course_question"),
);
const actors = computed(() => [
  ...new Set(items.value.map((item) => item.actor_id)),
]);
const studentCount = computed(() => actors.value.length);
const filtered = computed(() =>
  items.value.filter(
    (item) =>
      (!actor.value || item.actor_id === actor.value) &&
      (!kind.value || item.kind === kind.value) &&
      (!fromDate.value || item.received_at?.slice(0, 10) >= fromDate.value),
  ),
);
const selected = computed(
  () =>
    filtered.value.find((item) => item.feedback_id === selectedId.value) ||
    filtered.value[0],
);
function resultLabel(item: Feedback) {
  return item.assessment?.result.passed === true
    ? copy("本次作答通过", "This attempt passed")
    : item.assessment?.result.passed === false
      ? copy("本次作答需要再练", "This attempt needs practice")
      : copy("本次作答待评阅", "This attempt is pending review");
}
function dateLabel(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleString(activeLocale.value === "en" ? "en-GB" : "zh-CN");
}
function answerText(item: Feedback) {
  return JSON.stringify(item.assessment?.answer_payload || {}, null, 2);
}
let sequence = 0;
let controller: AbortController | undefined;
async function load() {
  const current = ++sequence;
  controller?.abort();
  controller = new AbortController();
  loading.value = true;
  error.value = "";
  try {
    const response = await http.get<{ items: Feedback[] }>(
      `/api/teacher/courses/${encodeURIComponent(props.courseId)}/exchange/feedback`,
      teacherReadRequestConfig({
        signal: controller.signal,
        silentError: true,
      }),
    );
    if (!Array.isArray(response.data.items))
      throw new Error(
        copy(
          "反馈暂时无法读取，请重试。",
          "Feedback could not be read. Please retry.",
        ),
      );
    if (current === sequence) items.value = response.data.items;
  } catch (cause) {
    if (current === sequence)
      error.value =
        cause instanceof Error
          ? cause.message
          : copy("读取反馈失败", "Could not load feedback");
  } finally {
    if (current === sequence) loading.value = false;
  }
}
watch(
  () => props.courseId,
  () => {
    items.value = [];
    actor.value = "";
    kind.value = "";
    fromDate.value = "";
    selectedId.value = "";
    void load();
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  sequence++;
  controller?.abort();
});
</script>

<style scoped>
.teacher-learning-analysis {
  height: 100%;
  min-height: 0;
  overflow: auto;
  padding: 28px;
  color: var(--lz-text);
  background: #fff;
  font-size: 15px;
}
.analysis-heading {
  display: flex;
  justify-content: space-between;
  align-items: start;
  gap: 24px;
}
h1 {
  margin: 0;
  font-size: 24px;
}
h2 {
  margin: 0;
  font-size: 19px;
}
h3 {
  margin: 22px 0 8px;
  font-size: 15px;
}
p {
  color: var(--lz-text-secondary);
  line-height: 1.8;
  overflow-wrap: anywhere;
}
.analysis-heading p {
  max-width: 840px;
}
button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 38px;
  padding: 8px 12px;
  border: 1px solid var(--lz-border);
  border-radius: var(--lz-radius-control);
  background: white;
  font: inherit;
  color: var(--lz-brand-strong);
  cursor: pointer;
}
button:focus-visible,
select:focus-visible,
input:focus-visible {
  outline: 2px solid var(--lz-brand);
  outline-offset: 2px;
}
.analysis-summary {
  display: flex;
  gap: 48px;
  margin: 22px 0;
  padding: 22px 0;
  border-block: 1px solid var(--lz-border);
}
dt {
  color: var(--lz-text-secondary);
}
dd {
  margin: 8px 0 0;
  font-size: 28px;
  color: var(--lz-text-strong);
}
.analysis-workspace {
  display: grid;
  grid-template-columns: 200px minmax(220px, 1fr) minmax(280px, 1fr);
  min-height: 360px;
  gap: 24px;
}
.analysis-filters {
  display: grid;
  align-content: start;
  gap: 20px;
}
.analysis-filters label {
  display: grid;
  gap: 9px;
}
select,
input {
  min-width: 0;
  max-width: 100%;
  padding: 9px;
  border: 1px solid var(--lz-border);
  border-radius: var(--lz-radius-control);
  font: inherit;
  color: var(--lz-text);
  background: #fff;
}
.analysis-list {
  display: grid;
  align-content: start;
  gap: 8px;
}
.analysis-list button {
  display: grid;
  justify-items: start;
  text-align: start;
  color: var(--lz-text);
  padding: 15px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.analysis-list button[aria-pressed="true"] {
  background: var(--lz-brand-soft);
  border-color: var(--lz-brand);
}
.analysis-list small {
  color: var(--lz-text-muted);
  font-size: 13px;
}
.analysis-evidence {
  padding-left: 24px;
  border-left: 1px solid var(--lz-border);
  min-width: 0;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 15px;
}
.analysis-empty {
  padding: 70px 20px;
  text-align: center;
  color: var(--lz-text-secondary);
}
.analysis-empty svg {
  color: var(--lz-brand);
  margin-bottom: 20px;
}
[role="alert"] {
  color: var(--lz-danger);
}
@media (max-width: 1100px) {
  .analysis-workspace {
    grid-template-columns: 170px minmax(0, 1fr);
  }
  .analysis-evidence {
    grid-column: 2;
    padding: 20px 0;
    border-left: 0;
    border-top: 1px solid var(--lz-border);
  }
}
</style>
