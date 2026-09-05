<template>
  <div v-if="visible" class="modal-overlay">
    <div class="modal-content create-resource-modal">
      <div class="modal-header">
        <h3>创建资源</h3>
        <button type="button" class="modal-close" @click="handleClose" aria-label="关闭">&times;</button>
      </div>
      <div class="modal-body">
        <div class="form-row">
          <label>资源名称</label>
          <input v-model.trim="form.name" type="text" class="form-input" placeholder="请输入资源名称" />
        </div>
        <div v-if="!props.initialResourceType" class="form-row">
          <label>资源类型</label>
          <select v-model="form.resourceType" class="form-select">
            <option value="outline">教学大纲</option>
            <option value="teaching_plan">教案</option>
            <option value="question_bank">题目</option>
            <option value="ppt">PPT</option>
          </select>
        </div>
        <div class="form-row">
          <label>绑定课程</label>
          <select v-model="form.courseId" class="form-select" @change="onCourseChange">
            <option value="">不绑定课程</option>
            <option v-for="c in courses" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
        </div>
        <div class="form-row">
          <label>绑定章节</label>
          <select v-model="form.unitId" class="form-select" :disabled="!form.courseId">
            <option value="">不绑定到具体章节</option>
            <option v-for="u in flattenedUnits" :key="u.id" :value="u.id">{{ u.indent }}{{ u.name }}</option>
          </select>
        </div>
        <div v-if="form.resourceType === 'teaching_plan' || form.resourceType === 'question_bank'" class="form-row">
          <label>{{ form.resourceType === 'question_bank' ? '选择参考教案' : '选择教学大纲' }} <span class="required">*</span></label>
          <select v-model="form.outlineId" class="form-select" required>
            <option value="">{{ form.resourceType === 'question_bank' ? '请选择参考教案' : '请选择教学大纲' }}</option>
            <option v-for="o in outlineList" :key="o.id" :value="o.id">{{ o.name }}</option>
          </select>
          <p v-if="outlineLoading" class="form-hint">加载中...</p>
          <p v-else-if="outlineList.length === 0" class="form-hint">
            {{ form.resourceType === 'question_bank' ? '暂无可用教案，请先创建教案' : '暂无可用教学大纲，请先创建教学大纲' }}
          </p>
        </div>
        <p v-if="submitError" class="form-error">{{ submitError }}</p>
      </div>
      <div class="modal-footer">
        <button type="button" class="action-btn secondary" @click="handleClose">取消</button>
        <button type="button" class="action-btn" :disabled="!canSubmit || submitting" @click="handleSubmit">
          {{ submitting ? '创建中...' : '创建并进入' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useUserStore } from '../stores/user'
import { listCourses, listUnitsByCourse } from '../api/course'
import { listResources, operateResource } from '../api/resource'
import type { CourseListItem, UnitListItem } from '../api/types'
import type { ResourceResponse } from '../api/types'
import { OperationEnum, ResourceTypeEnum } from '../api/types'

const props = withDefaults(
  defineProps<{
    visible: boolean
    initialCourseId?: string
    initialUnitId?: string
    initialResourceType?: string
    initialName?: string
  }>(),
  {
    initialCourseId: '',
    initialUnitId: '',
    initialResourceType: '',
    initialName: '',
  }
)

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'created', id: string, outlineId?: string): void
}>()

const userStore = useUserStore()

const form = ref({
  name: '',
  resourceType: 'outline',
  courseId: '',
  unitId: '',
  outlineId: '',
})
const courses = ref<CourseListItem[]>([])
const units = ref<UnitListItem[]>([])
const outlineList = ref<ResourceResponse[]>([])
const outlineLoading = ref(false)
const submitting = ref(false)
const submitError = ref('')

/** 创建并进入按钮是否可点：有名称；若为教案则必须已选教学大纲，若为题目则必须已选教案 */
const canSubmit = computed(() => {
  if (!form.value.name.trim()) return false
  if (
    (form.value.resourceType === 'teaching_plan' || form.value.resourceType === 'question_bank') &&
    !form.value.outlineId
  ) {
    return false
  }
  return true
})

const flattenedUnits = computed(() => {
  const list: { id: string; name: string; indent: string }[] = []
  function walk(nodes: UnitListItem[], depth: number) {
    for (const u of nodes) {
      list.push({ id: u.detail.id, name: u.detail.name, indent: '　'.repeat(depth) })
      if (u.children?.length) walk(u.children, depth + 1)
    }
  }
  walk(units.value, 0)
  return list
})

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      form.value = {
        name: props.initialName || '',
        resourceType: props.initialResourceType || 'outline',
        courseId: props.initialCourseId || '',
        unitId: props.initialUnitId || '',
        outlineId: '',
      }
      submitError.value = ''
      loadCourses()
      if (props.initialCourseId) loadUnits(props.initialCourseId)
      else units.value = []
      if (form.value.resourceType === 'teaching_plan' || form.value.resourceType === 'question_bank') loadOutlineList()
    }
  }
)

watch(
  () => form.value.resourceType,
  (type) => {
    if (type === 'teaching_plan' || type === 'question_bank') loadOutlineList()
    else form.value.outlineId = ''
  }
)

async function loadCourses() {
  try {
    courses.value = await listCourses()
  } catch {
    courses.value = []
  }
}

async function onCourseChange() {
  form.value.unitId = ''
  if (!form.value.courseId) {
    units.value = []
    return
  }
  await loadUnits(form.value.courseId)
}

async function loadUnits(courseId: string) {
  try {
    units.value = await listUnitsByCourse(courseId)
  } catch {
    units.value = []
  }
}

async function loadOutlineList() {
  outlineLoading.value = true
  try {
    // 参考资源列表不按绑定课程筛选：新建资源尚未绑定，参考大纲/教案多为未绑定或其它课程
    const params: { resource_type: ResourceTypeEnum; user_id?: string } = {
      resource_type: form.value.resourceType === 'question_bank' ? ResourceTypeEnum.TeachingPlan : ResourceTypeEnum.Outline,
    }
    if (userStore.currentUser?.id) params.user_id = userStore.currentUser.id
    outlineList.value = await listResources(params)
  } catch {
    outlineList.value = []
  } finally {
    outlineLoading.value = false
  }
}

function handleClose() {
  emit('close')
}

async function handleSubmit() {
  if (!form.value.name.trim()) return
  if (
    (form.value.resourceType === 'teaching_plan' || form.value.resourceType === 'question_bank') &&
    !form.value.outlineId
  ) {
    submitError.value = form.value.resourceType === 'question_bank' ? '请选择参考教案' : '请选择教学大纲'
    return
  }
  submitting.value = true
  submitError.value = ''
  try {
    const resourceType =
      form.value.resourceType === 'teaching_plan'
        ? ResourceTypeEnum.TeachingPlan
        : form.value.resourceType === 'question_bank'
          ? ResourceTypeEnum.QuestionBank
          : form.value.resourceType === 'ppt'
            ? ResourceTypeEnum.Ppt
            : ResourceTypeEnum.Outline
    // 教案/习题集选择的参考大纲/教案同时作为父资源，挂入层级链（版本号按父作用域分配）
    const parentResourceId =
      form.value.resourceType === 'teaching_plan' || form.value.resourceType === 'question_bank'
        ? form.value.outlineId || undefined
        : undefined
    // 课程/章节/父资源直接随 create 提交，保证版本号在正确作用域内计算
    const id = await operateResource({
      operation: OperationEnum.CREATE,
      name: form.value.name.trim(),
      resource_type: resourceType,
      editable: true,
      related_user_id: userStore.currentUser?.id ?? undefined,
      related_course_id: form.value.courseId || null,
      related_unit_id: form.value.unitId || null,
      parent_resource_id: parentResourceId ?? null,
    })
    if (!id) throw new Error('创建成功但未返回资源 id')
    const outlineId =
      form.value.resourceType === 'teaching_plan' || form.value.resourceType === 'question_bank'
        ? form.value.outlineId || undefined
        : undefined
    emit('created', id, outlineId)
    emit('close')
  } catch (err) {
    submitError.value = err instanceof Error ? err.message : '创建失败'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal-overlay, 1200);
}
.create-resource-modal {
  background: #fff;
  border-radius: 12px;
  width: min(440px, calc(100vw - 24px));
  min-width: 0;
  max-width: 90vw;
  max-height: calc(100vh - 32px);
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #eee;
}
.modal-header h3 {
  margin: 0;
  font-size: 18px;
}
.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
  color: #666;
  padding: 0 4px;
}
.modal-close:hover {
  color: #333;
}
.modal-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1 1 auto;
  min-height: 0;
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid #eee;
}
.form-row {
  margin-bottom: 14px;
}
.form-row label {
  display: block;
  margin-bottom: 6px;
  font-size: 14px;
  color: #333;
}
.form-input,
.form-select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
  box-sizing: border-box;
}
.form-input:focus,
.form-select:focus {
  outline: none;
  border-color: #1a73e8;
}
.form-row .required {
  color: #d32f2f;
}
.form-hint {
  margin: 4px 0 0;
  font-size: 12px;
  color: #666;
}
.form-error {
  margin: 12px 0 0;
  font-size: 13px;
  color: #d32f2f;
}
.action-btn {
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  border: 1px solid #e0e0e0;
  background: #fff;
  color: #333;
}
.action-btn:hover:not(:disabled) {
  border-color: #C5D9FF;
  background: #f8f9ff;
}
.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.action-btn.secondary {
  background: #f5f5f5;
}
</style>
