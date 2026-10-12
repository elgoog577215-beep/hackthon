<template>
  <main class="preview">
    <header>
      <h1>
        {{
          tr("教学图表 · 实际共享渲染", "Teaching diagrams · Shared renderer")
        }}
      </h1>
      <button @click="setLocale(activeLocale === 'zh' ? 'en' : 'zh')">
        {{ activeLocale === "zh" ? "English" : "中文" }}
      </button>
    </header>
    <p>
      {{
        tr(
          "44 种图型均通过讲义和 AI 使用的同一个 Markdown 组件显示。以下为自编样例，不写入正式课程。",
          "All 44 types use the same Markdown component as handouts and AI. These examples do not write course records.",
        )
      }}
    </p>
    <label
      >{{ tr("图型", "Type") }}
      <select v-model="selected">
        <option
          v-for="sample in teachingDiagramSamples"
          :key="sample.type"
          :value="sample.type"
        >
          {{ sample.title }}
        </option>
      </select></label
    ><label
      >{{ tr("显示位置", "Surface") }}
      <select v-model="surface">
        <option value="handout">{{ tr("讲义正文", "Handout") }}</option>
        <option value="answer">{{ tr("AI 回答", "AI answer") }}</option>
      </select></label
    ><label
      ><input type="checkbox" v-model="streaming" />
      {{ tr("检查流式未完成状态", "Inspect incomplete stream") }}</label
    >
    <details>
      <summary>
        {{ tr("检查隔离模型输出", "Inspect isolated model output") }}
      </summary>
      <label class="draft"
        >{{ tr("实验 Markdown", "Experiment Markdown")
        }}<textarea v-model="draft" /></label
      ><button @click="custom = draft">
        {{ tr("显示实验输出", "Show experiment output") }}</button
      ><button @click="custom = ''">
        {{ tr("返回类型示例", "Return to examples") }}
      </button>
    </details>
    <section :class="surface">
      <MarkdownRenderer :content="custom || content" :enable-code-run="false" />
    </section>
  </main>
</template>
<script setup lang="ts">
import { computed, ref } from "vue";
import MarkdownRenderer from "../src/components/MarkdownRenderer.vue";
import { activeLocale, setLocale } from "../src/shared/i18n";
import { teachingDiagramSamples } from "./teaching-diagram-samples";
const selected = ref("flowchart"),
  surface = ref("handout"),
  streaming = ref(false);
const draft = ref(""),
  custom = ref("");
const tr = (zh: string, en: string) => (activeLocale.value === "en" ? en : zh);
const content = computed(
  () =>
    `${tr("图前说明：先看条件，再理解关系。", "Read the conditions before interpreting the relationship.")}\n\n\`\`\`lingzhi-diagram\n${JSON.stringify(teachingDiagramSamples.find((s) => s.type === selected.value))}\n${streaming.value ? "" : "\`\`\`"}\n\n${streaming.value ? "" : tr("图后核对：图中关系和数值是否支持结论？", "Check whether the relationships and values support the conclusion.")}`,
);
</script>
<style scoped>
.preview {
  max-width: 1450px;
  margin: auto;
  padding: 30px;
  color: #172033;
  background: #f8fafc;
  min-height: 100vh;
  font:
    16px/1.7 system-ui,
    "Microsoft YaHei",
    sans-serif;
}
header {
  display: flex;
  justify-content: space-between;
  gap: 20px;
}
h1 {
  font-size: 26px;
}
label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 10px 20px 10px 0;
}
select,
button {
  padding: 6px;
  border: 1px solid #c7d2fe;
  background: white;
  border-radius: 3px;
}
.draft {
  display: flex;
  flex-direction: column;
  align-items: stretch;
}
textarea {
  min-height: 140px;
}
.handout {
  padding: 25px;
  background: white;
  border: 1px solid #e2e8f0;
}
.answer {
  width: 460px;
  max-width: 100%;
  padding: 18px;
  background: white;
  border: 1px solid #c7d2fe;
}
</style>
