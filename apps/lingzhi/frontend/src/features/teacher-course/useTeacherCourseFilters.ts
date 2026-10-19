import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { t, activeLocale } from '../../shared/i18n'
import { useCourseStore, type Course } from '../../stores/course'
import { useGenerationStore } from '../../stores/generation'
import { readCourseProductionStateWithLegacy } from '../../shared/teacher-production-state'

export type CourseStatusFilter = 'all' | 'preparing' | 'prepared'

export function courseTermKey(course: Course) {
  const year = String(course.academic_year || '').trim()
  const term = String(course.term || '').trim()
  return year || term ? `${year}\u0000${term}` : ''
}

export function courseTermLabel(course: Course) {
  return [course.academic_year, course.term].map(value => String(value || '').trim()).filter(Boolean).join(' ') || t('teacherCourseLibrary.termUnset')
}

/** List and calendar consume the same filters; the URL also preserves them on return. */
export function useTeacherCourseFilters() {
  const route = useRoute()
  const router = useRouter()
  const courses = useCourseStore()
  const generation = useGenerationStore()
  const query = ref(String(route.query.q || ''))
  const statusFilter = ref<CourseStatusFilter>(readStatus())
  const termFilter = ref(String(route.query.term || 'all'))
  function readStatus(): CourseStatusFilter {
    return route.query.status === 'preparing' || route.query.status === 'prepared' ? route.query.status : 'all'
  }
  function courseFilterKey(course: Course): Exclude<CourseStatusFilter, 'all'> {
    return readCourseProductionStateWithLegacy(course, generation.getTask(course.course_id)).preparation_state
  }
  const termMenuOptions = computed(() => {
    const terms = new Map<string, string>()
    courses.courseList.forEach(course => { const key = courseTermKey(course); if (key) terms.set(key, courseTermLabel(course)) })
    return [{ value: 'all', label: t('teacherCourseLibrary.allTerms') }, ...Array.from(terms, ([value, label]) => ({ value, label }))
      .sort((a, b) => b.label.localeCompare(a.label, activeLocale.value === 'zh' ? 'zh-CN' : 'en-US'))]
  })
  const termFilteredCourses = computed(() => {
    const keyword = query.value.trim().toLocaleLowerCase()
    return courses.courseList.filter(course => (
      (!keyword || [course.course_name, course.course_code, course.academic_year, course.term].some(value => String(value || '').toLocaleLowerCase().includes(keyword)))
      && (termFilter.value === 'all' || courseTermKey(course) === termFilter.value)
    ))
  })
  const filteredCourses = computed(() => statusFilter.value === 'all' ? termFilteredCourses.value : termFilteredCourses.value.filter(course => courseFilterKey(course) === statusFilter.value))
  const statusMenuOptions = computed(() => {
    const counts = { all: termFilteredCourses.value.length, preparing: 0, prepared: 0 }
    termFilteredCourses.value.forEach(course => { counts[courseFilterKey(course)] += 1 })
    return (['all', 'preparing', 'prepared'] as const).map(value => ({
      value, count: counts[value], label: t(`teacherCourseLibrary.${value === 'all' ? 'allCourses' : value === 'preparing' ? 'preparingCourses' : 'preparedCourses'}`),
    }))
  })
  watch([query, statusFilter, termFilter], () => {
    const next = { ...route.query }
    if (query.value) next.q = query.value; else delete next.q
    if (statusFilter.value !== 'all') next.status = statusFilter.value; else delete next.status
    if (termFilter.value !== 'all') next.term = termFilter.value; else delete next.term
    if (next.q !== route.query.q || next.status !== route.query.status || next.term !== route.query.term) void router.replace({ query: next })
  })
  watch(() => [route.query.q, route.query.status, route.query.term], () => {
    query.value = String(route.query.q || '')
    statusFilter.value = readStatus()
    termFilter.value = String(route.query.term || 'all')
  })
  const homeView = computed(() => route.query.view === 'calendar' ? 'calendar' : 'courses')
  function switchHomeTab(value: string) {
    void router.replace({ name: 'course-library', query: { ...route.query, view: value === 'calendar' ? 'calendar' : 'courses' } })
  }
  return { query, statusFilter, termFilter, filteredCourses, statusMenuOptions, termMenuOptions, courseFilterKey, homeView, switchHomeTab }
}
