import {mount} from '@vue/test-utils'
import {expect,it} from 'vitest'
import Header from '@/components/CompanionPanelHeader.vue'
it('keeps session actions collapsed until explicitly requested',async()=>{
 const view=mount(Header)
 expect(view.get('details.companion-session-menu').attributes('open')).toBeUndefined()
 expect(view.findAll('.companion-header-actions > button')).toHaveLength(1)
 await view.get('details summary').trigger('click')
 const action=view.findAll('details button')[0]!
 await action.trigger('click')
 expect(view.emitted('new')).toHaveLength(1)
 view.unmount()
})
