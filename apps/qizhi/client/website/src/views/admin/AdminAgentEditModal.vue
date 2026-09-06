<template>
  <Teleport to="body">
    <div v-if="modelValue" class="agent-modal-overlay" @click.self="onCancel">
      <div class="agent-modal-box" role="dialog" aria-modal="true">
        <header class="agent-modal-header">
          <h3>{{ isEdit ? '编辑智能体' : '新建智能体' }}</h3>
          <button type="button" class="agent-modal-close" @click="onCancel" :disabled="pending">&times;</button>
        </header>

        <form class="agent-modal-form" @submit.prevent="onSubmit">
          <div class="form-row">
            <label class="form-label">
              <span>标题<span class="required">*</span></span>
              <input v-model="form.title" type="text" maxlength="80" required />
            </label>
            <label class="form-label">
              <span>排序（越小越靠前）</span>
              <input v-model.number="form.sort_order" type="number" />
            </label>
          </div>

          <label class="form-label">
            <span>描述<span class="required">*</span></span>
            <textarea v-model="form.description" rows="3" required></textarea>
          </label>

          <label class="form-label">
            <span>标签（用英文逗号分隔，例如 <code>#dialog,#Mo</code>）</span>
            <input v-model="tagsRaw" type="text" />
          </label>

          <div class="form-row">
            <label class="form-label">
              <span>标签底色（hex）</span>
              <input v-model="form.badge_bg" type="text" placeholder="#DEE8FF" />
            </label>
            <label class="form-label">
              <span>标签前景色（hex）</span>
              <input v-model="form.badge_fg" type="text" placeholder="#2F4AA6" />
            </label>
          </div>

          <label class="form-label">
            <span>图标 SVG path<span class="required">*</span>（请粘贴 SVG path 的 d 属性值）</span>
            <textarea v-model="form.icon_path" rows="3" required></textarea>
          </label>

          <div class="form-row">
            <label class="form-label">
              <span>外链 URL（如填写则优先生效）</span>
              <input v-model="form.href" type="text" placeholder="https://..." />
            </label>
            <label class="form-label">
              <span>内部路由（外链为空时跳转）</span>
              <input v-model="form.route_to" type="text" placeholder="/" />
            </label>
          </div>

          <div class="form-row form-row-checks">
            <label class="form-check">
              <input v-model="form.popular" type="checkbox" />
              <span>标记为热门（POPULAR）</span>
            </label>
            <label class="form-check">
              <input v-model="form.enabled" type="checkbox" />
              <span>上架（在首页广场展示）</span>
            </label>
          </div>

          <label class="form-label">
            <span>card_key（稳定标识，可选）</span>
            <input v-model="form.card_key" type="text" placeholder="留空则不设置" />
          </label>

          <div v-if="errorText" class="form-error">{{ errorText }}</div>

          <footer class="agent-modal-footer">
            <button type="button" class="btn-secondary" @click="onCancel" :disabled="pending">取消</button>
            <button type="submit" class="btn-primary" :disabled="pending">
              {{ pending ? '提交中...' : (isEdit ? '保存' : '创建') }}
            </button>
          </footer>
        </form>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { operateAdminAgent } from '../../api/admin'
import { OperationEnum, type AdminAgentDetail } from '../../api/types'

const props = defineProps<{
  modelValue: boolean
  agent: AdminAgentDetail | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: []
}>()

const isEdit = computed(() => Boolean(props.agent?.id))

interface FormState {
  card_key: string
  title: string
  description: string
  popular: boolean
  badge_bg: string
  badge_fg: string
  icon_path: string
  href: string
  route_to: string
  enabled: boolean
  sort_order: number | null
}

function defaultForm(): FormState {
  return {
    card_key: '',
    title: '',
    description: '',
    popular: false,
    badge_bg: '#DEE8FF',
    badge_fg: '#2F4AA6',
    icon_path: '',
    href: '',
    route_to: '',
    enabled: false,
    sort_order: null,
  }
}

const form = ref<FormState>(defaultForm())
const tagsRaw = ref('')
const pending = ref(false)
const errorText = ref('')

watch(
  () => [props.modelValue, props.agent],
  () => {
    if (!props.modelValue) return
    errorText.value = ''
    pending.value = false
    if (props.agent) {
      form.value = {
        card_key: props.agent.card_key ?? '',
        title: props.agent.title,
        description: props.agent.description,
        popular: Boolean(props.agent.popular),
        badge_bg: props.agent.badge_bg,
        badge_fg: props.agent.badge_fg,
        icon_path: props.agent.icon_path,
        href: props.agent.href ?? '',
        route_to: props.agent.route_to ?? '',
        enabled: Boolean(props.agent.enabled),
        sort_order: props.agent.sort_order,
      }
      tagsRaw.value = (props.agent.tags ?? []).join(',')
    } else {
      form.value = defaultForm()
      tagsRaw.value = ''
    }
  },
  { immediate: true },
)

function parseTags(raw: string): string[] {
  return raw
    .split(/[,，]/)
    .map((t) => t.trim())
    .filter((t) => t.length > 0)
}

function onCancel() {
  if (pending.value) return
  emit('update:modelValue', false)
}

async function onSubmit() {
  errorText.value = ''
  if (!form.value.title.trim()) {
    errorText.value = '请填写标题'
    return
  }
  if (!form.value.description.trim()) {
    errorText.value = '请填写描述'
    return
  }
  if (!form.value.icon_path.trim()) {
    errorText.value = '请粘贴 SVG path 的 d 属性值'
    return
  }

  pending.value = true
  try {
    await operateAdminAgent({
      operation: isEdit.value ? OperationEnum.UPDATE : OperationEnum.CREATE,
      id: props.agent?.id ?? null,
      card_key: form.value.card_key.trim() || null,
      title: form.value.title.trim(),
      description: form.value.description.trim(),
      tags: parseTags(tagsRaw.value),
      popular: form.value.popular,
      badge_bg: form.value.badge_bg.trim() || '#DEE8FF',
      badge_fg: form.value.badge_fg.trim() || '#2F4AA6',
      icon_path: form.value.icon_path.trim(),
      href: form.value.href.trim() || null,
      route_to: form.value.route_to.trim() || null,
      enabled: form.value.enabled,
      sort_order: form.value.sort_order ?? null,
    })
    emit('update:modelValue', false)
    emit('saved')
  } catch (e) {
    errorText.value = e instanceof Error ? e.message : '提交失败'
  } finally {
    pending.value = false
  }
}
</script>

<style scoped>
.agent-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: var(--z-modal-overlay, 1200);
  display: flex;
  align-items: center;
  justify-content: center;
}

.agent-modal-box {
  background: #fff;
  border-radius: 16px;
  width: 90%;
  max-width: 720px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 16px 48px rgba(15, 28, 58, 0.2);
}

.agent-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px;
  border-bottom: 1px solid #eef1f6;
}

.agent-modal-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1a2540;
}

.agent-modal-close {
  border: none;
  background: none;
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
  color: #8a93a6;
}

.agent-modal-close:hover:not(:disabled) {
  color: #1a2540;
}

.agent-modal-form {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.form-row-checks {
  grid-template-columns: repeat(2, max-content);
}

.form-label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: #4b5670;
  font-weight: 500;
}

.form-label code {
  background: #f0f4fb;
  padding: 0 4px;
  border-radius: 4px;
  font-size: 12px;
}

.form-label input[type='text'],
.form-label input[type='number'],
.form-label textarea {
  width: 100%;
  border: 1px solid #d8deea;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 14px;
  color: #1a2540;
  font-family: inherit;
  background: #fff;
  box-sizing: border-box;
}

.form-label textarea {
  resize: vertical;
  min-height: 60px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.form-label input:focus,
.form-label textarea:focus {
  outline: none;
  border-color: #4467d9;
}

.form-check {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #4b5670;
  cursor: pointer;
}

.required {
  color: #d32f2f;
  margin-left: 2px;
}

.form-error {
  color: #c62828;
  font-size: 13px;
}

.agent-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 8px;
}

.btn-primary,
.btn-secondary {
  height: 36px;
  padding: 0 18px;
  border-radius: 8px;
  font-size: 14px;
  border: none;
  cursor: pointer;
}

.btn-primary {
  background: #2f4aa6;
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: #243a85;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: #f0f4fb;
  color: #1f3c8b;
}

.btn-secondary:hover:not(:disabled) {
  background: #dde6f8;
}

.btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@media (max-width: 720px) {
  .form-row {
    grid-template-columns: 1fr;
  }
}
</style>
