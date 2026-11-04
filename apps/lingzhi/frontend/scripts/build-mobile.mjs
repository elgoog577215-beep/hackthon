import { spawnSync } from 'node:child_process'

const rawApiBase = String(process.env.LINGZHI_MOBILE_API_BASE_URL || '').trim()
if (!rawApiBase) {
  console.error('请先设置 LINGZHI_MOBILE_API_BASE_URL，指向手机端可访问的灵知 API 根路径。')
  process.exit(2)
}

let apiBase
try {
  const parsed = new URL(rawApiBase)
  if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error('invalid URL')
  }
  apiBase = parsed.toString().replace(/\/+$/, '')
} catch {
  console.error('LINGZHI_MOBILE_API_BASE_URL 必须是有效的 HTTP(S) 根路径，不能包含凭据、查询参数或片段。')
  process.exit(2)
}

const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm'
const env = {
  ...process.env,
  VITE_BASE_PATH: '/',
  VITE_APP_SURFACE: 'student',
  VITE_API_BASE_URL: apiBase,
}

function run(args) {
  const result = spawnSync(npm, args, { stdio: 'inherit', env })
  if (result.error) throw result.error
  if (result.status !== 0) process.exit(result.status || 1)
}

run(['run', 'build'])
run(['run', 'cap:sync'])
