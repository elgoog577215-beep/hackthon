<template>
  <ul class="tree-mobile-list" :class="{ 'tree-mobile-children': nested }">
    <li v-for="node in nodes" :key="node.id" class="tree-mobile-node">
      <button v-if="node.kind === 'branch'" type="button" class="tree-mobile-item tree-mobile-branch" :class="{ expanded: branchExpanded(node), pending: node.pending }" :data-mobile-branch-id="node.sourceId" :aria-expanded="node.pending ? undefined : branchExpanded(node)" :disabled="Boolean(query.trim()) || node.pending" @click="emit('toggle', node.id)">
        <span class="tree-mobile-copy"><strong>{{ node.label }}</strong><small v-if="node.pending">{{ t('courseKnowledgeStudy.pendingLecture') }}</small><small v-else>{{ node.count }} {{ t('knowledgeProfile.points', '个元知识点') }}<template v-if="showMastery"> · {{ node.progress === null ? t('knowledgeProfile.unassessed') : `${node.progress}%` }}</template></small></span>
        <span v-if="!node.pending" class="tree-mobile-disclosure" aria-hidden="true"><Minus v-if="branchExpanded(node)" :size="16" /><Plus v-else :size="16" /></span>
      </button>
      <button v-else type="button" class="tree-mobile-item tree-mobile-leaf" :class="[showMastery ? node.status : '', { selected: selectedId === node.sourceId }]" :data-mobile-knowledge-id="node.sourceId" :aria-haspopup="showMastery ? 'dialog' : undefined" :aria-current="selectedId === node.sourceId ? 'true' : undefined" :aria-label="showMastery ? `${node.label} · ${node.progress === null ? t('knowledgeProfile.unassessed', '未评估') : `${node.progress}%`}` : node.label" @click="emit('select', node.sourceId, $event.currentTarget as HTMLElement)">
        <span v-if="showMastery" class="tree-mobile-score"><strong>{{ node.progress ?? '—' }}</strong><small v-if="node.progress !== null">%</small></span>
        <span v-else class="tree-mobile-point-icon"><Leaf :size="19" aria-hidden="true" /></span>
        <span class="tree-mobile-copy"><strong>{{ node.label }}</strong><small>{{ showMastery ? t(`knowledgeProfile.${node.status}`) : t('knowledgeFirst.pointDetails') }}</small>
          <span v-if="showMastery" class="tree-mobile-signals" :aria-label="t('knowledgeProfile.signalCounts', '学习信号')">
            <span v-if="node.learningSignals?.red_count" class="tree-mobile-signal is-red"><i aria-hidden="true" />{{ t('knowledgeProfile.redSignal', '待巩固') }} {{ node.learningSignals.red_count }}</span>
            <span v-if="node.learningSignals?.green_count" class="tree-mobile-signal is-green"><i aria-hidden="true" />{{ t('knowledgeProfile.greenSignal', '已理解') }} {{ node.learningSignals.green_count }}</span>
            <span v-if="!node.learningSignals?.red_count && !node.learningSignals?.green_count" class="tree-mobile-signal-empty">{{ t('knowledgeProfile.noSignals', '暂无红绿记录') }}</span>
          </span>
        </span>
      </button>
      <KnowledgeMasteryTreeMobileNodes v-if="node.kind === 'branch' && branchExpanded(node)" :nodes="node.children" :show-mastery="showMastery" :selected-id="selectedId" :collapsed="collapsed" :query="query" nested @toggle="emit('toggle', $event)" @select="(id, trigger) => emit('select', id, trigger)" />
    </li>
  </ul>
</template>

<script setup lang="ts">
import { Minus, Plus, Leaf } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import type { ProfileTreeItem } from '../utils/knowledge-tree-layout'

defineOptions({ name: 'KnowledgeMasteryTreeMobileNodes' })
const props = withDefaults(defineProps<{ nodes: ProfileTreeItem[]; showMastery: boolean; selectedId?: string; collapsed: Set<string>; query: string; nested?: boolean }>(), { selectedId: '', nested: false })
const emit = defineEmits<{ (event: 'toggle', id: string): void; (event: 'select', id: string, trigger: HTMLElement): void }>()

function branchExpanded(node: ProfileTreeItem) {
  return Boolean(node.children.length && (props.query.trim() || !props.collapsed.has(node.id)))
}
</script>

<style scoped>
.tree-mobile-list { display: grid; gap: 7px; min-width: 0; margin: 0; padding: 0; list-style: none; }
.tree-mobile-node { position: relative; min-width: 0; margin: 0; padding: 0; list-style: none; }
.tree-mobile-children { box-sizing: border-box; gap: 7px; margin: 0 0 0 10px; padding: 7px 0 0 10px; border-left: 1px solid #c5b8d4; }
.tree-mobile-children > .tree-mobile-node > .tree-mobile-item::before { content: ''; position: absolute; left: -11px; top: 50%; width: 10px; border-top: 1px solid #c5b8d4; }
.tree-mobile-item { position: relative; box-sizing: border-box; display: flex; align-items: center; gap: 11px; width: 100%; min-height: 64px; padding: 10px 12px; border: 1px solid #e7e1ed; border-radius: 11px; background: #fff; color: #554764; text-align: left; font: inherit; cursor: pointer; }
.tree-mobile-branch { justify-content: space-between; min-height: 58px; border-color: #e2d9ec; background: #f5f1f9; }
.tree-mobile-branch.expanded { background: #faf8fc; }
.tree-mobile-branch.expanded::after { content: ''; position: absolute; left: 10px; top: 50%; bottom: -8px; border-left: 1px solid #c5b8d4; }
.tree-mobile-branch.pending { border-style: dashed; color: #695b72; cursor: default; }
.tree-mobile-copy { display: flex; flex: 1; flex-direction: column; gap: 3px; min-width: 0; }
.tree-mobile-copy > strong { color: #514261; font-size: 16px; font-weight: 600; line-height: 1.4; overflow-wrap: anywhere; }
.tree-mobile-copy > small { color: #70647c; font-size: 13px; line-height: 1.4; }
.tree-mobile-disclosure { display: grid; flex: none; place-items: center; width: 32px; height: 32px; border: 1px solid #d9cde6; border-radius: 50%; background: #fff; color: #725c8a; }
.tree-mobile-score, .tree-mobile-point-icon { display: flex; flex: none; flex-direction: column; align-items: center; justify-content: center; width: 48px; height: 48px; border-radius: 12px; background: #f1edf7; color: #635176; font-variant-numeric: tabular-nums; }
.tree-mobile-score > strong { font-size: 17px; font-weight: 700; line-height: 1.1; }
.tree-mobile-score > small { margin-top: 2px; font-size: 11px; line-height: 1; }
.tree-mobile-point-icon { color: #745d91; }
.tree-mobile-leaf.supported_mastery .tree-mobile-score { background: #eaf5ef; color: #356b56; }
.tree-mobile-leaf.needs_review .tree-mobile-score { background: #fbf1e4; color: #815b2c; }
.tree-mobile-leaf.unassessed .tree-mobile-score { background: #f1edf5; color: #695979; }
.tree-mobile-leaf.selected { border-color: #a88bc9; background: #faf7ff; box-shadow: 0 0 0 2px #c4afe533; }
.tree-mobile-leaf.selected .tree-mobile-copy > strong { color: #68468f; }
.tree-mobile-signals { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 3px; }
.tree-mobile-signal { display: inline-flex; align-items: center; gap: 4px; padding: 3px 6px; border-radius: 6px; font-size: 12px; line-height: 1.3; font-variant-numeric: tabular-nums; }
.tree-mobile-signal > i { width: 7px; height: 7px; flex: none; border-radius: 50%; background: currentColor; }
.tree-mobile-signal.is-red { background: #fbefef; color: #984f54; }
.tree-mobile-signal.is-green { background: #edf6f0; color: #3e735e; }
.tree-mobile-signal-empty { color: #70647c; font-size: 12px; line-height: 1.35; }
.tree-mobile-item:focus-visible { outline: 2px solid #9376be; outline-offset: 3px; }
.tree-mobile-item:disabled { cursor: default; }
@media (hover: hover) { .tree-mobile-item:hover:not(:disabled) { border-color: #cbbadd; background-color: #fbf9fe; } }
@media (hover: none) { .tree-mobile-item:active:not(:disabled) { background-color: #f0eaf8; } }
</style>
