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
