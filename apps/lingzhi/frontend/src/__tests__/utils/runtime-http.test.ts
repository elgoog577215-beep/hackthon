import {afterEach,expect,it,vi} from 'vitest'

afterEach(()=>{vi.unstubAllEnvs();vi.unstubAllGlobals();vi.resetModules()})

it.each([false,true])('checks the backend before dispatching mutations (matching=%s)',async matching=>{
  vi.stubEnv('VITE_RUNTIME_ID','page-runtime');vi.resetModules()
  const fetcher=vi.fn(async(_input:unknown)=>({ok:true,json:async()=>({runtime_id:matching?'page-runtime':'another-runtime'})}))
  vi.stubGlobal('fetch',fetcher)
  const {default:http}=await import('@/utils/http')
  const adapter=vi.fn(async(config:any)=>({data:{ok:true},status:200,statusText:'OK',headers:{},config}))
  const request=http.post('/api/generate',{}, {adapter,silentError:true})
  if(matching){
    await expect(request).resolves.toMatchObject({data:{ok:true}})
    expect(adapter.mock.calls[0]![0].headers.get('X-Lingzhi-Runtime')).toBe('page-runtime')
  }else{
    await expect(request).rejects.toThrow();expect(adapter).not.toHaveBeenCalled()
  }
  expect(fetcher.mock.calls[0]?.[0]).toBe('/api/runtime')
})
