<template>
  <div class="admin-users-view">
    <div class="admin-toolbar">
      <h2 class="admin-page-title">用户管理</h2>
      <div class="admin-toolbar-actions">
        <input
          v-model="keyword"
          type="text"
          class="filter-input"
          placeholder="搜索 学工号 / 姓名 / 学院"
          @keyup.enter="reload"
        />
        <select v-model="roleFilter" class="filter-select">
          <option :value="null">全部角色</option>
          <option value="admin">管理员</option>
          <option value="teacher">教师</option>
          <option value="student">学生</option>
        </select>
        <button type="button" class="btn-secondary" :disabled="loading" @click="reload">
          {{ loading ? '加载中…' : '查询' }}
        </button>
      </div>
    </div>

    <div class="users-table-wrap">
      <table v-if="users.length > 0" class="users-table">
        <thead>
          <tr>
            <th>姓名</th>
            <th>学工号</th>
            <th>学院</th>
            <th class="col-role">角色</th>
            <th>注册时间</th>
            <th class="col-actions">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td>{{ u.name || '—' }}</td>
            <td>{{ u.zju_id || '—' }}</td>
            <td>{{ u.department || '—' }}</td>
            <td class="col-role">
              <span class="role-badge" :class="`role-${roleOf(u)}`">{{ roleLabel(roleOf(u)) }}</span>
            </td>
            <td>{{ u.create_time || '—' }}</td>
            <td class="col-actions">
              <button type="button" class="btn-link" @click="openRoleDialog(u)">改角色</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-else-if="loading" class="empty-state">加载中…</div>
      <div v-else-if="error" class="empty-state error">{{ error }}</div>
      <div v-else class="empty-state">暂无用户</div>

      <div v-if="users.length > 0 && hasMore" class="load-more-bar">
        <button type="button" class="btn-secondary" :disabled="loading" @click="loadMore">
          {{ loading ? '加载中…' : '加载更多' }}
        </button>
      </div>
    </div>

    <Teleport to="body">
      <Transition name="app-dialog">
        <div v-if="dialogOpen" class="app-dialog-overlay" @click.self="closeDialog">
          <div class="app-dialog-box" role="dialog" aria-modal="true" @click.stop>
            <h3 class="app-dialog-title">修改用户角色</h3>
            <div class="app-dialog-content">
              <div class="role-picker-target">
                <span class="picker-name">{{ target?.name || '—' }}</span>
                <span class="picker-zju">{{ target?.zju_id || '—' }}</span>
              </div>
              <div class="role-picker">
                <label v-for="r in roleOptions" :key="r.value" class="role-option" :class="{ active: pickedRole === r.value }">
                  <input v-model="pickedRole" type="radio" :value="r.value" :disabled="pending" />
                  <span class="role-option-text">
                    <span class="role-option-label">{{ r.label }}</span>
                    <span class="role-option-desc">{{ r.desc }}</span>
                  </span>
                </label>
              </div>
              <p v-if="isSelfDemote" class="role-warning">⚠️ 你即将把自己降级，确认后将立刻失去管理员入口。</p>
            </div>
            <div v-if="errorText" class="app-dialog-error">{{ errorText }}</div>
            <div class="app-dialog-footer">
              <button type="button" class="app-dialog-btn app-dialog-btn--cancel" :disabled="pending" @click="closeDialog">取消</button>
              <button
                type="button"
                class="app-dialog-btn"
                :class="isSelfDemote ? 'app-dialog-btn--danger' : 'app-dialog-btn--primary'"
                :disabled="pending || !target || pickedRole === roleOf(target!)"
                @click="confirmChange"
              >
                {{ pending ? '处理中…' : '确认修改' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import '../../assets/app-dialog.css'
import { fetchAdminUsers, updateUserRole } from '../../api/admin'
import { normalizeAppRole, type AdminUserDetail, type AppUserRole } from '../../api/types'
import { useUserStore } from '../../stores/user'

const PAGE_SIZE = 30

const userStore = useUserStore()

const users = ref<AdminUserDetail[]>([])
const keyword = ref('')
const roleFilter = ref<AppUserRole | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const offset = ref(0)
const hasMore = ref(true)

const dialogOpen = ref(false)
const target = ref<AdminUserDetail | null>(null)
const pickedRole = ref<AppUserRole>('student')
const pending = ref(false)
const errorText = ref('')

const roleOptions: { value: AppUserRole; label: string; desc: string }[] = [
  { value: 'admin', label: '管理员', desc: '可进运营后台，管理所有用户与智能体' },
  { value: 'teacher', label: '教师', desc: '可使用全部教学功能（大纲/教案/视频分析等）' },
  { value: 'student', label: '学生', desc: '仅可用 智能对话 / 智能体广场 / 论文检测 / 反馈' },
]

const isSelfDemote = computed(() => {
  return !!(
    target.value &&
    target.value.id === userStore.currentUser?.id &&
    pickedRole.value !== 'admin'
  )
})

function roleOf(u: AdminUserDetail): AppUserRole {
  return normalizeAppRole(u.role)
}

function roleLabel(r: AppUserRole): string {
  if (r === 'admin') return '管理员'
  if (r === 'teacher') return '教师'
  return '学生'
}

async function load(append: boolean) {
  loading.value = true
  error.value = null
  try {
    const list = await fetchAdminUsers({
      keyword: keyword.value.trim() || undefined,
      role: roleFilter.value,
      offset: append ? offset.value : 0,
      limit: PAGE_SIZE,
    })
    users.value = append ? [...users.value, ...list] : list
    offset.value = users.value.length
    hasMore.value = list.length === PAGE_SIZE
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
    hasMore.value = false
  } finally {
    loading.value = false
  }
}

async function reload() {
  await load(false)
}

async function loadMore() {
  await load(true)
}

function openRoleDialog(u: AdminUserDetail) {
  target.value = u
  pickedRole.value = roleOf(u)
  errorText.value = ''
  dialogOpen.value = true
}

function closeDialog() {
  if (pending.value) return
  dialogOpen.value = false
  target.value = null
}

async function confirmChange() {
  if (!target.value) return
  pending.value = true
  errorText.value = ''
  try {
    await updateUserRole(target.value.id, pickedRole.value)
    // 乐观更新本地行
    const idx = users.value.findIndex((x) => x.id === target.value!.id)
    if (idx >= 0) {
      users.value[idx] = { ...users.value[idx], role: pickedRole.value } as AdminUserDetail
    }
    // 自降级：刷新 store 立刻反映在 Navbar / 守卫
    if (target.value.id === userStore.currentUser?.id) {
      await userStore.fetchCurrentUser()
    }
    dialogOpen.value = false
    target.value = null
  } catch (e) {
    errorText.value = e instanceof Error ? e.message : '修改失败'
  } finally {
    pending.value = false
  }
}

onMounted(() => {
  void reload()
})
</script>

<style scoped>
.admin-users-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.admin-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.admin-page-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: #1a2540;
}

.admin-toolbar-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.filter-select,
.filter-input {
  height: 36px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid #d8deea;
  font-size: 14px;
  color: #1a2540;
  background: #fff;
}

.filter-input {
  width: 240px;
}

.filter-select:focus,
.filter-input:focus {
  outline: none;
  border-color: #4467d9;
}

.btn-primary,
.btn-secondary {
  height: 36px;
  padding: 0 16px;
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

.btn-secondary {
  background: #f0f4fb;
  color: #1f3c8b;
}

.btn-secondary:hover:not(:disabled) {
  background: #dde6f8;
}

.btn-primary:disabled,
.btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-link {
  background: transparent;
  border: none;
  color: #2f4aa6;
  cursor: pointer;
  font-size: 14px;
  padding: 0;
}

.btn-link:hover {
  text-decoration: underline;
}

.users-table-wrap {
  background: #fff;
  border-radius: 16px;
  padding: 16px;
  box-shadow: 0 2px 12px rgba(15, 28, 58, 0.05);
  overflow-x: auto;
}

.users-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 14px;
}

.users-table thead th {
  background: #f5f7fb;
  color: #4b5670;
  font-weight: 600;
  text-align: left;
  padding: 10px 12px;
  border-bottom: 1px solid #e6eaf2;
  white-space: nowrap;
}

.users-table tbody td {
  padding: 12px;
  color: #1a2540;
  border-bottom: 1px solid #f0f3f9;
  vertical-align: middle;
}

.col-role {
  width: 96px;
}

.col-actions {
  width: 90px;
  text-align: right;
}

.role-badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.role-badge.role-admin {
  background: #fde7e7;
  color: #b42318;
}

.role-badge.role-teacher {
  background: #e7eeff;
  color: #1f3c8b;
}

.role-badge.role-student {
  background: #f0f2f5;
  color: #4b5670;
}

.empty-state {
  padding: 48px 16px;
  text-align: center;
  color: #8a93a6;
  font-size: 14px;
}

.empty-state.error {
  color: #b42318;
}

.load-more-bar {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

.role-picker-target {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 12px 14px;
  margin-bottom: 16px;
  background: #f5f7fb;
  border-radius: 10px;
  font-size: 14px;
}

.picker-name {
  color: #1a2540;
  font-weight: 600;
  font-size: 15px;
}

.picker-zju {
  color: #8a93a6;
  font-size: 13px;
}

.role-picker {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.role-option {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid #e6eaf2;
  border-radius: 10px;
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease;
}

.role-option:hover {
  background: #f5f7fb;
}

.role-option.active {
  border-color: #2f4aa6;
  background: #eef3ff;
}

.role-option input {
  margin-top: 3px;
}

.role-option-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.role-option-label {
  font-weight: 600;
  color: #1a2540;
  font-size: 14px;
}

.role-option-desc {
  font-size: 12px;
  color: #4b5670;
  line-height: 1.4;
}

.role-warning {
  margin: 14px 0 0;
  padding: 10px 12px;
  background: #fff5e6;
  border: 1px solid #ffd591;
  border-radius: 8px;
  color: #b76800;
  font-size: 13px;
}
</style>
