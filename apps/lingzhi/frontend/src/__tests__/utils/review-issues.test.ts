import { describe, expect, it } from 'vitest'
import {
  dedupeReviewIssues,
  reviewBlockingIssues,
  reviewIssueMessage,
  reviewIssueTarget,
} from '@/utils/review-issues'

describe('generation review issues', () => {
  it('把同一问题的重复条目合并，计数与列表因此一致', () => {
    // The same blocker commonly arrives from both blocking_issues and the
    // source chain; counting it twice told the teacher there were more
    // blockers than the list below actually showed.
    const artifact = {
      blocking_issues: [
        { code: 'source_missing', message: '缺少来源绑定', target_id: 'L2-1-1', severity: 'blocker' },
      ],
      source_chain: {
        issues: [
          { code: 'source_missing', message: '缺少来源绑定', target_id: 'L2-1-1', severity: 'blocker' },
          { code: 'source_missing', message: '缺少来源绑定', target_id: 'L2-1-2', severity: 'blocker' },
        ],
      },
    }

    const issues = reviewBlockingIssues(artifact)

    expect(issues).toHaveLength(2)
    expect(issues.map(issue => issue.target_id)).toEqual(['L2-1-1', 'L2-1-2'])
  })

  it('重复条目里的补充字段回填到保留的那条，不因去重丢信息', () => {
    const merged = dedupeReviewIssues([
      { code: 'x', message: '同一问题', target_id: 'n1' },
      { code: 'x', message: '同一问题', target_id: 'n1', suggestion: '补充来源后重试' },
    ])

    expect(merged).toHaveLength(1)
    expect(merged[0]!.suggestion).toBe('补充来源后重试')
  })

  it('不同目标或不同严重度不算重复', () => {
    const issues = dedupeReviewIssues([
      { message: '同一句', target_id: 'a', severity: 'blocker' },
      { message: '同一句', target_id: 'b', severity: 'blocker' },
      { message: '同一句', target_id: 'a', severity: 'warning' },
    ])

    expect(issues).toHaveLength(3)
  })

  it('空数组、null 条目与纯字符串条目都不会导致崩溃', () => {
    expect(reviewBlockingIssues(undefined)).toEqual([])
    expect(reviewBlockingIssues({})).toEqual([])
    const issues = dedupeReviewIssues([null, '纯字符串问题', undefined, '纯字符串问题'])
    expect(issues).toHaveLength(1)
    expect(reviewIssueMessage(issues[0])).toBe('纯字符串问题')
  })

  it('教案本地保底提示走 i18n，不直接显示内部 code', () => {
    const message = reviewIssueMessage({ code: 'teaching_plan:local_fallback' })
    expect(message).not.toContain('teaching_plan:local_fallback')
    expect(message.length).toBeGreaterThan(10)
  })

  it('目标 ID 兼容 target_id / node_id / asset_id 三种写法', () => {
    expect(reviewIssueTarget({ target_id: 't' })).toBe('t')
    expect(reviewIssueTarget({ node_id: 'n' })).toBe('n')
    expect(reviewIssueTarget({ asset_id: 'a' })).toBe('a')
    expect(reviewIssueTarget({})).toBe('')
  })
})
