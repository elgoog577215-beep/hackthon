<template>
  <CourseWorkspaceHeaderAction v-if="!embedded" :label="copy('学生授权', 'Student access')" :display-label="copy('学生授权', 'Access')" @click="open = !open"><UsersRound :size="16" /></CourseWorkspaceHeaderAction>
  <Teleport to="body" :disabled="embedded"><div v-if="open || embedded" :class="{ 'grant-backdrop': !embedded }" @click.self="open = false"><section class="grant-panel" :class="{ 'is-embedded': embedded }" :role="embedded ? 'region' : 'dialog'" :aria-modal="embedded ? undefined : true" :aria-label="copy('学生授权', 'Student access')" @keydown.esc="open = false"><header><h2>{{ copy('课程学习授权', 'Course learning access') }}</h2><button v-if="!embedded" @click="open = false">{{ copy('关闭', 'Close') }}</button></header><p>{{ copy('授权学生阅读讲义、练习和生成个人学习材料。学生不能修改教师正文。', 'Allow students to read, practise and derive personal materials. Students cannot edit teacher content.') }}</p><form @submit.prevent="grant"><label>{{ copy('学生身份 ID（本地可填写用户名）', 'Student identity ID (or a local username)') }}<input v-model="identity" required maxlength="160" /></label><button :disabled="busy || !identity.trim()">{{ copy('授权', 'Grant access') }}</button></form><p v-if="error" role="alert">{{ error }}</p><ul><li v-for="item in grants" :key="item.grant_id"><span>{{ item.label }}<small>{{ item.status === 'active' ? copy('已授权', 'Active') : copy('已撤销', 'Revoked') }}</small></span><button v-if="item.status === 'active'" :disabled="busy" @click="revoke(item.learner_id)">{{ copy('撤销授权', 'Revoke access') }}</button></li></ul><p>{{ copy('撤销后停止新的读取和学习操作，学生已有笔记与作答保留。', 'Revocation stops new access and learning actions; existing notes and attempts are retained.') }}</p></section></div></Teleport>
</template>
<script setup lang="ts">
import { ref, watch } from 'vue'
import http, { teacherRequestConfig } from '../utils/http'
import { activeLocale } from '../shared/i18n'
import { UsersRound } from 'lucide-vue-next'
import CourseWorkspaceHeaderAction from './CourseWorkspaceHeaderAction.vue'
const props = withDefaults(defineProps<{ courseId: string; embedded?: boolean }>(), { embedded: false })
const copy = (zh: string, en: string) => activeLocale.value === 'en' ? en : zh
const open = ref(false), busy = ref(false), error = ref(''), identity = ref('')
const grants = ref<{ grant_id: string; learner_id: string; label: string; status: string }[]>([])
const endpoint = () => `/api/teacher/courses/${encodeURIComponent(props.courseId)}/learners`
let sequence = 0
async function load() { const current = ++sequence; try { const { data } = await http.get(endpoint(), teacherRequestConfig()); if (current === sequence) grants.value = Array.isArray(data) ? data : [] } catch (cause) { error.value = cause instanceof Error ? cause.message : copy('读取失败', 'Could not load access') } }
async function grant() { busy.value = true; error.value = ''; try { const value = identity.value.trim(); await http.post(endpoint(), value.startsWith('qizhi:') || value.startsWith('local-student:') ? { learner_id: value } : { local_username: value }, teacherRequestConfig()); identity.value = ''; await load() } catch (cause) { error.value = cause instanceof Error ? cause.message : copy('授权失败', 'Could not grant access') } finally { busy.value = false } }
async function revoke(id: string) { busy.value = true; error.value = ''; try { await http.delete(`${endpoint()}/${encodeURIComponent(id)}`, teacherRequestConfig()); await load() } catch (cause) { error.value = cause instanceof Error ? cause.message : copy('撤销失败', 'Could not revoke access') } finally { busy.value = false } }
watch([open, () => props.courseId], () => { sequence++; grants.value = []; error.value = ''; if (open.value || props.embedded) void load() }, { immediate: props.embedded })
</script>
<style scoped>
button, input { font: inherit; font-size: 15px; }
button { min-height: 40px; padding: 8px 14px; border: 1px solid var(--lz-border); border-radius: 8px; color: var(--lz-text); background: #fff; font-weight: 600; line-height: 1.4; cursor: pointer; }
button:hover { color: var(--lz-brand-strong); border-color: var(--lz-brand); }
button:disabled { opacity: .55; cursor: not-allowed; }
.grant-backdrop { position: fixed; inset: 0; z-index: 2100; display: grid; place-items: center; padding: 24px; background: rgba(30, 41, 59, .42); }
.grant-panel { width: min(620px, 100%); max-height: calc(100dvh - 48px); overflow: auto; padding: 24px; border: 1px solid var(--lz-border); border-radius: var(--lz-radius-surface); color: var(--lz-text); background: #fff; box-shadow: var(--lz-shadow-overlay); font: inherit; font-size: 15px; line-height: 1.6; }
header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
h2 { margin: 0; font-family: inherit; font-size: 20px; font-weight: 700; line-height: 1.4; color: var(--lz-text-strong); }
form { display: flex; align-items: end; gap: 12px; flex-wrap: wrap; margin: 20px 0; }
label { flex: 1; min-width: 220px; display: flex; flex-direction: column; gap: 7px; }
input { min-width: 0; min-height: 42px; padding: 9px 11px; border: 1px solid var(--lz-border); border-radius: 8px; color: var(--lz-text-strong); background: #fff; }
form button { border-color: var(--lz-action-border); color: var(--lz-action-text); background: var(--lz-action-bg); border: 1px solid var(--lz-action-border); border-radius: var(--lz-action-radius); box-shadow: var(--lz-action-shadow); }
form button:hover { border-color: var(--lz-action-border-hover); color: var(--lz-action-text); background: var(--lz-action-bg); }
p, small { color: var(--lz-text-secondary); }
ul { list-style: none; padding: 0; }
li { display: flex; align-items: center; justify-content: space-between; gap: 16px; border-top: 1px solid var(--lz-border); padding: 15px 0; overflow-wrap: anywhere; }
small { display: block; font-size: 15px; }
:is(input, button):focus-visible { outline: 2px solid var(--lz-brand); outline-offset: 2px; }
.grant-panel.is-embedded { width: 100%; max-height: none; padding: 0; border: 0; border-radius: 0; box-shadow: none; }
.grant-panel.is-embedded h2 { font-size: 17px; margin: 20px 0 12px; }
</style>
