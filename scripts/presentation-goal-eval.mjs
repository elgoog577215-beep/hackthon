import { existsSync, readFileSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { homedir } from 'node:os'
import { join, resolve } from 'node:path'

const root = resolve(import.meta.dirname, '..')

function run(name, executable, args, cwd = root) {
  const windowsLauncher = process.platform === 'win32' && /\.(cmd|bat)$/i.test(executable)
  const command = windowsLauncher ? (process.env.ComSpec || 'cmd.exe') : executable
  const commandArgs = windowsLauncher ? ['/d', '/s', '/c', executable, ...args] : args
  // The native GOAL runner intentionally strips ambient environment fields.
  // Python on Windows derives its user site-packages (including pytest) from
  // APPDATA, so restore that deterministic OS location for child checks.
  const environment = {
    ...process.env,
    APPDATA: process.env.APPDATA || join(homedir(), 'AppData', 'Roaming'),
  }
  const result = spawnSync(command, commandArgs, {
    cwd,
    encoding: 'utf8',
    shell: false,
    env: environment,
    timeout: 240_000,
    windowsHide: true,
  })
  const output = `${result.stdout || ''}\n${result.stderr || ''}`.trim()
  return {
    name,
    pass: result.status === 0 && !result.error,
    exit: result.status,
    reason: result.error?.message || (result.status === 0 ? null : output.slice(-1200)),
  }
}

const backend = run(
  'presentation-backend-tests',
  'python',
  ['-m', 'pytest',
    'backend/tests/test_presentation_contracts.py',
    'backend/tests/test_presentation_repository.py',
    'backend/tests/test_presentation_services.py',
    'backend/tests/test_presentations_api.py',
    '-q'],
)

const frontendTests = run(
  'presentation-frontend-tests',
  'npm.cmd',
  ['run', 'test', '--',
    'src/__tests__/components/learning-view-task-flow.test.ts',
    'src/__tests__/router-learning-entry.test.ts',
    'src/__tests__/stores/presentation.test.ts',
    'src/__tests__/presentation'],
  resolve(root, 'frontend'),
)

const frontendBuild = run('frontend-build', 'npm.cmd', ['run', 'build'], resolve(root, 'frontend'))
const spec = run('openspec-strict', 'openspec.cmd', ['validate', 'add-courseware-workbench', '--strict'])

const browserProofPath = resolve(
  root,
  'openspec/changes/add-courseware-workbench/runs/courseware-mvp-20260715/verification/browser-proof.json',
)
let browser = { name: 'browser-proof', pass: false, exit: null, reason: 'browser proof is missing' }
if (existsSync(browserProofPath)) {
  try {
    const proof = JSON.parse(readFileSync(browserProofPath, 'utf8'))
    const screenshots = Array.isArray(proof.screenshots) ? proof.screenshots : []
    const screenshotFilesExist = screenshots.length >= 2 && screenshots.every(path => existsSync(resolve(root, path)))
    browser = {
      name: 'browser-proof',
      pass: proof.status === 'PASS' && proof.desktop === 'PASS' && proof.narrow === 'PASS' && screenshotFilesExist,
      exit: 0,
      reason: screenshotFilesExist ? proof.reason || null : 'browser screenshots are missing',
    }
  } catch (error) {
    browser.reason = String(error)
  }
}

const checks = [backend, frontendTests, frontendBuild, spec, browser]
const gate = (id, pass, reason, critical = true) => ({ id, status: pass ? 'PASS' : 'FAIL', critical, reason: pass ? null : reason })
const backendReason = backend.reason || 'presentation backend tests failed'
const frontendReason = [frontendTests, frontendBuild].find(item => !item.pass)?.reason || 'frontend checks failed'
const hardGates = [
  gate('G1', spec.pass && backend.pass && frontendBuild.pass, spec.reason || backendReason || frontendReason),
  gate('G2', backend.pass, backendReason),
  gate('G3', backend.pass, backendReason),
  gate('G4', backend.pass && frontendTests.pass, backend.reason || frontendTests.reason),
  gate('G5', backend.pass, backendReason),
  gate('G6', backend.pass, backendReason),
  gate('G7', frontendTests.pass && frontendBuild.pass && browser.pass, frontendTests.reason || frontendBuild.reason || browser.reason),
  gate('G8', backend.pass, backendReason),
]
const passed = hardGates.filter(item => item.status === 'PASS').length

process.stdout.write(JSON.stringify({
  hard_gates: hardGates,
  metrics: { score: Math.round((passed / hardGates.length) * 100) },
  checks,
}))
