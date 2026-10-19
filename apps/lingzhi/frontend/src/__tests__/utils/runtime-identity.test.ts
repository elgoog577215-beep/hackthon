import {expect,it,vi} from 'vitest'
import {verifyRuntime} from '@/utils/runtime-identity'

it.each([undefined,'old-runtime'])('rejects a missing or different backend identity: %s',async id=>{
  const fetcher=vi.fn(async()=>({ok:true,json:async()=>({runtime_id:id})}))
  await expect(verifyRuntime('page-runtime',fetcher as any)).rejects.toThrow()
  expect(fetcher).toHaveBeenCalledTimes(1)
  expect(fetcher.mock.calls[0]?.[0]).toBe('/api/runtime')
})
it('rejects an old backend without a runtime endpoint',async()=>{
  await expect(verifyRuntime('page-runtime',vi.fn(async()=>({ok:false,status:404})) as any)).rejects.toThrow()
})
it('accepts only the matching runtime and skips the opt-in guard otherwise',async()=>{
  const fetcher=vi.fn(async()=>({ok:true,json:async()=>({runtime_id:'page-runtime',mode:'isolated'})}))
  expect(await verifyRuntime('page-runtime',fetcher as any)).toMatchObject({mode:'isolated'})
  fetcher.mockClear();await verifyRuntime('',fetcher as any);expect(fetcher).not.toHaveBeenCalled()
})
