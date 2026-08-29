import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import logger from '../utils/logger'
import { trackClientError } from '../utils/usage-tracker'
import { setActiveRequestIdentityScope, type RequestIdentityScope } from '../utils/http'

declare module 'vue-router' {
  interface RouteMeta {
    identityScope?: RequestIdentityScope
  }
}

const routes: Array<RouteRecordRaw> = [
  {
    path: '/',
    redirect: '/courses'
  },
  {
    path: '/courses',
    name: 'course-library',
    component: () => import('../views/TeacherTeachingCalendarView.vue'),
    meta: { identityScope: 'teacher' },
  },
  {
    path: '/teacher/courses',
    name: 'teacher-course-library',
    redirect: { name: 'course-library' }
  },
  {
    path: '/teacher/courses/new',
    name: 'teacher-course-create',
    redirect: { name: 'course-library', query: { view: 'courses', create: 'course' } }
  },
  {
    path: '/teacher-course-space',
    name: 'teacher-course-space',
    redirect: { name: 'course-library' }
  },
  {
    path: '/workspace-concept',
    name: 'workspace-concept',
    component: () => import('../views/WorkspacePortalConceptView.vue'),
    meta: { publicConcept: true, identityScope: 'learner' }
  },
  {
    path: '/workspace-concept/modes',
    name: 'workspace-mode-lab',
    component: () => import('../views/WorkspaceModeLabView.vue'),
    meta: { publicConcept: true, identityScope: 'learner' }
  },
  {
    path: '/workspace-concept/teacher-course-v1',
    name: 'teacher-course-production-concept',
    component: () => import('../views/TeacherCourseProductionConceptView.vue'),
    meta: { publicConcept: true, fullscreenConcept: true, identityScope: 'teacher' }
  },
  {
    path: '/course/:courseId',
    redirect: to => ({ name: 'course-workspace', params: { courseId: to.params.courseId, mode: 'setup' } })
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
    path: '/teacher/course/:courseId/overview',
    name: 'teacher-course-overview',
    redirect: to => ({ name: 'course-workspace', params: { courseId: to.params.courseId, mode: 'setup' } })
  },
  {
    path: '/teacher/course/:courseId/production',
    name: 'teacher-course-production',
    redirect: to => ({ name: 'course-workspace', params: { courseId: to.params.courseId, mode: 'setup' } })
  },
  {
    path: '/teacher/course/:courseId/outline',
    name: 'teacher-course-outline',
    redirect: to => ({ name: 'course-workspace', params: { courseId: to.params.courseId, mode: 'build' }, query: { section: 'outline' } })
  },
  {
    path: '/teacher/course/:courseId/release',
    name: 'teacher-course-release',
    redirect: to => ({
      name: 'learning',
      params: { courseId: to.params.courseId },
      query: { teacherPreview: '1' },
    })
  },
  {
    path: '/teacher/course/:courseId/files',
    name: 'teacher-course-files',
    redirect: to => ({ name: 'course-workspace', params: { courseId: to.params.courseId, mode: 'setup' } })
  },
  {
    path: '/teacher/course/:courseId/teaching-calendar',
    name: 'teacher-course-calendar',
    redirect: to => ({ name: 'course-workspace', params: { courseId: to.params.courseId, mode: 'setup' }, query: { section: 'calendar', ...(to.query.session ? { session: to.query.session } : {}) } })
  },
  {
    path: '/teacher/course/:courseId/ppt',
    name: 'teacher-ppt-workspace',
    redirect: to => ({ name: 'ppt-workspace', params: { courseId: to.params.courseId }, query: to.query })
  },
  {
    path: '/teacher/teaching-calendar',
    name: 'teacher-teaching-calendar',
    redirect: { name: 'course-library' }
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
    path: '/teacher',
    redirect: '/courses'
  },
  {
    path: '/teacher/:pathMatch(.*)*',
    redirect: '/courses'
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/courses'
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

router.beforeEach((to) => {
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
