import { describe, expect, it } from 'vitest'
import { buildLearningTrajectoryStats } from '@/utils/learning-insights'

describe('buildLearningTrajectoryStats', () => {
  it('优先消费服务端学习轨迹快照', () => {
    const trajectory = buildLearningTrajectoryStats({
      learningState: {
        snapshot: {
          trajectory: {
            available: true,
            total_nodes: 8,
            completed_nodes: 3,
            completion_percentage: 37.5,
            quizzes_taken: 2,
            average_quiz_score: 58,
            weak_nodes: [
              { node_id: 'node-1', node_name: '极限定义', quiz_score: 42, reason: '课程节点测验分数偏低' },
            ],
            strong_nodes: [
              { node_id: 'node-2', node_name: '导数应用', quiz_score: 92, reason: '课程节点测验表现较好' },
            ],
            review: { overdue: 1, due_today: 0 },
          },
        },
      },
      courseNodes: [{ node_id: 'local-1', node_name: '本地节点' }],
      completedNodeIds: ['local-1'],
    })

    expect(trajectory.source).toBe('LearningOSSnapshot')
    expect(trajectory.totalNodes).toBe(8)
    expect(trajectory.completedCount).toBe(3)
    expect(trajectory.completionRate).toBe(38)
    expect(trajectory.averageQuizScore).toBe(58)
    expect(trajectory.weakAreas[0]).toMatchObject({ nodeId: 'node-1', name: '极限定义', quizScore: 42 })
    expect(trajectory.strengthAreas[0]).toMatchObject({ nodeId: 'node-2', name: '导数应用', quizScore: 92 })
    expect(trajectory.review.overdue).toBe(1)
  })

  it('没有快照时从正式本地投影生成轨迹', () => {
    const trajectory = buildLearningTrajectoryStats({
      courseNodes: [
        { node_id: 'node-1', node_name: '极限定义' },
        { node_id: 'node-2', node_name: '导数应用' },
      ],
      completedNodeIds: ['node-1'],
      wrongAnswers: [
        { nodeId: 'node-2', nodeName: '导数应用' },
        { nodeId: 'node-2', nodeName: '导数应用' },
      ],
      quizHistory: [
        { nodeId: 'node-1', nodeName: '极限定义', correctCount: 4, totalQuestions: 5 },
      ],
    })

    expect(trajectory.source).toBe('local')
    expect(trajectory.totalNodes).toBe(2)
    expect(trajectory.completedCount).toBe(1)
    expect(trajectory.completionRate).toBe(50)
    expect(trajectory.averageQuizScore).toBe(80)
    expect(trajectory.weakAreas[0]).toMatchObject({ nodeId: 'node-2', wrongCount: 2 })
    expect(trajectory.strengthAreas[0]).toMatchObject({ nodeId: 'node-1', accuracy: 80 })
  })
})
