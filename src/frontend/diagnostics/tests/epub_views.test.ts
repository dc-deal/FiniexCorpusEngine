import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { getEpubSection, getEpubWork } from '@/api/api_client'
import { router } from '@/router'
import EpubSectionView from '@/views/EpubSectionView.vue'
import EpubWorkView from '@/views/EpubWorkView.vue'
import type { EpubSection, EpubWork } from '@/types/api/epub_types'

vi.mock('@/api/api_client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/api_client')>(),
  getEpubWork: vi.fn(),
  getEpubSection: vi.fn(),
}))

enableAutoUnmount(afterEach)

// invented throughout (123.a): no licensed title, text or image stands in a test
const KEY = 'an_invented_book'

function aWork(overrides: Partial<EpubWork> = {}): EpubWork {
  return {
    knowledge_base: 'licensed', source_id: KEY, title: 'An Invented Book', file: 'an_invented_book.epub', route: 'epub, parsed by section',
    licence: 'private copy (licensed)',
    sections: 3, images: 2,
    outline: [
      { id: 'h1', title: 'Chapter One', parent: null, level: 1, label: 's1', first: 's1', last: 's2', sections: 2, chunks: 0 },
      { id: 'h2', title: 'A Subsection', parent: 'h1', level: 2, label: 's2', first: 's2', last: 's2', sections: 1, chunks: 0 },
      { id: 'h3', title: 'Chapter Two', parent: null, level: 1, label: 's3', first: 's3', last: 's3', sections: 1, chunks: 0 },
    ],
    rows: [
      { label: 's1', heading_path: 'Chapter One', characters: 120, images: 2 },
      { label: 's2', heading_path: 'Chapter One > A Subsection', characters: 40, images: 0 },
      { label: 's3', heading_path: 'Chapter Two', characters: 60, images: 0 },
    ],
    ...overrides,
  }
}

function aSection(overrides: Partial<EpubSection> = {}): EpubSection {
  return {
    knowledge_base: 'licensed', source_id: KEY, work_title: 'An Invented Book', label: 's1', heading_path: 'Chapter One',
    place: 'OEBPS/text/ch1.xhtml',
    parts: [
      { kind: 'text', text: 'The return is ', image: null },
      { kind: 'image', text: null, image: { href: 'OEBPS/images/eq 1.png', alt: 'eq1', inline: true } },
      { kind: 'text', text: ' per year.\n', image: null },
      { kind: 'image', text: null, image: { href: 'OEBPS/images/figure.jpg', alt: 'a figure', inline: false } },
    ],
    previous: null, next: 's2', ...overrides,
  }
}

describe('a licensed EPUB work (123.a)', () => {
  beforeEach(async () => {
    vi.mocked(getEpubWork).mockReset().mockResolvedValue(aWork())
    vi.mocked(getEpubSection).mockReset().mockResolvedValue(aSection())
    localStorage.clear()
    await router.push({ name: 'epub-work', params: { kb: 'licensed', work: KEY } })
  })

  it('shows its outline as an HTML work\'s, each heading opening its section on the EPUB\'s route, and counts no chunks', async () => {
    const view = mount(EpubWorkView, { props: { kb: 'licensed', work: KEY }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(view.find('.view-title').text()).toBe('An Invented Book')
    expect(view.find('[data-part="summary"]').text()).toContain('3 sections by heading · 2 images')
    expect(view.find('[data-part="licence"]').text()).toBe('private copy (licensed)')
    const links = view.findAll('.outline a.unit-title')
    expect(links.map(link => link.attributes('href'))).toEqual([`#/licensed/epub/${KEY}/s1`, `#/licensed/epub/${KEY}/s2`, `#/licensed/epub/${KEY}/s3`])
    expect(view.find('.outline').text()).not.toContain('chunk')
  })

  it('shows one section\'s text with each image where its mark stood: inline in its line, or a block of its own', async () => {
    await router.push({ name: 'epub-section', params: { kb: 'licensed', work: KEY, section: 's1' } })
    const view = mount(EpubSectionView, { props: { kb: 'licensed', work: KEY, section: 's1' }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(getEpubSection).toHaveBeenCalledWith('licensed', KEY, 's1')
    expect(view.find('[data-part="heading-path"]').text()).toBe('Chapter One')
    const body = view.find('[data-part="section-text"]')
    expect(body.text()).toContain('The return is')
    const inline = body.find('[data-part="inline-image"]')
    expect(inline.attributes('src')).toBe(`/api/licensed/epub/${KEY}/image?href=${encodeURIComponent('OEBPS/images/eq 1.png')}`)
    expect(inline.attributes('alt')).toBe('eq1')
    // the inline image stands between its line's two runs, the block after them
    const order = body.element.innerHTML
    expect(order.indexOf('The return is')).toBeLessThan(order.indexOf('data-part="inline-image"'))
    expect(order.indexOf('data-part="inline-image"')).toBeLessThan(order.indexOf('per year.'))
    const block = body.find('[data-part="block-image"] img')
    expect(block.attributes('alt')).toBe('a figure')
    expect(block.attributes('src')).toContain(encodeURIComponent('OEBPS/images/figure.jpg'))
    // the neighbours: none before the first section, the next one after it
    expect(view.find('[data-part="previous"]').exists()).toBe(false)
    expect(view.find('[data-part="next"]').attributes('href')).toBe(`#/licensed/epub/${KEY}/s2`)
  })
})
