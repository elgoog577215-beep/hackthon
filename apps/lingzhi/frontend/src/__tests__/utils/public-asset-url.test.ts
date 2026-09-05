import { describe, expect, it } from 'vitest'
import { resolvePublicAssetUrl } from '../../utils/publicAssetUrl'

describe('resolvePublicAssetUrl', () => {
  it('places root-authored public assets under the deployed Vite base path', () => {
    expect(
      resolvePublicAssetUrl(
        '/presentation-assets/qizhi-classroom/chapter-opening.jpg',
        '/lingzhi/',
      ),
    ).toBe('/lingzhi/presentation-assets/qizhi-classroom/chapter-opening.jpg')
  })

  it('keeps local root deployments rooted at the site origin', () => {
    expect(
      resolvePublicAssetUrl(
        '/presentation-assets/qizhi-classroom/cover-learning-journey.jpg',
        '/',
      ),
    ).toBe('/presentation-assets/qizhi-classroom/cover-learning-journey.jpg')
  })

  it('does not rewrite absolute external or inline assets', () => {
    expect(resolvePublicAssetUrl('https://cdn.example.com/theme.jpg', '/lingzhi/'))
      .toBe('https://cdn.example.com/theme.jpg')
    expect(resolvePublicAssetUrl('data:image/png;base64,abc', '/lingzhi/'))
      .toBe('data:image/png;base64,abc')
  })
})
