<template>
  <Teleport to="body">
    <div v-if="modelValue" class="course-space-dialog-layer" @keydown.esc="close">
      <button class="course-space-dialog-backdrop" type="button" :aria-label="t('common.cancel')" @click="close" />
      <section ref="dialogRef" class="course-space-dialog" role="dialog" aria-modal="true" aria-labelledby="course-space-dialog-title" tabindex="-1">
        <header>
          <h2 id="course-space-dialog-title">{{ t('courseSpaceCreate.title') }}</h2>
          <button type="button" :aria-label="t('common.close')" :disabled="busy" @click="close"><X :size="17" /></button>
        </header>

        <form @submit.prevent="submit">
          <label class="course-name-field">
            <span>{{ t('courseSpaceCreate.courseName') }}</span>
            <input ref="nameInput" v-model.trim="form.courseName" maxlength="200" autocomplete="off" :placeholder="t('courseSpaceCreate.courseNamePlaceholder')" :disabled="busy" required />
          </label>
          <div class="term-fields">
            <label>
              <span>{{ t('courseSpaceCreate.academicYear') }}</span>
              <input v-model.trim="form.academicYear" maxlength="30" :placeholder="defaultAcademicYear" :disabled="busy" />
            </label>
            <label>
              <span>{{ t('courseSpaceCreate.term') }}</span>
              <select v-model="form.term" :disabled="busy">
                <option value="春季">{{ t('courseSpaceCreate.spring') }}</option>
                <option value="秋季">{{ t('courseSpaceCreate.autumn') }}</option>
              </select>
            </label>
          </div>
          <footer>
            <button type="button" :disabled="busy" @click="close">{{ t('common.cancel') }}</button>
            <button class="primary" type="submit" :disabled="busy || !form.courseName.trim()">
              <LoaderCircle v-if="busy" class="spin" :size="15" />
              <FolderPlus v-else :size="15" />
              {{ t('courseSpaceCreate.submit') }}
            </button>
          </footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { FolderPlus, LoaderCircle, X } from 'lucide-vue-next'
import { t } from '../shared/i18n'

const props = defineProps<{ modelValue: boolean; busy?: boolean }>()
const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'create', payload: { course_name: string; academic_year: string; term: string }): void
}>()

const now = new Date()
const startYear = now.getMonth() >= 7 ? now.getFullYear() : now.getFullYear() - 1
const defaultAcademicYear = `${startYear}-${startYear + 1}`
const defaultTerm = now.getMonth() >= 7 ? '秋季' : '春季'
const dialogRef = ref<HTMLElement | null>(null)
const nameInput = ref<HTMLInputElement | null>(null)
const form = reactive({ courseName: '', academicYear: defaultAcademicYear, term: defaultTerm })
const busy = computed(() => Boolean(props.busy))

function reset() {
  form.courseName = ''
  form.academicYear = defaultAcademicYear
  form.term = defaultTerm
}
function close() {
  if (busy.value) return
  emit('update:modelValue', false)
}
function submit() {
  if (busy.value || !form.courseName.trim()) return
  emit('create', {
    course_name: form.courseName.trim(),
    academic_year: form.academicYear.trim() || defaultAcademicYear,
    term: form.term || defaultTerm,
  })
}

watch(() => props.modelValue, async open => {
  if (!open) return
  reset()
  await nextTick()
  dialogRef.value?.focus()
  nameInput.value?.focus()
})
</script>

<style scoped>
.course-space-dialog-layer,.course-space-dialog-layer *{box-sizing:border-box}.course-space-dialog-layer{position:fixed;inset:0;z-index:2400;display:grid;place-items:center;padding:20px}.course-space-dialog-backdrop{position:absolute;inset:0;border:0;background:rgb(15 23 42/.3)}.course-space-dialog{position:relative;width:min(520px,100%);overflow:hidden;border:1px solid var(--lz-border);border-radius:12px;color:var(--lz-text-primary);background:var(--lz-surface);box-shadow:0 20px 48px rgb(15 23 42/.16);outline:0}.course-space-dialog>header{min-height:60px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 20px;border-bottom:1px solid var(--lz-border)}.course-space-dialog h2{margin:0;color:var(--lz-text-strong);font-size:18px;line-height:1.35}.course-space-dialog header button{width:32px;height:32px;display:grid;place-items:center;flex:none;border:0;border-radius:7px;color:var(--lz-text-muted);background:transparent;cursor:pointer}.course-space-dialog header button:hover{background:var(--lz-fill)}.course-space-dialog form{display:grid;gap:18px;padding:22px 20px 20px}.course-space-dialog label{display:grid;gap:8px;color:var(--lz-text-secondary);font-size:13px;font-weight:700}.course-space-dialog input,.course-space-dialog select{width:100%;height:42px;padding:0 11px;border:1px solid var(--lz-border);border-radius:8px;color:var(--lz-text-primary);background:var(--lz-surface);font:inherit;font-size:13px;outline:0}.course-name-field input{height:44px;font-size:14px}.course-space-dialog input:focus,.course-space-dialog select:focus{border-color:var(--lz-brand);box-shadow:0 0 0 3px var(--lz-brand-soft)}.term-fields{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(130px,.75fr);gap:12px}.course-space-dialog footer{display:flex;justify-content:flex-end;gap:8px;margin:2px -20px -20px;padding:14px 20px;border-top:1px solid var(--lz-border)}.course-space-dialog footer button{height:38px;display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:0 14px;border:1px solid var(--lz-border);border-radius:8px;color:var(--lz-text-secondary);background:var(--lz-surface);font:inherit;font-size:13px;font-weight:700;cursor:pointer}.course-space-dialog footer button.primary{min-width:128px;border-color:var(--lz-brand);color:#fff;background:var(--lz-brand)}.course-space-dialog button:disabled,.course-space-dialog input:disabled,.course-space-dialog select:disabled{opacity:.58;cursor:not-allowed}.spin{animation:course-space-spin .8s linear infinite}@keyframes course-space-spin{to{transform:rotate(360deg)}}
@media(max-width:560px){.course-space-dialog-layer{align-items:end;padding:10px}.course-space-dialog{border-radius:13px}.course-space-dialog>header{padding:16px}.course-space-dialog form{padding:16px}.term-fields{grid-template-columns:1fr}.course-space-dialog footer{margin:2px -16px -16px;padding:12px 16px}.course-space-dialog footer button{flex:1}}
@media(prefers-reduced-motion:reduce){.spin{animation:none}}
</style>
