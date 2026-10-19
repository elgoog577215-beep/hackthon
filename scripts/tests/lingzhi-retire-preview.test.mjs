import assert from 'node:assert/strict'
import test from 'node:test'
import { retiredPreviewHandler, redirectTarget } from '../lingzhi-retire-preview.mjs'

function request(method, url) {
  const headers = {}
  const response = { setHeader: (key, value) => { headers[key] = value }, end(body) { this.body = body } }
  retiredPreviewHandler('http://127.0.0.1:5183')({ method, url }, response)
  return { ...response, headers }
}

test('old lesson links retain their path and query and cannot redirect off the configured origin', () => {
  for (const prefix of ['', 'http://untrusted.example']) {
    const response = request('GET', `${prefix}/course/course-1/workspace/setup?stage=script&lesson=L1-5`)
    assert.equal(response.statusCode, 307)
    assert.equal(response.headers.Location, 'http://127.0.0.1:5183/course/course-1/workspace/setup?stage=script&lesson=L1-5')
    assert.equal(response.headers['Cache-Control'], 'no-store')
  }
})

test('cached isolated pages cannot send API calls or writes to the main course', () => {
  for (const [method, url] of [['GET', '/api/courses'], ['POST', '/api/changes'], ['POST', '/course/course-1'], ['GET', '/ws'], ['GET', '/assets/old.js']]) {
    const response = request(method, url)
    assert.equal(response.statusCode, 410)
    assert.equal(response.headers.Location, undefined)
    assert.equal(JSON.parse(response.body).error, 'preview_retired')
  }
})

test('retirement targets are local frontend origins', () => {
  for (const target of ['https://example.com', 'http://127.0.0.1:5183/api', 'http://user:pass@localhost:5183', 'http://localhost:5183/?next=external']) {
    assert.throws(() => redirectTarget(target))
  }
})
