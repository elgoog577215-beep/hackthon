import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import logger from '../utils/logger'
import { trackClientError } from '../utils/usage-tracker'
import { setActiveRequestIdentityScope, getQizhiAccessToken, type RequestIdentityScope } from '../utils/http'
import { setTeacherPreviewCourse } from '../utils/teacher-preview'
import { studyApi } from '../api/study'
import { getStudyToken, setStudyIdentity } from '../utils/study-identity'

declare module 'vue-router' {
  interface RouteMeta {
    identityScope?: RequestIdentityScope
  }
}

const routes: Array<RouteRecordRaw> = [
  ...(import.meta.env.DEV ? [{
    path: '/student-profile-demo', name: 'student-profile-demo',
    component: () => import('../views/KnowledgeProfileDemoView.vue'),
    meta: { publicConcept: true, fullscreenConcept: true, identityScope: 'learner' as const },
  }] : []),
  {
    path: '/study/:materialId?',
    name: 'study',
    component: () => import('../views/StudyView.vue'),
    meta: { identityScope: 'learner' },
  },
  {
    path: '/',
    redirect: import.meta.env.VITE_APP_SURFACE === 'student' ? '/study' : '/courses'
  },
  {
    path: '/courses',
    name: 'course-library',
    component: () => import('../views/TeacherTeachingCalendarView.vue'),
    meta: { identityScope: 'teacher' },
  },
  {
    path: '/workspace-concept',
    name: 'workspace-concept',
    component: () => import('../views/WorkspacePortalConceptView.vue'),
    meta: { publicConcept: true, identityScope: 'learner' }
  },
  {
    path: '/course/:courseId',
    redirect: to => ({ name: 'course-workspace', params: { courseId: to.params.courseId, mode: 'setup' } })
  },
  {
    path: '/course/:courseId/knowledge-first',
    name: 'course-knowledge-first',
    redirect: to => ({ name: 'course-workspace', params: { courseId: to.params.courseId, mode: 'setup' }, query: to.query }),
  },
  {
    path: '/course/:courseId/workspace/:mode(setup|build)?',
    name: 'course-workspace',
    component: () => import('../views/CourseWorkspaceView.vue'),
    props: true,
    meta: { identityScope: 'teacher' },
  },
  {
    path: '/course/:courseId/audit-updates/:planId?',
    name: 'course-audit-updates',
    component: () => import('../views/TeacherMaterialAuditReportView.vue'),
    props: true,
    meta: { identityScope: 'teacher' },
  },
  {
    path: '/course/:courseId/material-audit',
    name: 'course-material-audit',
    redirect: to => ({
      name: 'course-audit-updates',
      params: { courseId: to.params.courseId },
      query: { ...to.query, view: 'materials' },
    }),
  },
  {
    path: '/course/:courseId/changes/:planId?',
    name: 'course-change-workspace',
    redirect: to => ({
      name: 'course-audit-updates',
      params: {
        courseId: to.params.courseId,
        ...(to.params.planId ? { planId: to.params.planId } : {}),
      },
      query: { ...to.query, view: 'changes' },
    }),
  },
  {
    path: '/course/:courseId/learn/:nodeId?',
    name: 'learning',
    component: () => import('../views/LearningView.vue'),
    meta: { identityScope: 'learner' },
  },
  {
    path: '/course/:courseId/ppt',
    name: 'ppt-workspace',
    component: () => import('../views/PptWorkspaceView.vue'),
    meta: { identityScope: 'teacher' },
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: import.meta.env.VITE_APP_SURFACE === 'student' ? '/study' : '/courses'
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

router.beforeEach(async (to) => {
  if (import.meta.env.VITE_APP_SURFACE === 'student' && (to.meta.identityScope === 'teacher' || to.query.teacherPreview === '1')) return { name: 'study' }
  if (to.name === 'learning' && to.query.teacherPreview !== '1') {
    if (!getStudyToken() && !getQizhiAccessToken()) {
      const development = await studyApi.config().catch(() => null)
      if (!development?.development_identity) return { name: 'study', query: { returnTo: to.fullPath } }
    }
    try { setStudyIdentity(await studyApi.me()) }
    catch { setStudyIdentity(null); return { name: 'study', query: { returnTo: to.fullPath } } }
  }
  setTeacherPreviewCourse(to.name === 'learning' && to.query.teacherPreview === '1' ? String(to.params.courseId) : '')
  const scope = to.name === 'learning' && to.query.teacherPreview === '1'
    ? 'teacher'
    : to.meta.identityScope || 'learner'
  setActiveRequestIdentityScope(scope)
})

router.onError((error) => {
    trackClientError('router_error')
    logger.error('Router Error:', error)
})

export default router
