import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { presentationService, type PresentationDeckSnapshot } from '@/services/presentations'
import { usePresentationStore } from '@/stores/presentation'
import type { PresentationDeck, PresentationEvent, PresentationRevision, PresentationSlide } from '@/types/presentation'

const slide = (id: string, title: string): PresentationSlide => ({
  slide_id: id, position: id === 's1' ? 0 : 1, layout_id: 'L04', status: 'ready', title, subtitle: '', key_message: '', speaker_notes: '',
  blocks: [], source_refs: { section_ids: ['chapter-1'], block_ids: [`block-${id}`], block_revision_ids: [`rev-${id}`], objective_ids: [], asset_ids: [] },
  quality: { issues: [], capacity: {} },
})
const deck: PresentationDeck = {
  schema_version: 1, deck_id: 'deck-1', course_id: 'course-1', title: '指针课件',
  source_ref: { course_id: 'course-1', source_format: 'canonical', version_id: 'cv1', document_revision: '1', blueprint_revision_id: '', asset_bundle_revision_id: '', source_snapshot_id: 'source-1', source_snapshot_sha256: `sha256:${'a'.repeat(64)}` },
  scope: { type: 'chapter', section_ids: ['chapter-1'] }, purpose: 'teaching', template_id: 'lingzhi-engineering', status: 'editing', active_revision_id: 'revision-1', active_generation_id: null, latest_quality_report_id: null, latest_artifact_id: null, created_at: '', updated_at: '',
}
const revision: PresentationRevision = {
  revision_id: 'revision-1', parent_revision_id: null, deck_id: 'deck-1', reason: 'initial_generation', created_at: '', created_by: 'system', source_snapshot_id: 'source-1', slide_order: ['s1', 's2'], slides: [slide('s1', '第一页'), slide('s2', '第二页')],
}
const snapshot = (overrides: Partial<PresentationDeckSnapshot> = {}): PresentationDeckSnapshot => ({ deck, revision, revision_checksum: 'checksum-1', quality: null, artifact: null, ...overrides })
const event = (sequence: number, generationId: string, payloadSlide?: PresentationSlide): PresentationEvent => ({
  schema_version: 'presentation-event/v1', event_type: 'slide_upsert', deck_id: 'deck-1', generation_id: generationId,
  event_seq: sequence, outline_revision: 1, revision_id: null, emitted_at: '', payload: payloadSlide ? { slide: payloadSlide } : {},
})

describe('presentation store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('按 slide_id upsert，忽略重复序号和旧 generation', async () => {
    vi.spyOn(presentationService, 'get').mockResolvedValue(snapshot({
      deck: { ...deck, status: 'generating', active_generation_id: 'generation-new' },
      working: { generation_id: 'generation-new', event_seq: 1, outline_revision: 1, slide_order: ['s1', 's2'], slides: revision.slides },
    }))
    const store = usePresentationStore()
    await store.loadDeck('deck-1')

    await store.consumeEvent(event(2, 'generation-new', slide('s2', '第二页已更新')))
    await store.consumeEvent(event(2, 'generation-new', slide('s2', '重复事件不应覆盖')))
    await store.consumeEvent(event(3, 'generation-old', slide('s1', '旧流不应覆盖')))

    expect(store.slides).toHaveLength(2)
    expect(store.slides.find(item => item.slide_id === 's2')?.title).toBe('第二页已更新')
    expect(store.slides.find(item => item.slide_id === 's1')?.title).toBe('第一页')
    expect(store.lastSequence).toBe(2)
  })

  it('outline 与 patch 的部分字段会补齐默认值并保留既有 slide 内容', async () => {
    vi.spyOn(presentationService, 'get').mockResolvedValue(snapshot({
      deck: { ...deck, status: 'generating', active_generation_id: 'generation-new' },
      revision: null,
      working: { generation_id: 'generation-new', event_seq: 0, outline_revision: 1, slide_order: [], slides: [] },
    }))
    const store = usePresentationStore()
    await store.loadDeck('deck-1')

    await store.consumeEvent({
      ...event(1, 'generation-new'),
      event_type: 'deck_outline',
      payload: { slide_order: ['s1'], slides: [{ slide_id: 's1', position: 0, layout_id: 'L04', status: 'planned', title: '规划页' }] },
    })
    await store.consumeEvent({
      ...event(2, 'generation-new'),
      event_type: 'slide_patch',
      payload: { slide: { slide_id: 's1', status: 'generating', title: '正在生成' } },
    })

    expect(store.slides[0]?.blocks).toEqual([])
    expect(store.slides[0]?.layout_id).toBe('L04')
    expect(store.slides[0]?.title).toBe('正在生成')
    expect(store.slides[0]?.source_refs.section_ids).toEqual([])
  })

  it('发现 sequence 断档时重读 deck，不盲目应用跨序号事件', async () => {
    const get = vi.spyOn(presentationService, 'get')
      .mockResolvedValueOnce(snapshot({
        deck: { ...deck, status: 'generating', active_generation_id: 'generation-new' },
        working: { generation_id: 'generation-new', event_seq: 1, outline_revision: 1, slide_order: ['s1'], slides: [slide('s1', '服务端检查点')] },
      }))
      .mockResolvedValueOnce(snapshot({
        deck: { ...deck, status: 'generating', active_generation_id: 'generation-new' },
        working: { generation_id: 'generation-new', event_seq: 3, outline_revision: 1, slide_order: ['s1'], slides: [slide('s1', '重读后的真实状态')] },
      }))
    const store = usePresentationStore()
    await store.loadDeck('deck-1')

    const accepted = await store.consumeEvent(event(4, 'generation-new', slide('s1', '跨序号假状态')))

    expect(accepted).toBe(false)
    expect(get).toHaveBeenCalledTimes(2)
    expect(store.slides[0]?.title).toBe('重读后的真实状态')
    expect(store.lastSequence).toBe(3)
  })

  it('应用 proposal 只接收服务端新 revision，并将旧 artifact 标记为 stale', async () => {
    vi.spyOn(presentationService, 'get').mockResolvedValue(snapshot({ artifact: { artifact_id: 'artifact-1', deck_id: 'deck-1', revision_id: 'revision-1', page_count: 2, stale: false } }))
    const store = usePresentationStore()
    await store.loadDeck('deck-1')
    store.proposal = { proposal_id: 'proposal-1', request_id: 'request-1', deck_id: 'deck-1', base_revision_id: 'revision-1', scope: 'slide', slide_ids: ['s2'], prompt: '精简', patches: [], summary: '精简第二页', risks: [], status: 'proposed', created_at: '' }
    const nextRevision = { ...revision, revision_id: 'revision-2', parent_revision_id: 'revision-1', slides: [slide('s1', '第一页'), slide('s2', '第二页精简版')] }
    vi.spyOn(presentationService, 'applyProposal').mockResolvedValue(snapshot({
      deck: { ...deck, active_revision_id: 'revision-2', latest_artifact_id: 'artifact-1' },
      revision: nextRevision,
      artifact: { artifact_id: 'artifact-1', deck_id: 'deck-1', revision_id: 'revision-1', page_count: 2, stale: false },
    }))

    await store.applyProposal()

    expect(store.revision?.revision_id).toBe('revision-2')
    expect(store.slides.find(item => item.slide_id === 's1')?.title).toBe('第一页')
    expect(store.artifact?.stale).toBe(true)
    expect(store.canDownload).toBe(false)
  })

  it('最终质量门阻断时展示结构化问题和修复动作', async () => {
    vi.spyOn(presentationService, 'get').mockResolvedValue(snapshot())
    const store = usePresentationStore()
    await store.loadDeck('deck-1')
    store.setRenderMeasurement({ revision_id: 'revision-1', revision_checksum: 'checksum-1', overflow: false, collision: false, slide_count: 2 })
    vi.spyOn(presentationService, 'finalize').mockRejectedValue({
      response: { data: { detail: { message: '课件质量检查未通过', details: {
        report_id: 'quality-1', status: 'blocked', issues: [{
          code: 'missing_misconception', severity: 'blocking', message: '课程有常见误区，但课件没有误区页',
          target_type: 'deck', target_id: 'deck-1', fix_action: '增加一页 L08 常见误区并重新完成课件',
        }],
      } } } },
    })

    await store.finalize()

    expect(store.deck?.status).toBe('quality_blocked')
    expect(store.quality?.issues[0]?.code).toBe('missing_misconception')
    expect(store.quality?.issues[0]?.fix_action).toContain('L08')
    expect(store.error).toBe('课件质量检查未通过')
  })

  it('无当前 checksum 测量时阻止 finalize，并给出可操作等待提示', async () => {
    vi.spyOn(presentationService, 'get').mockResolvedValue(snapshot())
    const finalize = vi.spyOn(presentationService, 'finalize')
    const store = usePresentationStore()
    await store.loadDeck('deck-1')

    await store.finalize()

    expect(finalize).not.toHaveBeenCalled()
    expect(store.finalizing).toBe(false)
    expect(store.error).toContain('等待排版测量完成')
  })

  it('revision 或 checksum 变化时立即作废旧测量', async () => {
    const nextRevision = { ...revision, revision_id: 'revision-2', parent_revision_id: 'revision-1' }
    const get = vi.spyOn(presentationService, 'get')
      .mockResolvedValueOnce(snapshot())
      .mockResolvedValueOnce(snapshot({
        deck: { ...deck, active_revision_id: 'revision-2' }, revision: nextRevision, revision_checksum: 'checksum-2',
      }))
    const store = usePresentationStore()
    await store.loadDeck('deck-1')
    store.setRenderMeasurement({ revision_id: 'revision-1', revision_checksum: 'checksum-1', overflow: false, collision: false, slide_count: 2 })
    expect(store.measurementReady).toBe(true)

    await store.loadDeck('deck-1')

    expect(get).toHaveBeenCalledTimes(2)
    expect(store.revision?.revision_id).toBe('revision-2')
    expect(store.revisionChecksum).toBe('checksum-2')
    expect(store.renderMeasurement).toBeNull()
    expect(store.measurementReady).toBe(false)
  })
})
