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
button,input{font:inherit;font-size:15px}button{border:1px solid #dce1ed;border-radius:8px;background:white;padding:8px 13px;cursor:pointer}.grant-backdrop{position:fixed;inset:0;background:#26344955;z-index:2100;display:grid;place-items:center}.grant-panel{width:min(620px,85vw);max-height:85vh;overflow:auto;padding:30px;background:white;border-radius:18px;color:#263449;font:15px/1.7 var(--lz-font-sans,sans-serif)}header{display:flex;align-items:center;justify-content:space-between;gap:20px}h2{font-size:23px}form{display:flex;align-items:end;gap:15px;margin:24px 0}label{flex:1;display:flex;flex-direction:column;gap:10px}input{border:1px solid #d7deeb;padding:10px;border-radius:8px;min-width:0}form button{background:#6551c7;color:white}p,small{color:#758195}ul{list-style:none;padding:0}li{display:flex;align-items:center;justify-content:space-between;gap:16px;border-top:1px solid #e5e8f0;padding:15px 0;overflow-wrap:anywhere}small{display:block;font-size:15px}:is(input,button):focus-visible{outline:3px solid #9385ed;outline-offset:3px}
</style>

<style scoped>
.grant-panel.is-embedded{width:100%;max-height:none;padding:0;border-radius:0}.grant-panel.is-embedded h2{font-size:20px;margin:12px 0}.grant-panel.is-embedded form{flex-wrap:wrap}.grant-panel.is-embedded label{min-width:220px}
</style>
