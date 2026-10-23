import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import StudyDialoguePanel from '@/components/StudyDialoguePanel.vue'
import { useAITeacherStore, type AIConversation } from '@/stores/aiTeacher'
import { useCourseStore } from '@/stores/course'
import { useNoteStore } from '@/stores/notes'
import { useLearnerModelStore } from '@/stores/learnerModel'

const initial = ():AIConversation => ({ conversation_id:'study1', course_id:'c', revision:1, title:'Note', created_at:'', updated_at:'', messages:[], study_workspace:{ kind:'note',revision:1,course_version_id:'cv',node_id:'n',node_name:'Lecture',quote:'The passage',anchor:{block_id:'b'},record_id:'note1',saved_revision:0,draft:'',assisted:false,proposal:null,versions:[],nearby:[],knowledge:[],checks:[] } })
describe('study dialogue editing', () => {
  it('uses a readable short answer in the passage without workspace tabs and teaching toolbars',async()=>{
    const ai=useAITeacherStore()
    ai.currentConversation!.messages=[{message_id:'reply',role:'assistant',content:'先找内层 3x+1，再看外层平方。',status:'complete'}] as AIConversation['messages']
    wrapper=mount(StudyDialoguePanel,{props:{conversation:ai.currentConversation!,compact:true},global:{stubs:{MarkdownRenderer:{props:['content'],template:'<div>{{content}}</div>'}}}})
    expect(wrapper.find('.study-tabs').exists()).toBe(false)
    expect(wrapper.find('.study-teaching-actions').exists()).toBe(false)
    expect(wrapper.find('.study-source').exists()).toBe(false)
    expect(wrapper.get('.study-body').text()).toContain('先找内层')
    expect(wrapper.find('.study-composer').exists()).toBe(false)
    expect(wrapper.find('[data-testid="companion-expand"]').exists()).toBe(false)
    const long='较长的数学说明'.repeat(120)
    ai.currentConversation!.messages[0]!.content=long
    await flushPromises()
    expect(wrapper.text()).not.toContain(long)
    expect(wrapper.text()).toContain('readingCompanion.longReply')
    await wrapper.get('[data-testid="companion-expand"]').trigger('click')
    expect(wrapper.emitted('expand')).toHaveLength(1)
    await wrapper.setProps({compact:false})
    expect(wrapper.find('.study-tabs').exists()).toBe(true)
    expect(wrapper.text()).toContain(long)
  })
  it('offers an explicit one-step teaching action without changing the source or saving a note', async () => {
    const view=start()
    await view.get('[data-teaching-action="step"]').trigger('click');await flushPromises()
    expect(useAITeacherStore().studyCommand).toHaveBeenCalledWith('study1',expect.objectContaining({action:'discuss',teaching_action:'step'}))
    expect(useNoteStore().loadCourseRecords).not.toHaveBeenCalled()
    expect(useLearnerModelStore().load).not.toHaveBeenCalled()
  })
  let wrapper:ReturnType<typeof mount> | undefined
  beforeEach(() => {
    localStorage.clear(); setActivePinia(createPinia())
    const course = useCourseStore(); course.currentCourseId='c'; course.currentCourseVersionId='cv'
    const ai = useAITeacherStore(); ai.courseId='c'; ai.conversations=[initial()]; ai.currentConversationId='study1'
    vi.spyOn(useNoteStore(),'loadCourseRecords').mockResolvedValue([])
    vi.spyOn(useLearnerModelStore(),'load').mockResolvedValue(null)
    vi.spyOn(ai,'studyCommand').mockImplementation(async (_id,payload) => {
      const conversation=structuredClone(JSON.parse(JSON.stringify(ai.currentConversation))) as AIConversation
      const ws=conversation.study_workspace!
      if(payload.action==='draft') ws.draft=String(payload.text)
      if(payload.action==='discuss') { ws.draft='A continuously updated note'; ws.assisted=true; ws.solution_seen=true }
      if(payload.action==='adopt') { ws.draft=ws.proposal!; ws.proposal=null; ws.assisted=true }
      if(payload.action==='save') ws.saved_revision++
      ws.revision++
      ai.conversations=[conversation]
      return conversation
    })
  })
  afterEach(() => { wrapper?.unmount(); vi.restoreAllMocks() })
  function start() {
    wrapper=mount(defineComponent({ components:{StudyDialoguePanel}, setup(){return {ai:useAITeacherStore()}}, template:'<StudyDialoguePanel :conversation="ai.currentConversation" />' }), {global:{stubs:{MarkdownRenderer:{props:['content'],template:'<div>{{content}}</div>'}}}})
    return wrapper
  }
  it('automatically updates the draft after dialogue but saves only on confirmation', async () => {
    const view=start(), ai=useAITeacherStore()
    await view.get('.study-composer textarea').setValue('Help me explain this passage')
    await view.get('.study-composer').trigger('submit'); await flushPromises()
    expect(ai.currentConversation?.study_workspace?.draft).toBe('A continuously updated note')
    expect(useNoteStore().loadCourseRecords).not.toHaveBeenCalled()
    expect(useLearnerModelStore().load).not.toHaveBeenCalled()
    expect(view.get('[role="status"]').text()).toContain('studyDialogue.autoDraftUpdated')
    await view.findAll('.study-tabs button')[1]!.trigger('click')
    expect((view.get('.study-editor textarea').element as HTMLTextAreaElement).value).toBe('A continuously updated note')
    expect(view.find('.study-proposal').exists()).toBe(false)
    expect(view.findAll('.study-actions button')).toHaveLength(1)
    await view.get('.study-editor textarea').setValue('My final edited note')
    await view.get('.study-actions button').trigger('click'); await flushPromises()
    expect(ai.currentConversation?.study_workspace?.record_id).toBe('note1')
    expect(ai.currentConversation?.study_workspace?.draft).toBe('My final edited note')
    expect(useNoteStore().loadCourseRecords).toHaveBeenCalledWith('c')
    expect(useLearnerModelStore().load).not.toHaveBeenCalled()
  })
  it('keeps edits made while the AI reply is pending', async () => {
    const view=start(), ai=useAITeacherStore()
    let finish!: (response:AIConversation)=>void
    vi.mocked(ai.studyCommand).mockImplementation(()=>new Promise(resolve=>{ finish=resolve }))
    await view.get('.study-composer textarea').setValue('Explain this')
    await view.get('.study-composer').trigger('submit'); await flushPromises()
    await view.findAll('.study-tabs button')[1]!.trigger('click')
    expect(view.get('.study-editor textarea').attributes('disabled')).toBeUndefined()
    await view.get('.study-editor textarea').setValue('My edit made while waiting')
    const response=initial(); response.study_workspace!.draft='AI draft from earlier input';response.study_workspace!.revision=2
    ai.conversations=[response];finish(response);await flushPromises()
    expect((view.get('.study-editor textarea').element as HTMLTextAreaElement).value).toBe('My edit made while waiting')
    expect(view.get('[role="status"]').text()).toContain('studyDialogue.manualDraftKept')
    expect(useNoteStore().loadCourseRecords).not.toHaveBeenCalled()
  })
  it('preserves unsaved input across a failed action and reopening', async () => {
    let view=start()
    await view.findAll('.study-tabs button')[1]!.trigger('click')
    await view.get('.study-editor textarea').setValue('Keep this draft')
    vi.mocked(useAITeacherStore().studyCommand).mockRejectedValue({response:{status:409}})
    await view.get('.study-actions button').trigger('click'); await flushPromises()
    expect(view.get('[role="alert"]').text()).toContain('studyDialogue.conflict')
    expect(view.get('.study-actions button').attributes('disabled')).toBeDefined()
    expect(view.get('[role="alert"] button').attributes('disabled')).toBeUndefined()
    view.unmount(); view=start()
    await view.findAll('.study-tabs button')[1]!.trigger('click')
    expect((view.get('.study-editor textarea').element as HTMLTextAreaElement).value).toBe('Keep this draft')
  })
  it('lets the learner compose the next question without erasing it when a reply arrives', async () => {
    const view = start(), ai = useAITeacherStore()
    let finish!: (response: AIConversation) => void
    vi.mocked(ai.studyCommand).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await view.get('.study-composer textarea').setValue('First question')
    await view.get('.study-composer').trigger('submit'); await flushPromises()
    expect(view.get('.study-composer textarea').attributes('disabled')).toBeUndefined()
    await view.get('.study-composer textarea').setValue('Next question typed while waiting')
    const response = initial(); response.study_workspace!.revision = 2
    ai.conversations = [response]; finish(response); await flushPromises()
    expect((view.get('.study-composer textarea').element as HTMLTextAreaElement).value).toBe('Next question typed while waiting')
  })
  it('does not scroll the editable draft when a chat answer arrives', async () => {
    const view = start(), ai = useAITeacherStore()
    let finish!: (response: AIConversation) => void
    vi.mocked(ai.studyCommand).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await view.get('.study-composer textarea').setValue('Explain this')
    await view.get('.study-composer').trigger('submit'); await flushPromises()
    await view.findAll('.study-tabs button')[1]!.trigger('click')
    const body = view.get('.study-body').element as HTMLElement
    body.scrollTop = 65
    const response = initial(); response.messages = [{ message_id: 'a', role: 'assistant', content: 'Long reply', status: 'complete' }] as AIConversation['messages']
    response.study_workspace!.revision = 2
    ai.conversations = [response]; finish(response); await flushPromises()
    expect(body.scrollTop).toBe(65)
  })
  it('does not offer an unbound mastery check or allow edits to historical sources', async () => {
    const view=start()
    await view.findAll('.study-tabs button')[2]!.trigger('click')
    expect(view.text()).toContain('studyDialogue.noKnowledge')
    expect(view.find('select').exists()).toBe(false)
    useCourseStore().currentCourseVersionId='new'
    await view.findAll('.study-tabs button')[1]!.trigger('click')
    expect(view.get('.study-editor textarea').attributes('disabled')).toBeDefined()
    expect(useAITeacherStore().studyCommand).not.toHaveBeenCalled()
  })
})
