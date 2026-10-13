<template>
  <main class="interaction-preview">
    <header><h1>{{ tr('讲义与助手 · 使用流程检查', 'Handout and assistant · Interaction review') }}</h1><button @click="setLocale(activeLocale === 'zh' ? 'en' : 'zh')">{{ activeLocale === 'zh' ? 'English' : '中文' }}</button></header>
    <p>{{ tr('公开自编演示；回复在本页模拟，不访问模型或正式资料，不写入课程。可检查等待、引用、切换、重开和阅读位置。', 'Public synthetic demo. Replies are simulated in this page, without model calls or course writes. Inspect waiting, quotation, switching, reopening and reading position.') }}</p>
    <nav>
      <button @click="chapter = chapter === 1 ? 2 : 1; quote = ''">{{ tr('切换当前章节', 'Switch chapter') }}</button>
      <button @click="quote = 'u=(1,2), v=(2,1), u+2v=(5,4)'">{{ tr('引用例题', 'Quote example') }}</button>
      <button @click="showAssistant = !showAssistant">{{ showAssistant ? tr('切到笔记', 'Open notes') : tr('回到助手', 'Return to assistant') }}</button>
    </nav>
    <div class="reading-workspace">
      <article class="reading"><h2>{{ context.section_title }}</h2><p>{{ tr('向量的两个分量分别运算；平移改变起点，不改变方向和长度。', 'Compute vector components separately. Translation changes the starting point while preserving direction and length.') }}</p>
        <MarkdownRenderer :content="diagram" :enable-code-run="false" />
      </article>
      <aside>
        <PersonalHandoutAssistant v-if="showAssistant" owner-id="public-usability-demo" material-id="public-vector-demo" revision-id="public-demo-v1" :context="context" @clear-quote="quote = ''" />
        <section v-else class="notes"><h2>{{ tr('我的笔记', 'My notes') }}</h2><p>{{ tr('切回助手时，未发送的问题和已生成的回复仍会保留。', 'Return to the assistant to retain the unsent question and generated reply.') }}</p><textarea v-model="note" :aria-label="tr('演示笔记', 'Demo notes')" rows="10" /></section>
      </aside>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import PersonalHandoutAssistant from '../src/components/PersonalHandoutAssistant.vue'
import MarkdownRenderer from '../src/components/MarkdownRenderer.vue'
import { studyApi, type AssistantConversation, type AssistantContext } from '../src/api/study'
import { activeLocale, setLocale } from '../src/shared/i18n'
import { teachingDiagramSamples } from './teaching-diagram-samples'

const tr = (zh: string, en: string) => activeLocale.value === 'en' ? en : zh
const chapter = ref(1), quote = ref(''), note = ref(''), showAssistant = ref(true)
const context = computed<AssistantContext>(() => ({ section_id: `section-${chapter.value}`,
  section_title: chapter.value === 1 ? tr('第一章 · 向量组合', 'Chapter 1 · Vector combinations') : tr('第二章 · 组合的几何意义', 'Chapter 2 · Geometry of combinations'),
  block_id: quote.value ? 'example-1' : '', block_title: quote.value ? tr('向量例题', 'Vector example') : '', quote: quote.value }))
const sample = teachingDiagramSamples.find(item => item.type === 'vector_plot')!
const diagram = '```lingzhi-diagram\n' + JSON.stringify(sample) + '\n```'
const conversation: AssistantConversation = { conversation_id: 'public-demo', messages: [] }
const requests = new Map<string, AssistantConversation>()
const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))
// These adapters belong only to this dev document. The production entry does
// not import this page; no model, API, formal course or learner record is used.
studyApi.assistant = async () => { await delay(450); return structuredClone(conversation) }
studyApi.ask = async (_id, body) => {
  if (requests.has(body.request_id)) return structuredClone(conversation)
  const bound: AssistantContext = { section_id: body.section_id,
    section_title: context.value.section_title, block_id: body.block_id,
    block_title: context.value.block_title, quote: body.quote }
  const message = { message_id: body.request_id + ':reply', role: 'assistant' as const,
    content: '', status: 'running', context_ref: bound, task_ref: { task_id: body.request_id } }
  conversation.messages.push({ message_id: body.request_id + ':question', role: 'user', content: body.text, status: 'complete', context_ref: bound }, message)
  requests.set(body.request_id, conversation)
  const english = body.language === 'en'
  setTimeout(() => { message.content = english ? 'Compute 2v=(4,2), then add u=(1,2) to obtain w=(5,4).' : '先算 2v=(4,2)，再加上 u=(1,2)，得到 w=(5,4)。' }, 700)
  setTimeout(() => { message.content += '\n\n' + Array.from({ length: 7 }, (_, i) => english ? `Step ${i + 1}: keep the same coordinate scale. A translated vector retains its components; the connecting endpoint is (5,4).` : `第 ${i + 1} 步：横纵坐标采用相同尺度。向量平移后仍保留原分量，首尾连接后的终点为 (5,4)。`).join('\n\n') + '\n\n' + diagram; message.status = 'complete' }, 2200)
  await delay(250)
  return structuredClone(conversation)
}
</script>

<style scoped>
.interaction-preview{padding:24px;max-width:1340px;margin:auto;color:#34435d;font:15px/1.7 var(--handout-sans)}header{display:flex;align-items:center;justify-content:space-between}h1{font-size:24px}nav{display:flex;gap:12px;margin:18px 0}button{padding:8px 12px;border:1px solid #d8dfee;border-radius:8px;color:#6651a7;background:white;font:inherit;cursor:pointer}.reading-workspace{display:grid;grid-template-columns:minmax(0,1fr) 390px;gap:24px}.reading{background:white;padding:24px;border:1px solid #dde2ef;border-radius:12px}aside{display:flex;height:680px;min-width:0;border:1px solid #dde2ef;border-radius:12px;background:white;overflow:hidden}.notes{padding:20px;width:100%}textarea{width:100%;box-sizing:border-box;font:inherit;border:1px solid #d8dfee;border-radius:8px;padding:10px}
</style>
