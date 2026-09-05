<template>
  <div class="my-courses core-app-page core-app-page--flow">
    <!-- 二级顶栏（工具栏） -->
    <div class="toolbar">
      <div class="toolbar-left">
        <h2 class="page-title">我的课程</h2>
      </div>

      <div class="toolbar-right">
        <div class="search-box">
          <input
            type="text"
            class="search-input"
            placeholder="请输入课程名称、负责人或标签"
            v-model="searchQuery"
            @keydown.enter="handleSearch"
          />
          <button type="button" class="search-btn" aria-label="搜索" @click="handleSearch">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="11" cy="11" r="8" stroke="currentColor" stroke-width="2"/>
              <path d="m21 21-4.35-4.35" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </button>
        </div>
        <button type="button" class="btn-primary" @click="handleCreateCourse">
          <svg
            class="btn-primary-icon"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
          >
            <path
              d="M12 5v14M5 12h14"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
            />
          </svg>
          <span>新建课程</span>
        </button>
      </div>
    </div>

    <!-- 内容区域 -->
    <div class="content-area">
      <!-- 加载状态 -->
      <div v-if="coursesLoading" class="courses-loading">
        <p>加载中...</p>
      </div>
      <!-- 错误提示 -->
      <div v-else-if="coursesError" class="courses-error">
        <p>加载失败，请稍后重试</p>
        <button @click="loadCourses" class="retry-btn">重试</button>
      </div>
      <!-- 空状态 -->
      <div v-else-if="courses.length === 0" class="empty-state">
        <div class="empty-icon" aria-hidden="true">
          <svg width="80" height="80" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M4 4h16v12H4V4z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
            <path d="M8 20h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            <path d="M12 16v4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
        </div>
        <p class="empty-title">暂无课程</p>
        <p class="empty-desc">点击「新建课程」开始创建并管理课程</p>
      </div>
      <!-- 课程卡片列表（与「我的资源」卡片样式对齐） -->
      <div v-else class="courses-grid resource-card-grid resource-card-scope">
        <div
          v-for="course in courses"
          :key="course.id"
          class="resource-card course-resource-card"
          :style="{ '--course-accent-color': getCourseAccentColor(course.id) }"
          role="button"
          tabindex="0"
          @click="handleView(course.id)"
          @keydown.enter="handleView(course.id)"
        >
          <div class="course-card-accent" aria-hidden="true" />

          <div class="card-top">
            <div class="card-type-row" :style="{ color: getCourseAccentColor(course.id) }">
              <span class="card-type-label"></span>
            </div>
            <div class="card-menu-wrapper">
              <ResourceCardMenuButton @click="toggleCardMenu(course.id)" />
              <div
                v-if="openCardMenuId === course.id"
                class="card-menu-dropdown"
                @click.stop
              >
                <button type="button" class="card-menu-item" @click.stop="handleView(course.id)">
                  查看
                </button>
                <button
                  type="button"
                  class="card-menu-item card-menu-item--danger"
                  @click.stop="openDeleteModal(course.id)"
                >
                  删除
                </button>
              </div>
            </div>
          </div>

          <div class="card-bottom">
            <h3 class="file-name" :title="course.name">{{ course.name }}</h3>
            <div class="file-meta">
              {{ formatCourseHours(course.hours) }} | {{ formatCourseCredits(course.credits) }}
            </div>
            <div v-if="course.tags.length" class="tags-container">
              <span v-for="tag in course.tags" :key="tag" class="tag-badge">
                {{ tag }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <DeleteConfirmModal
      v-model="showDeleteModal"
      title="删除课程"
      entity-kind="课程"
      :entity-name="deleteCourseName"
      :pending="deletePending"
      :error="!!deleteError"
      :error-text="deleteError || '操作失败，请稍后重试'"
      @cancel="closeDeleteModal"
      @confirm="confirmDelete"
    />

  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { listCourses, operateCourse, visitMyCourses } from '../api/course'
import type { CourseListItem } from '../api/types'
import { OperationEnum } from '../api/types'
import DeleteConfirmModal from '../components/DeleteConfirmModal.vue'
import ResourceCardMenuButton from '../components/ResourceCardMenuButton.vue'
import { getCourseAccentColor, getCourseDisplayCode } from '../lib/courseCardTheme'
import { getStoredCourseCredits } from '../lib/courseOutlineBridge'
import '../assets/resource-card.css'

const router = useRouter()

const searchQuery = ref('')

// 课程列表（从 /course/list 接口获取）
interface CourseCard {
  id: string
  name: string
  hours: number
  credits: number | null
  tags: string[]
}
const courses = ref<CourseCard[]>([])
const coursesLoading = ref(false)
const coursesError = ref<string | null>(null)
const openCardMenuId = ref<string | null>(null)

function toCourseCard(item: CourseListItem): CourseCard {
  return {
    id: item.id,
    name: item.name,
    hours: item.lesson_count ?? 0,
    credits: getStoredCourseCredits(item.id),
    tags: item.labels ?? [],
  }
}

function formatCourseHours(hours: number): string {
  return hours > 0 ? `${hours} 课时` : '— 课时'
}

function formatCourseCredits(credits: number | null): string {
  if (credits == null) return '— 学分'
  return `${credits} 学分`
}

// 加载课程列表
async function loadCourses() {
  coursesLoading.value = true
  coursesError.value = null
  try {
    const params: { keyword?: string } = {}
    const keyword = searchQuery.value.trim() || undefined
    if (keyword) params.keyword = keyword
    const data = await listCourses(params)
    courses.value = data.map((item) => toCourseCard(item))
  } catch (err) {
    coursesError.value =
      err instanceof Error ? err.message : '加载课程列表失败'
    console.error('加载课程列表失败:', err)
    courses.value = []
  } finally {
    coursesLoading.value = false
  }
}

// 实时搜索：输入时防抖请求（300ms）
const searchDebounceTimer = ref<ReturnType<typeof setTimeout> | null>(null)
const SEARCH_DEBOUNCE_MS = 300

watch(searchQuery, () => {
  if (searchDebounceTimer.value) clearTimeout(searchDebounceTimer.value)
  searchDebounceTimer.value = setTimeout(() => {
    loadCourses()
    searchDebounceTimer.value = null
  }, SEARCH_DEBOUNCE_MS)
})

onMounted(() => {
  void visitMyCourses()
  loadCourses()
})

onBeforeUnmount(() => {
  if (searchDebounceTimer.value) clearTimeout(searchDebounceTimer.value)
  if (typeof window !== 'undefined') {
    window.removeEventListener('click', handleClickOutside)
  }
})

const handleSearch = () => {
  if (searchDebounceTimer.value) clearTimeout(searchDebounceTimer.value)
  searchDebounceTimer.value = null
  loadCourses()
}

function handleCreateCourse() {
  router.push('/newcourse-form')
}

function toggleCardMenu(courseId: string) {
  openCardMenuId.value = openCardMenuId.value === courseId ? null : courseId
}

const handleView = (courseId: string) => {
  openCardMenuId.value = null
  router.push(`/course/${courseId}`)
}

// 删除课程弹窗
const showDeleteModal = ref(false)
const deleteCourseId = ref<string | null>(null)
const deleteCourseName = ref('')
const deletePending = ref(false)
const deleteError = ref<string | null>(null)

function openDeleteModal(courseId: string) {
  openCardMenuId.value = null
  const course = courses.value.find((c) => c.id === courseId)
  deleteCourseId.value = courseId
  deleteCourseName.value = course?.name ?? ''
  deleteError.value = null
  showDeleteModal.value = true
}

function closeDeleteModal() {
  if (deletePending.value) return
  showDeleteModal.value = false
  deleteCourseId.value = null
  deleteCourseName.value = ''
  deleteError.value = null
}

async function confirmDelete() {
  const id = deleteCourseId.value
  if (!id || deletePending.value) return
  deletePending.value = true
  deleteError.value = null
  try {
    await operateCourse({ operation: OperationEnum.DELETE, id })
    // 须先结束 loading：closeDeleteModal 在 pending 时会直接 return，否则弹窗关不掉
    deletePending.value = false
    closeDeleteModal()
    await loadCourses()
  } catch (err) {
    deleteError.value = err instanceof Error ? err.message : '删除失败'
  } finally {
    deletePending.value = false
  }
}

const handleClickOutside = (event: MouseEvent) => {
  const target = event.target as HTMLElement
  if (!target.closest('.card-menu-wrapper')) {
    openCardMenuId.value = null
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('click', handleClickOutside)
}

</script>

<style scoped>
/* 工具栏与内容区同宽 1280px 居中（与「我的资源」对齐） */
.my-courses {
  --page-content-width: 1280px;
  --resource-card-gap: 24px;
  --resource-card-height: 230px;
}

.my-courses.core-app-page--flow .toolbar,
.my-courses.core-app-page--flow .content-area {
  width: min(calc(100% - 32px), var(--page-content-width));
  max-width: var(--page-content-width);
  margin-left: auto;
  margin-right: auto;
  box-sizing: border-box;
}

.my-courses.core-app-page--flow .toolbar {
  padding-left: 0;
  padding-right: 0;
}

.my-courses.core-app-page--flow .content-area {
  margin-left: auto;
  margin-right: auto;
}

.btn-primary {
  border: none;
  cursor: pointer;
  font-family: inherit;
}

/* 搜索框（胶囊，与「我的资源」一致） */
.search-box {
  display: flex;
  align-items: center;
  background-color: rgba(255, 255, 255, 0.7);
  border-radius: 999px;
  padding: 0 14px 0 16px;
  border: 1px solid #e0e0e0;
  transition: border-color 0.2s, background-color 0.2s;
  min-width: 200px;
  max-width: 320px;
  width: 100%;
  height: 40px;
  flex: 0 1 320px;
  gap: 6px;
  box-sizing: border-box;
}

.search-box:focus-within {
  border-color: #C5D9FF;
  background-color: #ffffff;
}

.search-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  padding: 0 4px;
  font-size: 13px;
  color: #333;
  min-width: 0;
}

.search-input::placeholder {
  color: #999;
}

.search-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #666;
  transition: color 0.2s;
  border-radius: 4px;
  flex-shrink: 0;
}

.search-btn:hover {
  color: #333;
}

/* 下拉框样式 */
.dropdown-wrapper {
  position: relative;
  flex-shrink: 0;
  z-index: 10;
}

.dropdown-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background-color: #ffffff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  color: #333;
  transition: all 0.2s;
  white-space: nowrap;
}

.dropdown-btn:hover {
  border-color: #C5D9FF;
  background-color: #f8f9ff;
}

.dropdown-btn svg {
  transition: transform 0.2s;
}

.dropdown-btn svg.rotate {
  transform: rotate(180deg);
}

.dropdown-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  background-color: #ffffff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  min-width: 200px;
  max-height: 280px;
  overflow-y: auto;
  z-index: 1000;
  padding: 8px;
}

.dropdown-item {
  padding: 10px 12px;
  font-size: 14px;
  color: #333;
  cursor: pointer;
  border-radius: 6px;
  transition: background-color 0.2s;
}
.dropdown-item:hover {
  background-color: #f5f5f5;
}
.dropdown-item.active {
  background-color: #e8f0fe;
  color: #1a73e8;
}

.dropdown-placeholder {
  padding: 12px;
  color: #999;
  font-size: 14px;
  text-align: center;
}

.courses-loading,
.courses-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: #666;
  font-size: 14px;
}

.courses-error p {
  color: #d32f2f;
  margin-bottom: 16px;
}

/* 空状态（统一风格） */
.empty-state {
  text-align: center;
  padding: 48px 24px;
}
.empty-icon {
  color: #bbb;
  margin-bottom: 20px;
}
.empty-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
  margin: 0 0 12px 0;
}
.empty-desc {
  font-size: 14px;
  color: #666;
  margin: 0 0 24px 0;
}
.empty-action-btn {
  display: inline-block;
  padding: 10px 24px;
  background-color: #C5D9FF;
  color: #333;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s;
}
.empty-action-btn:hover {
  background-color: #b0caff;
}

.retry-btn {
  padding: 8px 16px;
  background-color: #C5D9FF;
  border: none;
  border-radius: 8px;
  color: #333;
  font-size: 14px;
  cursor: pointer;
}

.retry-btn:hover {
  background-color: #a8c5ff;
}

/* 课程卡片网格（与「我的资源」对齐） */
.courses-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.course-resource-card {
  position: relative;
  overflow: hidden;
  padding-left: 30px;
}

.course-card-accent {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 6px;
  background: var(--course-accent-color, #1358e4);
  border-radius: 20px 0 0 20px;
}

@media (max-width: 1200px) {
  .courses-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .courses-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .courses-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 1200px) {
  .search-box {
    min-width: 160px;
    max-width: 260px;
    flex: 0 1 260px;
  }
}

@media (max-width: 900px) {
  .search-box {
    min-width: 140px;
    max-width: 220px;
    flex: 0 1 220px;
  }
}
</style>
