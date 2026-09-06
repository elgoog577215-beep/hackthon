import { createRouter, createWebHistory } from 'vue-router'
import { installRouteSlideTransition } from '../lib/routeTransition'
import { getStoredToken } from '../api/user'
import { useUserStore } from '../stores/user'
import type { AppUserRole } from '../api/types'
import HomeView from '../views/HomeView.vue'
/** 与首页等同：静态打包，避免线上仅 index 更新而懒加载 chunk 404/缓存不一致导致「Failed to fetch dynamically imported module」 */
import PptEmbedView from '../views/PptEmbedView.vue'

declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean
    requiresAuth?: boolean
    admin?: boolean
    // 命中其一即可（admin 同时通过 admin meta；teacher 命中 requiredRoles=['teacher','admin']）
    requiredRoles?: AppUserRole[]
  }
}

const TEACHER_ROLES: AppUserRole[] = ['teacher', 'admin']

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
      meta: { public: true },
    },
    {
      path: '/auth',
      name: 'auth',
      component: () => import('../views/AuthView.vue'),
      meta: { public: true },
    },
    {
      // 前端回调页：IdP 重定向到此（带 ?code=），再请求后端 GET /auth/callback 换 JWT
      path: '/auth/callback',
      name: 'auth-oauth-callback',
      component: () => import('../views/ZjuCallbackView.vue'),
      meta: { public: true },
    },
    {
      path: '/auth/zju/callback',
      name: 'auth-zju-callback',
      component: () => import('../views/ZjuCallbackView.vue'),
      meta: { public: true },
    },
    {
      path: '/resource/generate',
      name: 'resource-generate',
      component: () => import('../views/ResourceView.vue'),
      meta: { requiresAuth: true, requiredRoles: TEACHER_ROLES },
    },
    {
      path: '/resource/:id',
      name: 'resource',
      component: () => import('../views/ResourceView.vue'),
      props: true,
      meta: { requiresAuth: true, requiredRoles: TEACHER_ROLES },
    },
    {
      path: '/outline-form',
      name: 'outline-form',
      component: () => import('../views/OutlineFormView.vue'),
      meta: { requiresAuth: true, requiredRoles: TEACHER_ROLES },
    },
    {
      path: '/newcourse-form',
      name: 'newcourse-form',
      component: () => import('../views/NewCourseFormView.vue'),
      meta: { requiresAuth: true, requiredRoles: TEACHER_ROLES },
    },
    {
      path: '/my-courses',
      name: 'my-courses',
      component: () => import('../views/MyCoursesView.vue'),
      meta: { requiresAuth: true, requiredRoles: TEACHER_ROLES },
    },
    {
      path: '/lingzhi-entry',
      name: 'lingzhi-entry',
      component: () => import('../views/LingzhiEntryView.vue'),
      meta: { requiresAuth: true, requiredRoles: TEACHER_ROLES },
    },
    {
      path: '/chat',
      name: 'chat',
      component: () => import('../views/ChatView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/course/:id',
      name: 'course',
      component: () => import('../views/CourseView.vue'),
      props: true,
      meta: { requiresAuth: true, requiredRoles: TEACHER_ROLES },
    },
    // ===== 课程资源层级下钻：课程 → 大纲版本 → 教案版本 → PPT/视频 =====
    {
      path: '/course/:courseId/outline/:outlineId',
      name: 'course-outline',
      component: () => import('../views/OutlineDetailView.vue'),
      props: true,
      meta: { requiresAuth: true, requiredRoles: TEACHER_ROLES },
    },
    {
      path: '/course/:courseId/outline/:outlineId/plan/:planId',
      name: 'course-outline-plan',
      component: () => import('../views/PlanDetailView.vue'),
      props: true,
      meta: { requiresAuth: true, requiredRoles: TEACHER_ROLES },
    },
    {
      path: '/ppt-generate',
      name: 'ppt-generate',
      component: PptEmbedView,
      meta: { requiresAuth: true, requiredRoles: TEACHER_ROLES },
    },
    {
      path: '/resource-analysis',
      name: 'resource-analysis',
      component: () => import('../views/ResourceAnalysisListView.vue'),
      meta: { requiresAuth: true, requiredRoles: TEACHER_ROLES },
    },
    {
      path: '/resource-analysis/submit',
      redirect: '/resource-analysis',
    },
    {
      path: '/resource-analysis/report/:id',
      name: 'resource-analysis-report',
      component: () => import('../views/ResourceAnalysisReportView.vue'),
      props: true,
      meta: { requiresAuth: true, requiredRoles: TEACHER_ROLES },
    },
    {
      path: '/resource-analysis/report-new/:id',
      name: 'resource-analysis-report-new',
      component: () => import('../views/VideoAnalysisReportNewView.vue'),
      props: true,
      meta: { requiresAuth: true, requiredRoles: TEACHER_ROLES },
    },
    {
      path: '/resource-analysis/report-mock',
      name: 'resource-analysis-report-mock',
      component: () => import('../views/ResourceAnalysisReportView.vue'),
      props: () => ({ id: 'mock-video-report' }),
      meta: { requiresAuth: true, requiredRoles: TEACHER_ROLES },
    },

    // ===== 文档教学分析 =====
    {
      path: '/document-analysis',
      name: 'document-analysis',
      component: () => import('../views/DocumentAnalysisView.vue'),
      meta: { requiresAuth: true, requiredRoles: TEACHER_ROLES },
    },
    {
      path: '/document-analysis/compare',
      name: 'document-analysis-compare',
      component: () => import('../views/DocumentCompareView.vue'),
      meta: { requiresAuth: true, requiredRoles: TEACHER_ROLES },
    },

    // ===== 智云课堂视频分析（新入口） =====
    {
      path: '/smart-classroom-video-analysis',
      name: 'smart-classroom-video-analysis',
      component: () => import('../views/SmartClassroomVideoAnalysisCourseListView.vue'),
      meta: { requiresAuth: true, requiredRoles: TEACHER_ROLES },
    },
    {
      path: '/smart-classroom-video-analysis/course/:courseId',
      name: 'smart-classroom-video-analysis-course',
      component: () => import('../views/SmartClassroomVideoAnalysisCourseDetailView.vue'),
      props: true,
      meta: { requiresAuth: true, requiredRoles: TEACHER_ROLES },
    },
    {
      path: '/smart-classroom-video-analysis/sub/:subId',
      name: 'smart-classroom-video-analysis-sub',
      component: () => import('../views/SmartClassroomVideoAnalysisSubView.vue'),
      props: true,
      meta: { requiresAuth: true, requiredRoles: TEACHER_ROLES },
    },

    // ===== 论文分析（全员可用，含学生）=====
    {
      path: '/essay-check',
      name: 'essay-check',
      component: () => import('../views/EssayCheckListView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/essay-check/upload',
      name: 'essay-check-upload',
      component: () => import('../views/EssayCheckUploadView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/essay-check/:id',
      name: 'essay-check-detail',
      component: () => import('../views/EssayCheckDetailView.vue'),
      props: true,
      meta: { requiresAuth: true },
    },

    // ===== 运营后台 =====
    {
      path: '/admin',
      redirect: '/admin/dashboard',
    },
    {
      path: '/admin',
      component: () => import('../layouts/AdminLayout.vue'),
      meta: { admin: true },
      children: [
        {
          path: 'dashboard',
          name: 'admin-dashboard',
          component: () => import('../views/admin/AdminDashboardView.vue'),
        },
        {
          path: 'agents',
          name: 'admin-agents',
          component: () => import('../views/admin/AdminAgentsView.vue'),
        },
        {
          path: 'users',
          name: 'admin-users',
          component: () => import('../views/admin/AdminUsersView.vue'),
        },
        {
          path: 'feedbacks',
          name: 'admin-feedbacks',
          component: () => import('../views/admin/AdminFeedbacksView.vue'),
        },
        {
          path: 'audit-logs',
          name: 'admin-audit-logs',
          component: () => import('../views/admin/AdminAuditLogsView.vue'),
        },
      ],
    },
  ],
})

installRouteSlideTransition(router)

function isLocalhost(): boolean {
  try {
    const h = window.location.hostname
    return h === 'localhost' || h === '127.0.0.1'
  } catch {
    return false
  }
}

// 守卫顺序：public → token → currentUser → admin → requiredRoles
router.beforeEach(async (to, _from, next) => {
  const isPublic = to.matched.some((r) => r.meta.public === true)
  const requiresAdmin = to.matched.some((r) => r.meta.admin === true)
  const requiresAuth = to.matched.some((r) => r.meta.requiresAuth === true) || requiresAdmin
  const requiredRoles = to.matched.flatMap((r) => r.meta.requiredRoles ?? [])

  if (isPublic && !requiresAdmin) {
    next()
    return
  }

  // Token 校验：本机开发对非鉴权页面放行，避免反复跳登录
  const token = getStoredToken()
  if (!token) {
    if (isLocalhost() && !requiresAuth) {
      next()
      return
    }
    next({
      path: '/auth',
      query: to.path !== '/' && to.path !== '/auth' ? { redirect: to.fullPath } : {},
      replace: true,
    })
    return
  }

  // 拉取 currentUser（首次或缺失时）。失败回 /auth，避免短暂被当作 student 误拦
  const userStore = useUserStore()
  if (!userStore.currentUser) {
    const user = await userStore.fetchCurrentUser()
    if (!user) {
      next({ path: '/auth', query: { redirect: to.fullPath }, replace: true })
      return
    }
  }

  if (requiresAdmin && !userStore.isAdmin) {
    next({ path: '/' })
    return
  }

  if (requiredRoles.length && !requiredRoles.includes(userStore.role)) {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('rbac:denied', { detail: { roles: requiredRoles } }))
    }
    next({ path: '/' })
    return
  }

  next()
})

export default router
