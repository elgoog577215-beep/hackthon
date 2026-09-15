import { expect, test } from '@playwright/test'

test('admin can inspect engagement and task conversion metrics', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('auth_token', 'e2e-token')
    localStorage.setItem('auth_token_set_at', String(Date.now()))
  })

  await page.route('http://127.0.0.1:4174/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const dataByPath: Record<string, unknown> = {
      '/api/user/current': { id: 'admin-1', name: '测试管理员', zju_id: '001', department: '测试', role: 'admin' },
      '/api/admin/dashboard/stats': { total_users: 100, dau: 12, wau: 40, as_of: '2026-09-15 22:00' },
      '/api/admin/dashboard/behavior-metrics': {
        page_views: 80,
        unique_visitors: 40,
        sessions: 32,
        engaged_duration_ms: 320000,
        average_engaged_seconds: 10,
        bounce_count: 4,
        bounce_rate: 12.5,
        task_started: 20,
        task_succeeded: 15,
        task_failed: 3,
        task_cancelled: 1,
        task_completion_rate: 75,
        task_failure_rate: 15,
        task_cancellation_rate: 5,
        unfinished_tasks: 1,
        scroll_reach: { '25': 60, '50': 50, '75': 40, '100': 20 },
        latest_event_at: '2026-09-15 22:00',
      },
      '/api/admin/dashboard/feature-usage': [],
      '/api/admin/dashboard/agent-usage': [],
      '/api/admin/dashboard/users': [],
    }
    if (path === '/api/analytics/events') {
      await route.fulfill({ json: { success: true, data: { accepted: 1, duplicates: 0 } } })
      return
    }
    await route.fulfill({ json: { success: true, data: dataByPath[path] ?? null } })
  })

  const analyticsDelivered = page.waitForRequest((request) =>
    new URL(request.url()).pathname.endsWith('/analytics/events'),
  )
  await page.goto('/admin/dashboard')
  await expect(page.getByRole('heading', { name: '用户行为与任务转化' })).toBeVisible()
  await expect(page.getByText('12.5%')).toBeVisible()
  await expect(page.getByText('75%', { exact: true })).toBeVisible()
  await expect(page.getByText('10 秒', { exact: true })).toBeVisible()
  await expect(page.getByText('1 个取消任务')).toBeVisible()
  await analyticsDelivered
  const engagementDelivered = page.waitForRequest((request) =>
    new URL(request.url()).pathname.endsWith('/analytics/events'),
  )
  await page.evaluate(() => window.dispatchEvent(new Event('pagehide')))
  await engagementDelivered
})
