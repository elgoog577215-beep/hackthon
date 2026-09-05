<template>
  <svg class="ppt-scene" :viewBox="`0 0 ${scene.width} ${scene.height}`" role="img" :aria-label="scene.objects.find((o: any) => o.object_id === 'title')?.text">
    <defs><marker :id="markerId" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#305AC7" /></marker></defs>
    <rect :width="scene.width" :height="scene.height" :fill="`#${scene.background}`" />
    <g v-for="obj in scene.objects" :key="obj.object_id" :data-element-id="obj.element_id" :data-subject-id="obj.subject_id" :data-dimension-id="obj.dimension_id">
      <template v-if="obj.kind === 'image'">
        <image v-if="assetUrls[obj.asset_id]" :x="obj.x" :y="obj.y" :width="obj.width" :height="obj.height" :href="assetUrls[obj.asset_id]" preserveAspectRatio="xMidYMid meet" />
        <g v-else role="status"><rect :x="obj.x" :y="obj.y" :width="obj.width" :height="obj.height" fill="#F3F5F9" /><text :x="obj.x + 12" :y="obj.y + 32" font-size="20">{{ assetErrors[obj.asset_id] || !(obj.asset_course_id || courseId) || !(obj.asset_representation_id || representationId) ? t('pptWorkspace.sceneImageUnavailable') : t('pptWorkspace.sceneImageLoading') }}</text></g>
      </template>
      <template v-else>
        <rect :x="obj.x" :y="obj.y" :width="obj.width" :height="obj.height" :fill="`#${obj.fill}`" :stroke="scene.emphasized_element_ids.includes(obj.element_id) ? '#305AC7' : `#${obj.stroke}`" :stroke-width="scene.emphasized_element_ids.includes(obj.element_id) ? 1.5 : 0" />
        <text :x="obj.x + 8" :y="obj.y + 6 + obj.font_size" :fill="`#${obj.color}`" :font-size="obj.font_size" :font-weight="obj.bold ? 700 : 400" :font-family="scene.execution.font_family" xml:space="preserve">
          <tspan v-for="(line, index) in obj.lines" :key="index" :x="obj.x + 8" :dy="index ? obj.font_size * 1.3 : 0">{{ line }}</tspan>
        </text>
      </template>
    </g>
    <g v-for="edge in scene.edges" :key="edge.relation_id" :data-relation-id="edge.relation_id" :data-source="edge.source_id" :data-target="edge.target_id">
      <line :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2" stroke="#305AC7" stroke-width="1.7" :marker-end="['association', 'contrasts', 'equivalent'].includes(edge.kind) ? undefined : `url(#${markerId})`" />
      <text v-if="edge.label_object" :x="edge.label_object.x + 8" :y="edge.label_object.y + 6 + edge.label_object.font_size" :font-size="edge.label_object.font_size" :fill="`#${edge.label_object.color}`" :font-family="scene.execution.font_family" xml:space="preserve"><tspan v-for="(line, index) in edge.label_object.lines" :key="index" :x="edge.label_object.x + 8" :dy="index ? edge.label_object.font_size * 1.3 : 0">{{ line }}</tspan></text>
    </g>
  </svg>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import http from '../utils/http'
import { t } from '../shared/i18n'
const props = defineProps<{ scene: Record<string, any>; courseId?: string; representationId?: string }>()
const assetUrls = ref<Record<string, string>>({})
const assetErrors = ref<Record<string, boolean>>({})
const markerId = computed(() => `arrow-${props.scene.scene_digest}`)
let loadVersion = 0
function clearAssets() { Object.values(assetUrls.value).forEach(URL.revokeObjectURL); assetUrls.value = {}; assetErrors.value = {} }
watch(() => [props.scene.scene_digest, props.courseId, props.representationId], async () => {
  const version = ++loadVersion
  clearAssets()
  for (const obj of props.scene.objects.filter((o: any) => o.kind === 'image')) {
    const owner = obj.asset_course_id || props.courseId
    const representation = obj.asset_representation_id || props.representationId
    if (!owner || !representation) continue
    try {
      const response = await http.get(`/api/courses/${encodeURIComponent(owner)}/teaching-representations/${encodeURIComponent(representation)}/assets/${encodeURIComponent(obj.asset_id)}`, { responseType: 'blob' })
      if (version !== loadVersion) return
      assetUrls.value[obj.asset_id] = URL.createObjectURL(response.data)
    } catch { if (version === loadVersion) assetErrors.value[obj.asset_id] = true }
  }
}, { immediate: true })
onBeforeUnmount(() => { loadVersion++; clearAssets() })
</script>

<style>
@font-face{font-family:'Noto Sans CJK SC';src:url('../../public/presentation-assets/fonts/NotoSansCJKsc-Regular.otf') format('opentype');font-display:block}
.ppt-scene{display:block;width:100%;height:100%;aspect-ratio:16/9;background:#fff}
</style>
