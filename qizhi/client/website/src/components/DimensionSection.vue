<template>
  <div class="dimension-section">
    <div class="section-header" @click="expanded = !expanded">
      <div class="section-title-row">
        <h3 class="section-title">{{ title }}</h3>
        <span class="section-score" :class="scoreClass">{{ score }}分</span>
      </div>
      <span class="toggle-icon" :class="{ expanded }">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </span>
    </div>
    <div v-show="expanded" class="section-body">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps<{
  title: string
  score: number
}>()

const expanded = ref(true)

const scoreClass = computed(() => {
  if (props.score >= 80) return 'score-high'
  if (props.score >= 60) return 'score-mid'
  return 'score-low'
})
</script>

<style scoped>
.dimension-section {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  user-select: none;
}

.section-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin: 0;
}

.section-score {
  font-size: 14px;
  font-weight: 700;
  padding: 2px 10px;
  border-radius: 999px;
}

.score-high { background: #e6f7e6; color: #52c41a; }
.score-mid { background: #fff7e6; color: #faad14; }
.score-low { background: #fff1f0; color: #f5222d; }

.toggle-icon {
  color: #999;
  transition: transform 0.2s;
}

.toggle-icon.expanded {
  transform: rotate(180deg);
}

.section-body {
  margin-top: 16px;
}
</style>
