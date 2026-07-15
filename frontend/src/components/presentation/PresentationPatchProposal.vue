<script setup lang="ts">
import { computed } from 'vue'
import type { PresentationProposal } from '@/types/presentation'

const props = defineProps<{
  proposal: PresentationProposal
  applying?: boolean
}>()

defineEmits<{
  apply: []
  cancel: []
  compare: []
}>()

const plainText = (value: unknown): string => {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

const summarizeBlocks = (value: unknown): string[] => {
  if (!Array.isArray(value)) return []
  return value
    .filter((block): block is Record<string, unknown> => Boolean(block && typeof block === 'object'))
    .map((block) => {
      const title = plainText(block.title)
      const content = plainText(block.content)
      const items = Array.isArray(block.items)
        ? block.items.map(plainText).filter(Boolean).slice(0, 2).join('；')
        : ''
      const detail = content || items
      return [title, detail].filter(Boolean).join('：')
    })
    .filter(Boolean)
    .slice(-3)
}

const summarizeChanges = (value: unknown): string => {
  if (typeof value === 'string') return value
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return plainText(value) || '按建议调整本页内容'
  }

  const changes = value as Record<string, unknown>
  const lines = [
    ...summarizeBlocks(changes.blocks),
    plainText(changes.title) ? `标题：${plainText(changes.title)}` : '',
    plainText(changes.key_message) ? `核心信息：${plainText(changes.key_message)}` : '',
    plainText(changes.speaker_notes) ? `讲稿备注：${plainText(changes.speaker_notes)}` : '',
    plainText(changes.layout_id) ? `版式：${plainText(changes.layout_id)}` : '',
  ].filter(Boolean)
  return lines.slice(0, 4).join('\n') || '按建议调整本页内容'
}

const diff = computed(() => {
  const patch = props.proposal.patches[0] || {}
  const before = summarizeChanges(patch.before || patch.old_value || patch.previous || '保留当前内容与来源锚点')
  const after = summarizeChanges(patch.after || patch.value || patch.changes || '按建议调整本页内容')
  return { before, after }
})
</script>

<template>
  <section class="patch-proposal" :class="{ stale: proposal.status === 'stale' }">
    <h3>✦ 建议：{{ proposal.summary || '调整当前课件' }}</h3>
    <p>
      {{ proposal.scope === 'slide' ? `仅影响 ${proposal.slide_ids.length || 1} 页` : '影响整套课件' }}
      · 保留课程来源锚点
    </p>
    <div class="diff-grid" aria-label="修改前后对比">
      <div class="before"><b>修改前</b><span>{{ diff.before }}</span></div>
      <div class="after"><b>修改后</b><span>{{ diff.after }}</span></div>
    </div>
    <ul v-if="proposal.risks.length" class="risks">
      <li v-for="risk in proposal.risks" :key="risk">{{ risk }}</li>
    </ul>
    <div v-if="proposal.status === 'stale'" class="stale-note">课件已有新版本，请重新生成建议。</div>
    <div class="proposal-actions">
      <button type="button" @click="$emit('compare')">查看对比</button>
      <button class="apply" type="button" :disabled="applying || proposal.status === 'stale'" @click="$emit('apply')">
        {{ applying ? '应用中…' : '应用修改' }}
      </button>
      <button type="button" :disabled="applying" @click="$emit('cancel')">取消</button>
    </div>
  </section>
</template>

<style scoped>
.patch-proposal{border:1px solid #dddff1;border-radius:10px;padding:14px;background:#fcfcff}.patch-proposal.stale{border-color:#fed7aa;background:#fffaf5}.patch-proposal h3{margin:0;color:#1e293b;font-size:14px}.patch-proposal>p{margin:5px 0 12px;color:#64748b;font-size:12px}.diff-grid{display:grid;grid-template-columns:1fr 1fr;overflow:hidden;border:1px solid #e8e8ec;border-radius:7px;font-size:12px}.diff-grid>div{min-width:0;padding:10px;white-space:pre-wrap;overflow-wrap:anywhere}.diff-grid b{display:block;margin-bottom:6px;font-size:11px}.diff-grid span{line-height:1.58}.before{color:#a33;background:#fff7f5}.after{border-left:1px solid #e8e8ec;color:#176c4e;background:#f3fbf7}.risks{margin:10px 0 0;padding-left:20px;color:#b45309;font-size:12px}.stale-note{margin-top:10px;color:#b45309;font-size:12px}.proposal-actions{display:flex;gap:8px;margin-top:12px}.proposal-actions button{min-height:38px;flex:1;border:1px solid #dfe3eb;border-radius:8px;color:#475569;background:#fff}.proposal-actions button.apply{border-color:#6366f1;color:#fff;background:#6366f1}.proposal-actions button:disabled{opacity:.55;cursor:not-allowed}@media(max-width:390px){.diff-grid{grid-template-columns:1fr}.after{border-top:1px solid #e8e8ec;border-left:0}.proposal-actions{flex-wrap:wrap}.proposal-actions button{flex-basis:calc(50% - 4px)}}
</style>
