<template>
  <section class="course-calendar-page">
    <header class="product-bar">
      <button type="button" class="brand" @click="router.push({ name: 'teacher-course-library' })">
        <img src="/qizhi-favicon.svg" alt="" /><strong>启智</strong>
      </button>
      <nav aria-label="当前位置">
        <button type="button" @click="router.push({ name: 'teacher-course-library' })">课程工作台</button><ChevronRight :size="14" />
        <button type="button" @click="router.push({ name: 'teacher-course-overview', params: { courseId } })">{{ courseTitle }}</button><ChevronRight :size="14" />
        <strong>教学日历</strong>
      </nav>
      <div class="product-actions">
        <button type="button" @click="openTotalCalendar"><CalendarRange :size="16" />教学总日历</button>
        <button type="button" aria-label="刷新日历" @click="load"><RefreshCw :size="17" :class="{ spin: store.loading }" /></button>
      </div>
    </header>

    <div class="page-shell">
      <TeacherCourseSidebar :course-id="courseId" :title="courseTitle" :meta="courseMeta" active="calendar" />
      <main class="calendar-main">
        <div class="status-bar" role="status">
          <strong>{{ courseTitle }}</strong>
          <span>{{ editable?.academic_year || t('teacherCalendar.yearUnset', '未设学年') }}</span>
          <span>{{ editable?.term || t('teacherCalendar.termUnset', '未设学期') }}</span>
          <span>{{ t('teacherCalendar.sessions', '课次') }} {{ editable?.sessions.length || 0 }}</span>
          <span>{{ t('teacherCalendar.scheduled', '已排期') }} {{ scheduledCount }}</span>
          <span>{{ t('teacherCalendar.unscheduled', '未排期') }} {{ unscheduledCount }}</span>
          <span class="spacer"></span>
          <span v-if="dirty" class="dirty">未保存，不会同步总日历</span>
          <span v-else>{{ t('teacherCalendar.revision', '修订') }} {{ editable?.revision || 0 }}</span>
        </div>

        <section class="calendar-workspace">
          <header class="workspace-toolbar">
            <div class="segmented" role="tablist">
              <button type="button" data-testid="calendar-table-view" :class="{ active: view === 'table' }" @click="view = 'table'"><Table2 :size="15" />教学日历</button>
              <button type="button" data-testid="calendar-month-view" :class="{ active: view === 'month' }" @click="view = 'month'"><CalendarDays :size="15" />月历</button>
              <button type="button" data-testid="calendar-week-view" :class="{ active: view === 'week' }" @click="view = 'week'"><Columns3 :size="15" />周历</button>
            </div>
            <template v-if="editable">
              <label class="meta-field"><span>学年</span><input v-model="editable.academic_year" placeholder="2025-2026" @input="markDirty" /></label>
              <label class="meta-field"><span>学期</span><input v-model="editable.term" placeholder="春夏" @input="markDirty" /></label>
            </template>
            <span class="toolbar-spacer"></span>
            <input ref="csvInput" class="visually-hidden" type="file" accept=".csv,text/csv" @change="importCsv" />
            <el-dropdown v-if="editable" trigger="click" @command="handleTransferCommand">
              <button type="button" class="quiet-button transfer-button"><ArrowUpDown :size="15" />导入 / 导出<ChevronDown :size="13" /></button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="import"><Upload :size="14" />导入 CSV 交换表</el-dropdown-item>
                  <el-dropdown-item command="docx"><Download :size="14" />导出可编辑 DOCX</el-dropdown-item>
                  <el-dropdown-item command="pdf"><Download :size="14" />导出阅读 PDF</el-dropdown-item>
                  <el-dropdown-item command="xlsx"><Download :size="14" />导出 Excel</el-dropdown-item>
                  <el-dropdown-item command="csv"><Download :size="14" />导出 CSV</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <button v-if="editable && view === 'table'" type="button" class="quiet-button" data-testid="add-table-session" @click="addSession"><Plus :size="15" />新增课次</button>
            <button v-if="editable" type="button" class="quiet-button" :disabled="store.deriving" @click="deriveFromOutline"><Sparkles :size="15" />{{ store.deriving ? '正在识别大纲' : '从大纲生成课次' }}</button>
            <button v-if="editable" type="button" class="primary-button" data-testid="save-calendar" :disabled="!dirty || store.saving" @click="save"><Save :size="15" />{{ store.saving ? '保存中' : '保存并同步' }}</button>
          </header>

          <div v-if="store.conflictRevision !== null" class="issue-bar" role="alert">
            <TriangleAlert :size="16" /><strong>日历已在其他页面更新</strong><span>本地草稿仍保留。请复制必要内容后重新载入最新修订。</span><button type="button" @click="load">重新加载</button>
          </div>
          <div v-else-if="store.error" class="issue-bar" role="alert"><TriangleAlert :size="16" /><span>{{ store.error }}</span><button type="button" @click="load">重试</button></div>

          <div v-if="store.loading && !editable" class="loading-state"><LoaderCircle class="spin" :size="22" />正在读取教学日历</div>
          <div v-else-if="editable" class="calendar-board" :class="{ 'is-table': view === 'table' }">
            <aside class="session-rail" aria-label="课次目录">
              <header><div><strong>课次目录</strong><span>{{ editable.sessions.length }}</span></div><button type="button" data-testid="add-calendar-session" aria-label="新增课次" @click="addSession"><Plus :size="16" /></button></header>
              <div v-if="editable.sessions.length" class="session-list">
                <button v-for="item in indexedSessions" :key="item.key" type="button" :class="{ active: item.index === selectedIndex }" @click="selectSession(item.index)">
                  <span class="session-sequence">{{ String(item.session.sequence || item.index + 1).padStart(2, '0') }}</span>
                  <span class="session-copy"><strong>{{ item.session.content_summary || '未命名课次' }}</strong><small>{{ sessionMeta(item.session) }}</small></span>
                  <i :data-state="item.session.status"></i>
                </button>
              </div>
              <button v-else type="button" class="rail-empty" @click="deriveFromOutline"><Sparkles :size="18" /><strong>还没有课次</strong><span>从教学大纲生成，或手动新增。</span></button>
              <footer><span><i data-state="scheduled"></i>已排期 {{ scheduledCount }}</span><span><i data-state="unscheduled"></i>待排期 {{ unscheduledCount }}</span></footer>
            </aside>

            <section class="calendar-canvas">
              <template v-if="view === 'month'">
                <header class="month-heading">
                  <div><small>课程排期</small><strong>{{ monthLabel }}</strong></div>
                  <div><button type="button" aria-label="上个月" @click="moveMonth(-1)"><ChevronLeft :size="16" /></button><button type="button" @click="goToday">今天</button><button type="button" aria-label="下个月" @click="moveMonth(1)"><ChevronRight :size="16" /></button></div>
                </header>
                <div v-if="!editable.sessions.length" class="calendar-hint"><Sparkles :size="16" /><span>确认教学大纲后，可自动形成课次候选；候选不会覆盖人工排课。</span><button type="button" @click="deriveFromOutline">生成候选</button></div>
                <div class="month-scroll"><TeachingCalendarMonthGrid :month="monthCursor" :sessions="editable.sessions" @select="focusSession" @day="addSessionForDate" /></div>
              </template>

              <template v-else-if="view === 'week'">
                <header class="month-heading">
                  <div><small>本周排期</small><strong>{{ weekLabel }}</strong></div>
                  <div><button type="button" aria-label="上一周" @click="moveWeek(-1)"><ChevronLeft :size="16" /></button><button type="button" @click="goToday">今天</button><button type="button" aria-label="下一周" @click="moveWeek(1)"><ChevronRight :size="16" /></button></div>
                </header>
                <div class="course-week-grid">
                  <section v-for="day in weekDays" :key="day.date">
                    <header><strong>{{ day.label }}</strong><span>{{ day.date.slice(5) }}</span></header>
                    <button v-for="session in day.sessions" :key="session.session_id || `${day.date}-${session.sequence}`" type="button" :class="{ active: session === selectedSession }" @click="focusSession(session)">
                      <time>{{ session.start_time?.slice(0, 5) || '时间待定' }}</time>
                      <strong>第 {{ session.sequence }} 讲 · {{ session.content_summary }}</strong>
                      <small>{{ session.location || '地点待定' }}</small>
                    </button>
                    <button v-if="!day.sessions.length" type="button" class="add-day" @click="addSessionForDate(day.date)"><Plus :size="14" />安排课次</button>
                  </section>
                </div>
              </template>

              <div v-else class="table-wrap" :class="{ 'is-empty': !editable.sessions.length }">
                <table v-if="editable.sessions.length">
                  <thead><tr><th class="sequence">课次</th><th>日期</th><th>教学内容</th><th>教学要求（含作业）</th><th>上课地点</th><th>教师</th><th>类型</th><th>小组</th><th>学时</th><th class="actions">操作</th></tr></thead>
                  <tbody>
                    <tr v-for="(session, index) in editable.sessions" :key="session.session_id || index" data-testid="calendar-session-row" :class="{ highlighted: index === selectedIndex }" @click="selectSession(index)">
                      <td class="sequence"><strong>{{ index + 1 }}</strong><small v-if="session.source === 'outline'">大纲</small></td>
                      <td><input v-model="session.date" type="date" @input="schedule(session)" /><div class="time-row"><input v-model="session.start_time" type="text" inputmode="numeric" maxlength="5" placeholder="08:00" aria-label="开始时间" @input="schedule(session)" /><span>—</span><input v-model="session.end_time" type="text" inputmode="numeric" maxlength="5" placeholder="09:30" aria-label="结束时间" @input="schedule(session)" /></div></td>
                      <td><button type="button" class="cell-editor-trigger" @click.stop="openEditor(index)"><span>{{ session.content_summary || '待补充教学内容' }}</span><PencilLine :size="13" /></button></td>
                      <td><button type="button" class="cell-editor-trigger" @click.stop="openEditor(index)"><span>{{ session.requirements || '待补充教学要求' }}</span><PencilLine :size="13" /></button></td>
                      <td><input v-model="session.location" @input="markDirty" /></td><td><input v-model="session.teacher_name" @input="markDirty" /></td>
                      <td><select v-model="session.teaching_type" @change="markDirty"><option>理论课</option><option>讨论课</option><option>实践课</option><option>实验课</option><option>答疑</option></select></td>
                      <td><input v-model="session.group_code" @input="markDirty" /></td><td><input v-model.number="session.credit_hours" type="number" min="0" step="0.5" @input="markDirty" /></td>
                      <td class="actions"><button type="button" data-testid="delete-calendar-session" aria-label="删除课次" @click.stop="removeSession(index)"><Trash2 :size="15" /></button></td>
                    </tr>
                  </tbody>
                </table>
                <section v-else class="empty-action" aria-label="空教学日历">
                  <Sparkles :size="22" />
                  <strong>先建立这门课的课次</strong>
                  <span>已有教学大纲时可直接生成；也可以先手动新增，再逐讲补充。</span>
                  <div>
                    <button type="button" class="quiet-button" @click="deriveFromOutline"><Sparkles :size="15" />从大纲生成</button>
                    <button type="button" class="primary-button" @click="addSession"><Plus :size="15" />手动新增课次</button>
                  </div>
                </section>
              </div>
            </section>

            <aside v-if="view !== 'table'" class="session-inspector" aria-label="当前课次编辑">
              <template v-if="selectedSession">
                <header><div><small>当前课次</small><strong>第 {{ selectedSession.sequence }} 讲</strong></div><span :data-state="selectedSession.status">{{ selectedSession.status === 'scheduled' ? '已排期' : '待排期' }}</span></header>
                <div class="inspector-form">
                  <label class="wide"><span>教学内容</span><textarea v-model="selectedSession.content_summary" rows="3" @input="markDirty"></textarea></label>
                  <label><span>日期</span><input v-model="selectedSession.date" type="date" @input="schedule(selectedSession)" /></label>
                  <div class="field-pair"><label><span>开始</span><input v-model="selectedSession.start_time" type="text" inputmode="numeric" maxlength="5" placeholder="08:00" @input="schedule(selectedSession)" /></label><label><span>结束</span><input v-model="selectedSession.end_time" type="text" inputmode="numeric" maxlength="5" placeholder="09:30" @input="schedule(selectedSession)" /></label></div>
                  <div class="field-pair"><label><span>地点</span><input v-model="selectedSession.location" @input="markDirty" /></label><label><span>教师</span><input v-model="selectedSession.teacher_name" @input="markDirty" /></label></div>
                  <div class="field-pair"><label><span>教学类型</span><select v-model="selectedSession.teaching_type" @change="markDirty"><option>理论课</option><option>讨论课</option><option>实践课</option><option>实验课</option><option>答疑</option></select></label><label><span>学时</span><input v-model.number="selectedSession.credit_hours" type="number" min="0" step="0.5" @input="markDirty" /></label></div>
                  <label class="wide"><span>教学要求与作业</span><textarea v-model="selectedSession.requirements" rows="4" @input="markDirty"></textarea></label>
                  <label class="wide"><span>小组 / 备注</span><input v-model="selectedSession.group_code" placeholder="例如 A 组" @input="markDirty" /></label>
                </div>
                <footer><span>{{ selectedSession.source === 'outline' ? '来源：教学大纲' : selectedSession.source === 'import' ? '来源：CSV 交换表' : '来源：手动创建' }}</span><button type="button" class="danger-button" @click="removeSession(selectedIndex!)"><Trash2 :size="14" />删除</button></footer>
              </template>
              <button v-else type="button" class="inspector-empty" @click="addSession"><CalendarDays :size="24" /><strong>选择一个课次</strong><span>在月历或左侧目录中选择后，可在这里完成排课。</span><em><Plus :size="14" />新增课次</em></button>
            </aside>
          </div>

          <el-drawer v-model="editorOpen" title="编辑课次详情" size="min(420px, 92vw)" append-to-body>
            <div v-if="selectedSession" class="drawer-session-editor">
              <div class="drawer-session-meta"><strong>第 {{ selectedSession.sequence }} 讲</strong><span :data-state="selectedSession.status">{{ selectedSession.status === 'scheduled' ? '已排期' : '待排期' }}</span></div>
              <label><span>教学内容</span><textarea v-model="selectedSession.content_summary" rows="6" @input="markDirty"></textarea></label>
              <label><span>教学要求（含作业）</span><textarea v-model="selectedSession.requirements" rows="7" @input="markDirty"></textarea></label>
              <label><span>备注</span><textarea v-model="selectedSession.notes" rows="4" @input="markDirty"></textarea></label>
              <p>日期、时间、地点、教师等短字段继续在横向表格内修改。</p>
            </div>
          </el-drawer>

          <el-dialog v-model="deriveDialogOpen" title="大纲课次候选" width="min(720px, 92vw)" append-to-body>
            <template v-if="deriveProposal">
              <div class="derive-summary">
                <strong>本次不会直接改动日历</strong>
                <span>新增 {{ deriveProposal.diff.add_count }} · 更新 {{ deriveProposal.diff.update_count }} · 保持 {{ deriveProposal.diff.keep_count }} · 待处理 {{ deriveProposal.diff.stale_count }}</span>
              </div>
              <div class="derive-list">
                <label v-for="(item, index) in deriveProposal.diff.items" :key="`${item.session_id || item.lesson_unit_id}-${index}`" :data-kind="item.kind">
                  <input v-if="item.kind === 'add' || item.kind === 'update'" v-model="selectedDiffIndexes" type="checkbox" :value="index" />
                  <span v-else class="derive-marker"></span>
                  <span><strong>{{ item.kind === 'add' ? '新增' : item.kind === 'update' ? '更新' : item.kind === 'stale' ? '待处理' : '保持' }} · {{ item.title }}</strong><small>{{ item.reason }}</small></span>
                </label>
              </div>
            </template>
            <template #footer><button type="button" class="quiet-button" @click="deriveDialogOpen = false">取消</button><button type="button" class="primary-button" @click="applyDeriveProposal">采用所选候选</button></template>
          </el-dialog>
        </section>
      </main>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowUpDown, CalendarDays, CalendarRange, ChevronDown, ChevronLeft, ChevronRight, Columns3, Download, LoaderCircle, PencilLine, Plus, RefreshCw, Save, Sparkles, Table2, Trash2, TriangleAlert, Upload } from 'lucide-vue-next'
import TeacherCourseSidebar from '../components/TeacherCourseSidebar.vue'
import TeachingCalendarMonthGrid from '../components/TeachingCalendarMonthGrid.vue'
import { t } from '../shared/i18n'
import { useTeacherCourseRuntime } from '../features/teacher-course/useTeacherCourseRuntime'
import { useTeachingCalendarStore, type ClassSession, type OutlineCalendarCandidate, type TeachingCalendar } from '../stores/teachingCalendar'
import { sessionImportKey, teachingCalendarFromCsv } from '../utils/teaching-calendar-csv'
import http, { getTeacherIdentity } from '../utils/http'

const route = useRoute()
const router = useRouter()
const { course: courseStore } = useTeacherCourseRuntime()
const store = useTeachingCalendarStore()
const editable = ref<TeachingCalendar | null>(null)
const csvInput = ref<HTMLInputElement | null>(null)
const dirty = ref(false)
const view = ref<'table' | 'month' | 'week'>('table')
const monthCursor = ref(`${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-01`)
const weekCursor = ref(`${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}`)
const selectedIndex = ref<number | null>(null)
const editorOpen = ref(false)
const deriveDialogOpen = ref(false)
const deriveProposal = ref<OutlineCalendarCandidate | null>(null)
const selectedDiffIndexes = ref<number[]>([])
const courseId = computed(() => String(route.params.courseId || ''))
const courseSummary = computed(() => courseStore.courseList.find(item => item.course_id === courseId.value))
const courseTitle = computed(() => editable.value?.course_title || courseSummary.value?.course_name || '未命名课程')
const courseMeta = computed(() => [editable.value?.academic_year, editable.value?.term].filter(Boolean).join(' ') || '教学日历')
const scheduledCount = computed(() => editable.value?.sessions.filter(isCompleteSession).length || 0)
const unscheduledCount = computed(() => (editable.value?.sessions.length || 0) - scheduledCount.value)
const monthLabel = computed(() => { const value = new Date(`${monthCursor.value.slice(0, 7)}-01T12:00:00`); return `${value.getFullYear()}年${value.getMonth() + 1}月` })
const indexedSessions = computed(() => (editable.value?.sessions || []).map((session, index) => ({ session, index, key: session.session_id || `session-${index}` })))
const selectedSession = computed(() => selectedIndex.value === null ? null : editable.value?.sessions[selectedIndex.value] || null)
const weekStart = computed(() => {
  const value = new Date(`${weekCursor.value}T12:00:00`)
  value.setDate(value.getDate() - ((value.getDay() + 6) % 7))
  return value
})
const pad = (value: number) => String(value).padStart(2, '0')
const iso = (value: Date) => `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
const weekLabel = computed(() => { const end = new Date(weekStart.value); end.setDate(end.getDate() + 6); return `${iso(weekStart.value)} — ${iso(end)}` })
const weekDays = computed(() => ['周一', '周二', '周三', '周四', '周五', '周六', '周日'].map((label, index) => {
  const value = new Date(weekStart.value); value.setDate(value.getDate() + index); const date = iso(value)
  return { label, date, sessions: editable.value?.sessions.filter(item => item.date === date && item.status !== 'cancelled') || [] }
}))

function normalizeClock(value?: string | null) {
  const normalized = String(value || '').trim()
  return /^([01]\d|2[0-3]):[0-5]\d/.test(normalized) ? normalized.slice(0, 5) : null
}
function cloneCalendar(calendar: TeachingCalendar): TeachingCalendar {
  const cloned = JSON.parse(JSON.stringify(calendar)) as TeachingCalendar
  cloned.sessions = cloned.sessions.map(session => {
    const startTime = normalizeClock(session.start_time)
    const endTime = normalizeClock(session.end_time)
    const complete = Boolean(session.date && startTime && endTime && endTime > startTime && session.status !== 'cancelled')
    return {
      ...session,
      start_time: startTime,
      end_time: endTime,
      status: session.status === 'cancelled' ? 'cancelled' : complete ? 'scheduled' : 'unscheduled',
    }
  })
  return cloned
}
function markDirty() { dirty.value = true }
function validTime(value?: string | null) { return /^([01]\d|2[0-3]):[0-5]\d$/.test(String(value || '')) }
function isCompleteSession(session: ClassSession) { return Boolean(session.date && validTime(session.start_time) && validTime(session.end_time) && String(session.end_time) > String(session.start_time) && session.status !== 'cancelled') }
function schedule(session: ClassSession) { session.status = isCompleteSession(session) ? 'scheduled' : 'unscheduled'; markDirty() }
function blankSession(date = ''): ClassSession { return { sequence: (editable.value?.sessions.length || 0) + 1, date: date || null, start_time: null, end_time: null, content_summary: '新增课次', requirements: '', location: '', teacher_name: '', teaching_type: '理论课', group_code: '', credit_hours: 2, notes: '', status: 'unscheduled', source: 'manual' } }
function selectSession(index: number) { selectedIndex.value = index; const date = editable.value?.sessions[index]?.date; if (date) { monthCursor.value = `${date.slice(0, 7)}-01`; weekCursor.value = date } }
function addSession() { if (!editable.value) return; editable.value.sessions.push(blankSession()); selectSession(editable.value.sessions.length - 1); markDirty() }
function addSessionForDate(date: string) { if (!editable.value) return; editable.value.sessions.push(blankSession(date)); selectSession(editable.value.sessions.length - 1); markDirty() }
function openEditor(index: number) { selectSession(index); editorOpen.value = true }
function sessionMeta(session: ClassSession) { return session.date ? `${session.date.slice(5)} · ${session.start_time?.slice(0, 5) || '时间待定'}` : '日期待安排' }
function handleTransferCommand(command: 'import' | 'docx' | 'pdf' | 'xlsx' | 'csv') {
  if (command === 'import') csvInput.value?.click()
  else void downloadExport(command)
}
async function downloadExport(format: 'docx' | 'pdf' | 'xlsx' | 'csv') {
  if (!editable.value) return
  if (dirty.value) {
    try {
      await ElMessageBox.confirm('正式导出只读取已保存修订。是否先保存当前修改？', '保存后导出', { type: 'info', confirmButtonText: '保存并导出', cancelButtonText: '取消' })
      if (!await save()) return
    } catch { return }
  }
  try {
    const response = await http.get(`/api/courses/${courseId.value}/teaching-calendar/export`, {
      params: { format, revision: editable.value.revision },
      responseType: 'blob',
      headers: { 'X-User-Id': getTeacherIdentity() },
    })
    const url = URL.createObjectURL(response.data)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${courseTitle.value.replace(/[\\/:*?"<>|]/g, '_') || '教学日历'}_教学日历_r${editable.value.revision}.${format}`
    anchor.click()
    URL.revokeObjectURL(url)
    ElMessage.success(`${format.toUpperCase()} 已按修订 ${editable.value.revision} 导出`)
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    ElMessage.error(detail?.message || `${format.toUpperCase()} 导出失败，请确认日历已保存且包含课次`)
  }
}
async function importCsv(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !editable.value) return
  try {
    const imported = teachingCalendarFromCsv(await file.text())
    const existingKeys = new Set(editable.value.sessions.map(sessionImportKey))
    const additions = imported.filter(session => !existingKeys.has(sessionImportKey(session)))
    const duplicateCount = imported.length - additions.length
    await ElMessageBox.confirm(
      `识别到 ${imported.length} 条课次，可新增 ${additions.length} 条${duplicateCount ? `，跳过重复 ${duplicateCount} 条` : ''}。导入只合并到本地草稿，点击“保存日历”后才会生效。`,
      '合并 CSV 课次候选',
      { type: 'info', confirmButtonText: '合并到草稿', cancelButtonText: '取消' },
    )
    additions.forEach(session => editable.value?.sessions.push(session))
    editable.value.sessions.forEach((session, index) => { session.sequence = index + 1 })
    if (additions.length) { selectSession(editable.value.sessions.length - additions.length); markDirty() }
    ElMessage.success(additions.length ? `已合并 ${additions.length} 条课次候选` : '没有发现新的课次')
  } catch (error: any) {
    if (error !== 'cancel') ElMessage.error(error?.message || 'CSV 识别失败')
  }
}
async function removeSession(index: number) {
  if (!editable.value) return
  try {
    await ElMessageBox.confirm('删除后将在下次保存时生效，是否继续？', '删除课次', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    editable.value.sessions.splice(index, 1); editable.value.sessions.forEach((item, order) => { item.sequence = order + 1 }); selectedIndex.value = editable.value.sessions.length ? Math.min(index, editable.value.sessions.length - 1) : null; markDirty()
  } catch { /* cancelled */ }
}
async function deriveFromOutline() {
  if (!editable.value) return
  try {
    const result = await store.deriveFromOutline(courseId.value)
    if (!result.diff.add_count && !result.diff.update_count && !result.diff.stale_count) {
      ElMessage.info(`当前 ${result.retained_count} 条课次已与教学大纲一致`)
      return
    }
    deriveProposal.value = result
    selectedDiffIndexes.value = result.diff.items.map((item, index) => item.kind === 'add' || item.kind === 'update' ? index : -1).filter(index => index >= 0)
    deriveDialogOpen.value = true
  } catch { ElMessage.error(store.error || '从大纲生成失败') }
}
function applyDeriveProposal() {
  if (!editable.value || !deriveProposal.value) return
  const currentById = new Map(editable.value.sessions.map(session => [session.session_id, session]))
  const selected = new Set(selectedDiffIndexes.value)
  const next = deriveProposal.value.candidate.sessions.flatMap((candidate, index) => {
    const diff = deriveProposal.value?.diff.items[index]
    if (!diff) return [candidate]
    if (diff.kind === 'add') return selected.has(index) ? [candidate] : []
    if (diff.kind === 'update' && !selected.has(index)) return [currentById.get(candidate.session_id) || candidate]
    return [candidate]
  })
  editable.value.sessions = next.map((session, index) => ({ ...session, sequence: index + 1 }))
  editable.value.source_outline_revision = deriveProposal.value.candidate.source_outline_revision
  selectedIndex.value = editable.value.sessions.length ? 0 : null
  dirty.value = true
  deriveDialogOpen.value = false
  ElMessage.success('所选候选已进入本地草稿；保存后才会同步总日历')
}
async function save(): Promise<boolean> {
  if (!editable.value) return false
  try {
    editable.value = cloneCalendar(await store.saveCourse(courseId.value, editable.value))
    dirty.value = false
    ElMessage.success('教学日历已保存，教学总日历已同步')
    return true
  } catch {
    ElMessage.error(store.error || '教学日历保存失败')
    return false
  }
}
async function openTotalCalendar() {
  if (dirty.value) {
    if (!await save()) return
  }
  await router.push({ name: 'teacher-teaching-calendar' })
}
async function load() {
  try {
    await courseStore.fetchCourseList(); editable.value = cloneCalendar(await store.loadCourse(courseId.value)); dirty.value = false
    const routeSession = String(route.query.session || '')
    const routeIndex = editable.value.sessions.findIndex(item => item.session_id === routeSession)
    selectedIndex.value = routeIndex >= 0 ? routeIndex : editable.value.sessions.length ? 0 : null
    const firstDate = selectedSession.value?.date || editable.value.sessions.find(item => item.date)?.date
    if (firstDate) { monthCursor.value = `${firstDate.slice(0, 7)}-01`; weekCursor.value = firstDate }
  } catch { /* store exposes exact reason */ }
}
function moveMonth(delta: number) { const value = new Date(`${monthCursor.value.slice(0, 7)}-01T12:00:00`); value.setMonth(value.getMonth() + delta); monthCursor.value = `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-01` }
function moveWeek(delta: number) { const value = new Date(weekStart.value); value.setDate(value.getDate() + delta * 7); weekCursor.value = iso(value) }
function goToday() { const value = new Date(); monthCursor.value = `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-01`; weekCursor.value = iso(value) }
function focusSession(session: ClassSession) { const index = editable.value?.sessions.findIndex(item => item === session || (session.session_id && item.session_id === session.session_id)) ?? -1; if (index >= 0) selectSession(index) }

watch(courseId, () => { store.resetCourse(); editable.value = null; void load() }, { immediate: true })
function beforeUnload(event: BeforeUnloadEvent) { if (!dirty.value) return; event.preventDefault(); event.returnValue = '' }
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
onBeforeRouteLeave(async () => {
  if (!dirty.value) return true
  try {
    await ElMessageBox.confirm('当前日历还有未保存修改。离开前是否保存并同步？', '保存教学日历', { type: 'warning', confirmButtonText: '保存并离开', cancelButtonText: '留在当前页' })
    return await save()
  } catch { return false }
})
</script>

<style scoped>
.course-calendar-page{height:100vh;min-height:100vh;overflow:hidden;color:var(--lz-text-primary);background:var(--lz-canvas)}button,input,textarea,select{font:inherit}.product-bar{height:52px;display:grid;grid-template-columns:188px minmax(0,1fr) auto;align-items:center;border-bottom:1px solid var(--lz-border);background:var(--lz-surface)}.brand{height:100%;display:flex;align-items:center;gap:10px;padding:0 20px;border:0;border-right:1px solid var(--lz-border);color:var(--lz-text-primary);background:transparent;cursor:pointer}.brand img{width:25px;height:25px}.brand strong{font-size:17px}.product-bar nav{min-width:0;display:flex;align-items:center;gap:8px;padding:0 24px;color:var(--lz-text-muted);font-size:12px}.product-bar nav button{max-width:220px;overflow:hidden;padding:0;border:0;color:inherit;background:transparent;text-overflow:ellipsis;white-space:nowrap;cursor:pointer}.product-bar nav strong{color:var(--lz-text-primary)}.product-actions{display:flex;align-items:center;gap:6px;padding-right:14px}.product-actions button{height:34px;display:inline-flex;align-items:center;gap:6px;padding:0 11px;border:1px solid var(--lz-border);border-radius:9px;color:var(--lz-text-secondary);background:var(--lz-surface);cursor:pointer}
.page-shell{height:calc(100vh - 52px);display:grid;grid-template-columns:188px minmax(0,1fr)}.calendar-main{min-width:0;min-height:0;display:grid;grid-template-rows:42px minmax(0,1fr)}.status-bar{min-width:0;display:flex;align-items:center;padding:0 14px;border-bottom:1px solid var(--lz-border);background:var(--lz-surface);font-size:11px;white-space:nowrap}.status-bar>strong,.status-bar>span{padding:0 11px;border-right:1px solid var(--lz-border)}.status-bar>strong{padding-left:0}.status-bar .spacer{flex:1;border:0}.status-bar .dirty{border:0;color:var(--lz-warning);font-weight:700}
.calendar-workspace{min-width:0;min-height:0;display:grid;grid-template-rows:50px auto minmax(0,1fr);background:var(--lz-surface)}.workspace-toolbar{display:flex;align-items:center;gap:8px;padding:7px 12px;border-bottom:1px solid var(--lz-border)}.segmented{display:flex;padding:2px;border:1px solid var(--lz-border);border-radius:8px;background:var(--lz-fill)}.segmented button,.quiet-button,.primary-button{height:30px;display:inline-flex;align-items:center;gap:5px;padding:0 10px;border:0;border-radius:6px;color:var(--lz-text-secondary);background:transparent;cursor:pointer}.segmented button.active{color:var(--lz-brand-strong);background:var(--lz-surface);box-shadow:0 1px 2px rgb(0 0 0/.06);font-weight:700}.meta-field{display:flex;align-items:center;gap:5px;color:var(--lz-text-muted);font-size:10px}.meta-field input{width:96px;height:30px;padding:0 8px;border:1px solid var(--lz-border);border-radius:7px;background:var(--lz-surface)}.toolbar-spacer{flex:1}.quiet-button{border:1px solid var(--lz-border);background:var(--lz-surface)}.transfer-button{white-space:nowrap}.primary-button{color:#fff;background:var(--lz-brand)}.primary-button:disabled,.quiet-button:disabled{opacity:.45;cursor:not-allowed}.visually-hidden{display:none!important}.issue-bar{min-height:38px;display:flex;align-items:center;gap:8px;padding:7px 12px;border-bottom:1px solid var(--lz-warning-border);color:var(--lz-text-secondary);background:var(--lz-warning-soft);font-size:10px}.issue-bar span{flex:1}.issue-bar button{height:26px;padding:0 9px;border:1px solid var(--lz-warning-border);border-radius:6px;background:var(--lz-surface);cursor:pointer}.loading-state{height:100%;display:flex;align-items:center;justify-content:center;gap:8px;color:var(--lz-text-muted);font-size:11px}
.calendar-board{min-width:0;min-height:0;display:grid;grid-template-columns:218px minmax(0,1fr) 306px}.calendar-board.is-table{grid-template-columns:190px minmax(0,1fr)}.calendar-board.is-table .session-inspector{display:none}.session-rail,.session-inspector{min-width:0;min-height:0;background:var(--lz-surface)}.session-rail{display:grid;grid-template-rows:46px minmax(0,1fr) 38px;border-right:1px solid var(--lz-border)}.session-rail>header{display:flex;align-items:center;justify-content:space-between;padding:0 12px;border-bottom:1px solid var(--lz-border)}.session-rail>header div{display:flex;align-items:center;gap:7px}.session-rail>header strong{font-size:11px}.session-rail>header span{padding:2px 6px;border-radius:8px;color:var(--lz-brand-strong);background:var(--lz-brand-soft);font-size:9px}.session-rail>header button{width:28px;height:28px;display:grid;place-items:center;border:1px solid var(--lz-border);border-radius:7px;color:var(--lz-brand-strong);background:var(--lz-surface);cursor:pointer}.session-list{min-height:0;overflow:auto;padding:5px}.session-list button{width:100%;min-height:52px;display:grid;grid-template-columns:28px minmax(0,1fr) 8px;align-items:center;gap:7px;padding:7px 8px;border:1px solid transparent;border-radius:8px;color:var(--lz-text-secondary);background:transparent;text-align:left;cursor:pointer}.session-list button:hover{background:var(--lz-fill)}.session-list button.active{border-color:var(--lz-brand-border);background:var(--lz-brand-soft)}.session-sequence{color:var(--lz-brand);font-size:9px;font-weight:800}.session-copy{min-width:0;display:grid;gap:4px}.session-copy strong,.session-copy small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.session-copy strong{color:var(--lz-text-primary);font-size:10px}.session-copy small{color:var(--lz-text-muted);font-size:9px}.session-list i,.session-rail footer i{width:7px;height:7px;border-radius:50%;background:var(--lz-warning)}.session-list i[data-state="scheduled"],.session-rail footer i[data-state="scheduled"]{background:var(--lz-success)}.session-rail footer{display:flex;align-items:center;gap:12px;padding:0 11px;border-top:1px solid var(--lz-border);color:var(--lz-text-muted);font-size:9px}.session-rail footer span{display:flex;align-items:center;gap:5px}.rail-empty,.inspector-empty{border:0;color:var(--lz-text-muted);background:transparent;cursor:pointer}.rail-empty{display:grid;place-content:center;justify-items:center;gap:6px;padding:18px}.rail-empty strong{color:var(--lz-text-primary);font-size:11px}.rail-empty span{font-size:9px;text-align:center}
.calendar-canvas{min-width:0;min-height:0;display:grid;grid-template-rows:auto auto minmax(0,1fr);overflow:hidden;background:var(--lz-surface)}.month-heading{height:46px;display:flex;align-items:center;justify-content:space-between;padding:0 12px;border-bottom:1px solid var(--lz-border)}.month-heading>div:first-child{display:flex;align-items:baseline;gap:8px}.month-heading small{color:var(--lz-text-muted);font-size:9px}.month-heading strong{font-size:12px}.month-heading>div:last-child{display:flex;gap:5px}.month-heading button{height:28px;min-width:28px;padding:0 8px;border:1px solid var(--lz-border);border-radius:7px;color:var(--lz-text-secondary);background:var(--lz-surface);cursor:pointer}.calendar-hint{min-height:34px;display:flex;align-items:center;gap:7px;padding:5px 10px;border-bottom:1px solid var(--lz-brand-border);color:var(--lz-text-secondary);background:var(--lz-brand-soft);font-size:9px}.calendar-hint span{flex:1}.calendar-hint button{height:24px;padding:0 8px;border:1px solid var(--lz-brand-border);border-radius:6px;color:var(--lz-brand-strong);background:var(--lz-surface);cursor:pointer}.month-scroll{min-width:0;min-height:0;overflow:auto;padding:8px}.table-wrap{min-width:0;min-height:0;overflow:auto;grid-row:1/-1}.table-wrap.is-empty{display:grid;place-items:center;overflow:hidden}.table-wrap table{width:100%;min-width:1180px;border-collapse:collapse;table-layout:fixed}.table-wrap th{position:sticky;top:0;z-index:2;height:35px;padding:0 7px;border-right:1px solid var(--lz-border);border-bottom:1px solid var(--lz-border);color:var(--lz-text-muted);background:var(--lz-fill);font-size:9px;text-align:left}.table-wrap th:nth-child(1){width:58px}.table-wrap th:nth-child(2){width:172px}.table-wrap th:nth-child(3){width:210px}.table-wrap th:nth-child(4){width:240px}.table-wrap th:nth-child(5){width:120px}.table-wrap th:nth-child(6){width:95px}.table-wrap th:nth-child(7){width:95px}.table-wrap th:nth-child(8){width:82px}.table-wrap th:nth-child(9){width:64px}.table-wrap th:nth-child(10){width:50px}.table-wrap td{height:74px;padding:6px;border-right:1px solid var(--lz-border);border-bottom:1px solid var(--lz-border);vertical-align:top}.table-wrap tr.highlighted td{background:var(--lz-brand-soft)}.table-wrap input,.table-wrap textarea,.table-wrap select{width:100%;box-sizing:border-box;border:1px solid transparent;border-radius:5px;color:var(--lz-text-primary);background:transparent;font-size:10px}.table-wrap input,.table-wrap select{height:28px;padding:0 5px}.table-wrap textarea{padding:5px;resize:vertical;line-height:1.45}.table-wrap input:hover,.table-wrap input:focus,.table-wrap textarea:hover,.table-wrap textarea:focus,.table-wrap select:hover,.table-wrap select:focus{outline:0;border-color:var(--lz-brand-border);background:var(--lz-surface)}.sequence{text-align:center!important}.sequence strong{display:block;font-size:11px}.sequence small{display:block;margin-top:6px;color:var(--lz-brand);font-size:8px}.time-row{display:flex;align-items:center;gap:3px;margin-top:3px}.time-row input{min-width:0}.actions{text-align:center!important}.actions button{width:28px;height:28px;display:grid;place-items:center;margin:auto;border:0;border-radius:6px;color:var(--lz-danger);background:transparent;cursor:pointer}.actions button:hover{background:var(--lz-danger-soft)}.empty-action{width:min(520px,calc(100% - 48px));display:grid;place-content:center;justify-items:center;gap:8px;color:var(--lz-text-muted);text-align:center}.empty-action strong{color:var(--lz-text-primary);font-size:14px}.empty-action span{max-width:420px;font-size:10px;line-height:1.65}.empty-action>div{display:flex;gap:8px;margin-top:7px}.empty-action .quiet-button,.empty-action .primary-button{min-width:122px;justify-content:center}
.session-inspector{display:grid;grid-template-rows:54px minmax(0,1fr) 44px;border-left:1px solid var(--lz-border)}.session-inspector>header{display:flex;align-items:center;justify-content:space-between;padding:0 14px;border-bottom:1px solid var(--lz-border)}.session-inspector>header div{display:grid;gap:3px}.session-inspector>header small{color:var(--lz-text-muted);font-size:9px}.session-inspector>header strong{font-size:12px}.session-inspector>header>span{padding:3px 7px;border-radius:7px;color:var(--lz-warning);background:var(--lz-warning-soft);font-size:9px}.session-inspector>header>span[data-state="scheduled"]{color:var(--lz-success);background:var(--lz-success-soft)}.inspector-form{min-height:0;overflow:auto;display:grid;align-content:start;gap:12px;padding:14px}.inspector-form label{min-width:0;display:grid;gap:5px}.inspector-form label>span{color:var(--lz-text-muted);font-size:9px;font-weight:700}.inspector-form input,.inspector-form textarea,.inspector-form select{box-sizing:border-box;width:100%;border:1px solid var(--lz-border);border-radius:7px;color:var(--lz-text-primary);background:var(--lz-surface);font-size:10px;outline:0}.inspector-form input,.inspector-form select{height:31px;padding:0 8px}.inspector-form textarea{padding:7px 8px;line-height:1.55;resize:vertical}.inspector-form input:focus,.inspector-form textarea:focus,.inspector-form select:focus{border-color:var(--lz-brand-border);box-shadow:0 0 0 3px var(--lz-brand-soft)}.field-pair{display:grid;grid-template-columns:1fr 1fr;gap:8px}.session-inspector>footer{display:flex;align-items:center;justify-content:space-between;padding:0 12px;border-top:1px solid var(--lz-border);color:var(--lz-text-muted);font-size:9px}.danger-button{height:28px;display:flex;align-items:center;gap:5px;padding:0 8px;border:0;border-radius:6px;color:var(--lz-danger);background:transparent;cursor:pointer}.danger-button:hover{background:var(--lz-danger-soft)}.inspector-empty{height:100%;display:grid;place-content:center;justify-items:center;gap:7px;padding:24px;text-align:center}.inspector-empty strong{color:var(--lz-text-primary);font-size:12px}.inspector-empty span{font-size:10px;line-height:1.6}.inspector-empty em{display:flex;align-items:center;gap:5px;margin-top:4px;color:var(--lz-brand-strong);font-style:normal;font-size:10px}.spin{animation:spin .9s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
.calendar-board{grid-row:3}
.calendar-board.is-table{grid-template-rows:minmax(0,1fr)}
.cell-editor-trigger{width:100%;min-height:60px;display:grid;grid-template-columns:minmax(0,1fr) 16px;align-items:start;gap:5px;padding:5px;border:1px solid transparent;border-radius:6px;color:var(--lz-text-secondary);background:transparent;text-align:left;cursor:pointer}.cell-editor-trigger span{display:-webkit-box;overflow:hidden;line-height:1.5;-webkit-box-orient:vertical;-webkit-line-clamp:3}.cell-editor-trigger svg{margin-top:2px;color:var(--lz-text-muted)}.cell-editor-trigger:hover,.cell-editor-trigger:focus-visible{border-color:var(--lz-brand-border);background:var(--lz-surface);outline:none}
.course-week-grid{min-width:760px;min-height:0;display:grid;grid-template-columns:repeat(7,minmax(105px,1fr));overflow:auto;padding:10px}.course-week-grid>section{min-width:0;border:1px solid var(--lz-border);border-right:0}.course-week-grid>section:last-child{border-right:1px solid var(--lz-border)}.course-week-grid>section>header{height:38px;display:flex;align-items:center;justify-content:space-between;padding:0 8px;border-bottom:1px solid var(--lz-border);font-size:10px}.course-week-grid>section>header span{color:var(--lz-text-muted)}.course-week-grid>section>button{width:calc(100% - 10px);display:grid;gap:4px;margin:5px;padding:8px;border:1px solid var(--lz-border);border-radius:7px;color:var(--lz-text-secondary);background:var(--lz-surface);text-align:left;cursor:pointer}.course-week-grid>section>button.active{border-color:var(--lz-brand-border);background:var(--lz-brand-soft)}.course-week-grid time{color:var(--lz-brand-strong);font-size:9px;font-weight:700}.course-week-grid strong,.course-week-grid small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.course-week-grid strong{font-size:10px}.course-week-grid small{color:var(--lz-text-muted);font-size:9px}.course-week-grid .add-day{display:flex;align-items:center;justify-content:center;color:var(--lz-text-muted);border-style:dashed;background:transparent}
.drawer-session-editor{display:grid;gap:16px}.drawer-session-meta{display:flex;align-items:center;justify-content:space-between;padding-bottom:12px;border-bottom:1px solid var(--lz-border)}.drawer-session-meta>span{padding:3px 7px;border-radius:7px;color:var(--lz-warning);background:var(--lz-warning-soft);font-size:10px}.drawer-session-meta>span[data-state="scheduled"]{color:var(--lz-success);background:var(--lz-success-soft)}.drawer-session-editor label{display:grid;gap:6px}.drawer-session-editor label>span{color:var(--lz-text-muted);font-size:10px;font-weight:700}.drawer-session-editor textarea{width:100%;box-sizing:border-box;padding:9px 10px;border:1px solid var(--lz-border);border-radius:8px;color:var(--lz-text-primary);background:var(--lz-surface);line-height:1.65;resize:vertical;outline:0}.drawer-session-editor textarea:focus{border-color:var(--lz-brand-border);box-shadow:0 0 0 3px var(--lz-brand-soft)}.drawer-session-editor p{margin:0;color:var(--lz-text-muted);font-size:10px;line-height:1.6}
.derive-summary{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:10px 12px;border-bottom:1px solid var(--lz-border);background:var(--lz-fill)}.derive-summary strong{font-size:11px}.derive-summary span{color:var(--lz-text-muted);font-size:10px}.derive-list{max-height:52vh;overflow:auto;border-bottom:1px solid var(--lz-border)}.derive-list label{min-height:54px;display:grid;grid-template-columns:24px minmax(0,1fr);align-items:center;gap:8px;padding:7px 10px;border-bottom:1px solid var(--lz-border);cursor:pointer}.derive-list label:last-child{border-bottom:0}.derive-list label[data-kind="stale"]{background:var(--lz-warning-soft)}.derive-list input{width:16px;height:16px}.derive-marker{width:8px;height:8px;justify-self:center;border-radius:50%;background:var(--lz-text-muted)}.derive-list label[data-kind="stale"] .derive-marker{background:var(--lz-warning)}.derive-list label>span:last-child{min-width:0;display:grid;gap:4px}.derive-list strong{overflow:hidden;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.derive-list small{color:var(--lz-text-muted);font-size:9px;line-height:1.5}
@media(max-width:1100px){.calendar-board{grid-template-columns:170px minmax(0,1fr) 286px}.calendar-board.is-table{grid-template-columns:170px minmax(0,1fr)}.meta-field{display:none}}
@media(max-width:900px){.product-bar{grid-template-columns:64px minmax(0,1fr) auto}.brand{justify-content:center;padding:0}.brand strong{display:none}.page-shell{grid-template-columns:64px minmax(0,1fr)}.status-bar>span:nth-of-type(n+4){display:none}.workspace-toolbar>.quiet-button{font-size:0}.workspace-toolbar>.quiet-button svg{margin:0}.transfer-button{font-size:0}.calendar-board{grid-template-columns:150px minmax(0,1fr) 250px}.calendar-board.is-table{grid-template-columns:150px minmax(0,1fr)}}
@media(max-width:680px){.course-calendar-page{height:auto;overflow:auto}.product-bar nav button:first-child,.product-bar nav svg,.product-actions button:first-child{display:none}.product-bar nav{padding:0 10px}.page-shell{height:auto;display:block}.calendar-main{min-height:calc(100vh - 52px)}.workspace-toolbar{flex-wrap:wrap}.toolbar-spacer{display:none}.primary-button{margin-left:auto}.status-bar>span{display:none}.calendar-board,.calendar-board.is-table{grid-template-columns:1fr}.session-rail{display:none}.session-inspector{min-height:430px;border-top:1px solid var(--lz-border);border-left:0}.month-scroll{min-height:500px}}
</style>
