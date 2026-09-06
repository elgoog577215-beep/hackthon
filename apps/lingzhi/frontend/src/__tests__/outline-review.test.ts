import { afterEach, describe, expect, it, vi } from 'vitest'
import { setLocale } from '@/shared/i18n'
import { outlineReviewAction, outlineReviewEvidence, outlineReviewMessage } from '@/shared/outline-review'
import zh from '../../public/locales/zh/translation.json'
import en from '../../public/locales/en/translation.json'

afterEach(() => vi.unstubAllGlobals())

describe.each([['zh', zh], ['en', en]] as const)('outline review in %s', (locale, messages) => {
  it('shows original objective sentences and explains the limit of the heuristic', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => messages }))
    await setLocale(locale)
    const issue = {
      code: 'outline:repeated_objective_template', node_ids: ['one', 'two'],
      evidence: { examples: [{ title: '第一讲', text: '比较两种请求方法并说明理由' }] },
    }
    expect(outlineReviewMessage(issue)).toBe(messages.courseWorkbench.outlineReview.repeatedObjectives.replace('{count}', '2'))
    expect(outlineReviewEvidence(issue)).toEqual([
      messages.courseWorkbench.outlineReview.templateLimit,
      '第一讲: 比较两种请求方法并说明理由',
    ])
  })

  it('requires human input for unknown sources and identifies missing verification fields', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => messages }))
    await setLocale(locale)
    expect(outlineReviewAction({ code: 'missing_extension_resources', repair_mode: 'manual', repair_instruction: '补充参考资料' })).toBe('manual')
    expect(outlineReviewAction({ code: 'missing_extension_resources', repair_mode: 'ai', repair_instruction: '关联现有资料' })).toBe('ai')
    const issue = {
      code: 'outline:unverified_extension_resources', repair_instruction: '核验来源',
      evidence: { resources: [{ title: '第一讲', resource: '参考书', missing_fields: ['edition', 'locator'] }] },
    }
    expect(outlineReviewAction(issue)).toBe('manual')
    expect(outlineReviewEvidence(issue)[1]).toContain(messages.courseWorkbench.outlineReview.missingFields.edition)
    expect(outlineReviewEvidence(issue)[1]).toContain(messages.courseWorkbench.outlineReview.missingFields.locator)
    expect(outlineReviewEvidence(issue)[1]).not.toContain('missingFields.')
  })
})
