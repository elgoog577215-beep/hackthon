import { defineStore } from 'pinia'
import http, { getTeacherIdentity } from '../utils/http'

export const TEACHING_CALENDAR_SAVED_EVENT = 'lingzhi:teaching-calendar-saved'
export const TEACHING_CALENDAR_SAVED_STORAGE_KEY = 'lingzhi_teaching_calendar_saved_v1'

export type TeachingCalendarStatus = 'draft' | 'ready'
export type ClassSessionStatus = 'unscheduled' | 'scheduled' | 'cancelled'

export interface ClassSession {
  session_id?: string
  lesson_unit_id?: string | null
  sequence: number
  date?: string | null
  start_time?: string | null
  end_time?: string | null
  content_summary: string
  requirements: string
  location: string
  teacher_name: string
  teaching_type: string
  group_code: string
  credit_hours?: number | null
  notes: string
  status: ClassSessionStatus
  source: 'manual' | 'outline' | 'import'
  course_id?: string
  course_title?: string
  course_color_key?: number
  calendar_revision?: number
  calendar_layer?: 'official' | 'incomplete'
  lesson_plan_status?: string
  ppt_status?: string
  has_conflict?: boolean
}

export interface TeachingCalendar {
  schema_version: 'teaching_calendar_v1'
  course_id: string
  course_title: string
  academic_year: string
  term: string
  timezone: string
  status: TeachingCalendarStatus
  source_outline_revision: string
  revision: number
  sessions: ClassSession[]
  created_at: string
  updated_at: string
}

export interface OutlineCalendarCandidate {
  candidate: TeachingCalendar
  candidate_count: number
  retained_count: number
  new_count: number
  current_revision: number
  projection?: {
    mode: 'outline_chapters' | 'legacy_roots'
    lesson_unit_count: number
    requested_session_count?: number | null
  }
  diff: {
    items: Array<{
      kind: 'add' | 'update' | 'keep' | 'stale'
      session_id?: string
      lesson_unit_id?: string | null
      title: string
      reason: string
      changes: Record<string, { before: string; after: string }>
    }>
    add_count: number
    update_count: number
    keep_count: number
    stale_count: number
  }
}

const messageFromError = (error: any, fallback: string) => {
  const detail = error?.response?.data?.detail
  return String(detail?.message || detail || error?.message || fallback)
}

const teacherRequestConfig = () => ({
  headers: { 'X-User-Id': getTeacherIdentity() },
})

const announceCalendarSaved = (calendar: TeachingCalendar) => {
  if (typeof window === 'undefined') return
  const detail = {
    courseId: calendar.course_id,
    revision: calendar.revision,
    updatedAt: calendar.updated_at,
    timestamp: Date.now(),
  }
  window.dispatchEvent(new CustomEvent(TEACHING_CALENDAR_SAVED_EVENT, { detail }))
  try {
    window.localStorage.setItem(TEACHING_CALENDAR_SAVED_STORAGE_KEY, JSON.stringify(detail))
  } catch {
    // Same-tab refresh still works when storage is unavailable.
  }
}

export const useTeachingCalendarStore = defineStore('teaching-calendar', {
  state: () => ({
    calendar: null as TeachingCalendar | null,
    totalSessions: [] as ClassSession[],
    totalRange: { dateFrom: '', dateTo: '' },
    loading: false,
    saving: false,
    deriving: false,
    error: '',
    conflictRevision: null as number | null,
  }),
  actions: {
    resetCourse() {
      this.calendar = null
      this.error = ''
      this.conflictRevision = null
    },
    async loadCourse(courseId: string) {
      this.loading = true
      this.error = ''
      try {
        const response = await http.get<TeachingCalendar>(
          `/api/courses/${courseId}/teaching-calendar`,
          teacherRequestConfig(),
        )
        this.calendar = response.data
        return response.data
      } catch (error) {
        this.error = messageFromError(error, '教学日历读取失败')
        throw error
      } finally {
        this.loading = false
      }
    },
    async deriveFromOutline(courseId: string) {
      this.deriving = true
      this.error = ''
      try {
        const response = await http.post<OutlineCalendarCandidate>(
          `/api/courses/${courseId}/teaching-calendar/derive-from-outline`,
          undefined,
          teacherRequestConfig(),
        )
        return response.data
      } catch (error) {
        this.error = messageFromError(error, '无法从教学大纲生成课次候选')
        throw error
      } finally {
        this.deriving = false
      }
    },
    async saveCourse(courseId: string, calendar: TeachingCalendar) {
      this.saving = true
      this.error = ''
      this.conflictRevision = null
      try {
        const response = await http.put<TeachingCalendar>(
          `/api/courses/${courseId}/teaching-calendar`,
          {
            base_revision: calendar.revision,
            course_title: calendar.course_title,
            academic_year: calendar.academic_year,
            term: calendar.term,
            timezone: calendar.timezone,
            status: calendar.status,
            source_outline_revision: calendar.source_outline_revision,
            sessions: calendar.sessions,
          },
          teacherRequestConfig(),
        )
        this.calendar = response.data
        announceCalendarSaved(response.data)
        return response.data
      } catch (error: any) {
        const detail = error?.response?.data?.detail
        if (error?.response?.status === 409) {
          this.conflictRevision = Number(detail?.current_revision ?? 0)
        }
        this.error = messageFromError(error, '教学日历保存失败')
        throw error
      } finally {
        this.saving = false
      }
    },
    async loadTotal(dateFrom: string, dateTo: string, includeIncomplete = false) {
      this.loading = true
      this.error = ''
      try {
        const response = await http.get<{ count: number; sessions: ClassSession[] }>('/api/teachers/me/teaching-calendar', {
          params: { date_from: dateFrom, date_to: dateTo, include_incomplete: includeIncomplete },
          ...teacherRequestConfig(),
        })
        this.totalSessions = response.data.sessions
        this.totalRange = { dateFrom, dateTo }
        return response.data.sessions
      } catch (error) {
        this.error = messageFromError(error, '教学总日历读取失败')
        throw error
      } finally {
        this.loading = false
      }
    },
  },
})
