import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PresentationAiAside from '@/components/presentation/PresentationAiAside.vue'

const baseProps = {
  scopeType: 'chapter' as const,
  templateId: 'lingzhi-classroom' as const,
  purpose: 'teaching' as const,
  pageBudget: 8,
  requirements: '',
  selectedSlide: null,
  proposal: null,
  quality: null,
  error: null,
  progress: { completed: 0, total: 0, message: '' },
}

describe('PresentationAiAside', () => {
  it('只在创建配置阶段允许改变课件真值字段', () => {
    const configuring = mount(PresentationAiAside, {
      props: { ...baseProps, phase: 'configuring' },
    })
    expect(configuring.findAll('select').every(select => !select.attributes('disabled'))).toBe(true)

    const editing = mount(PresentationAiAside, {
      props: { ...baseProps, phase: 'editing' },
    })
    expect(editing.findAll('select').every(select => select.attributes('disabled') !== undefined)).toBe(true)
  })

  it.each(['model_unavailable', 'invalid_model_payload', 'slide_generation_failed'])(
    '质量问题 %s 出现时允许重新生成并复用 generate 事件',
    async (code) => {
      const wrapper = mount(PresentationAiAside, {
        props: {
          ...baseProps,
          phase: 'quality_blocked',
          quality: {
            status: 'blocked',
            issues: [{
              code,
              severity: 'blocking',
              message: '页面生成失败',
              target_type: 'slide',
              target_id: 'slide-1',
              fix_action: '重新生成课件',
            }],
          },
        },
      })

      const retry = wrapper.findAll('button').find(button => button.text() === '重新生成课件')
      expect(retry?.exists()).toBe(true)
      await retry?.trigger('click')
      expect(wrapper.emitted('generate')).toHaveLength(1)
    },
  )

  it('兼容旧版“页面未就绪 + 缺少内容槽”的 15 项质量报告', () => {
    const wrapper = mount(PresentationAiAside, {
      props: {
        ...baseProps,
        phase: 'quality_blocked',
        quality: {
          status: 'blocked',
          issues: [
            {
              code: 'slide_not_ready',
              severity: 'blocking',
              message: '第 1 页尚未就绪',
              target_type: 'slide',
              target_id: 'slide-1',
              fix_action: '重新生成或修复该页后再完成课件',
            },
            {
              code: 'layout_required_slot_missing',
              severity: 'blocking',
              message: '版式 L02 缺少必填内容槽：blocks。',
              target_type: 'slide',
              target_id: 'slide-1',
              fix_action: '补齐本页必填内容后重新检查',
            },
          ],
        },
      },
    })

    expect(wrapper.findAll('button').some(button => button.text() === '重新生成课件')).toBe(true)
  })

  it('正常编辑态不显示重试；重试生成中按钮禁用并显示进度', () => {
    const normal = mount(PresentationAiAside, {
      props: {
        ...baseProps,
        phase: 'editing',
        quality: { status: 'advisory', issues: [] },
      },
    })
    expect(normal.findAll('button').some(button => button.text() === '重新生成课件')).toBe(false)

    const configuring = mount(PresentationAiAside, {
      props: {
        ...baseProps,
        phase: 'configuring',
        quality: {
          status: 'blocked',
          issues: [{
            code: 'model_unavailable',
            severity: 'blocking',
            message: '模型不可用',
            target_type: 'slide',
            target_id: 'slide-1',
            fix_action: '检查模型后重试',
          }],
        },
      },
    })
    expect(configuring.findAll('button').some(button => button.text() === '重新生成课件')).toBe(false)

    const retrying = mount(PresentationAiAside, {
      props: {
        ...baseProps,
        phase: 'generating',
        generating: true,
        progress: { completed: 3, total: 8, message: '正在生成第 4 页' },
        quality: {
          status: 'blocked',
          issues: [{
            code: 'model_unavailable',
            severity: 'blocking',
            message: '模型不可用',
            target_type: 'slide',
            target_id: 'slide-1',
            fix_action: '检查模型后重试',
          }],
        },
      },
    })
    const retry = retrying.findAll('button').find(button => button.text().includes('正在重新生成课件'))
    expect(retry?.attributes('disabled')).toBeDefined()
    expect(retry?.text()).toContain('3 / 8')
  })
})
