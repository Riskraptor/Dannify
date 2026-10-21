import { describe, expect, it } from 'vitest'

// English for the pages opened later lives in a second file (en-more.js);
// by the time the window is drawn (localeReady) its words are there.
describe('the second English file', () => {
  it('is read before the app is drawn', async () => {
    const { t, localeReady } = await import('../i18n/index.js')
    await localeReady
    expect(t('recap.nav')).toBe('Your Soundtrack')
    expect(t('story.lately')).toBe('Your music lately')
    expect(t('problems.report')).not.toBe('problems.report')
    // And the first file's words, as ever.
    expect(t('nav.home')).not.toBe('nav.home')
  })
})
