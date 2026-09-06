import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SlideDeckBuildProgress from '@/components/SlideDeckBuildProgress.vue'

describe('SlideDeckBuildProgress V2', () => {
  it('renders the backend-owned dynamic work list and provider state', () => {
    const wrapper = mount(SlideDeckBuildProgress, {
      props: {
        progress: 42,
        stage: 'visual',
        progressV2: {
          schema_version: 'slide_build_progress_v2',
          event_type: 'heartbeat',
          task_id: 'v6-task',
          status: 'active',
          percent: 42,
          published: false,
          stage: 'visual',
          step_index: 5,
          step_count: 8,
          current_chapter_id: 'chapter-2',
          current_batch_id: 'visual-2',
          current_page_id: 'page-7',
          completed_items: 4,
          total_items: 8,
          completed_weight: 30,
          total_weight: 70,
          elapsed_seconds: 25,
          provider_wait: true,
          retry_attempt: 2,
          newly_discovered_work: 1,
          estimated_remaining_seconds: 33,
          failure: null,
          items: [
            { item_id: 'source', kind: 'local', stage: 'source', label: '冻结课程真源', status: 'completed' },
            { item_id: 'visual-2', kind: 'ai_batch', stage: 'visual', label: '视觉规划批次 2', status: 'running' },
            { item_id: 'render-7', kind: 'render_page', stage: 'render', label: '渲染第 7 页', status: 'pending' },
          ],
        },
      },
    })

    expect(wrapper.findAll('[data-build-work-item]')).toHaveLength(3)
    expect(wrapper.text()).toContain('视觉规划批次 2')
    expect(wrapper.text()).toContain('等待 AI 提供商')
    expect(wrapper.text()).toContain('第 2 次重试')
    expect(wrapper.text()).toContain('page-7')
    expect(wrapper.text()).toContain('新增 1 项工作')
    expect(wrapper.text()).not.toContain('读取课程源')
  })
})
