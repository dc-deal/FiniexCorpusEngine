import { describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PageJump from '@/components/PageJump.vue'
import { router } from '@/router'
import { KELLY } from './page_fixture'

vi.mock('@/api/api_client', () => ({ getWorks: vi.fn() }))

function mountJump() {
  return mount(PageJump, { props: { kb: 'free', work: KELLY }, global: { plugins: [router] } })
}

async function type(jump: ReturnType<typeof mountJump>, typed: string): Promise<void> {
  await jump.find('input').setValue(typed)
  await jump.find('input').trigger('keydown', { key: 'Enter' })
  await flushPromises()
}

describe('PageJump', () => {
  beforeEach(async () => {
    await router.push('/sources')
  })

  it('opens the PDF page typed in, and empties the field', async () => {
    const jump = mountJump()
    await type(jump, ' 17 ')
    expect(router.currentRoute.value.fullPath).toBe(`/free/sources/${KELLY}/page/17`)
    expect((jump.find('input').element as HTMLInputElement).value).toBe('')
  })

  it('stays within the knowledge base it was given', async () => {
    const jump = mount(PageJump, { props: { kb: 'licensed', work: 'a_licensed_book' }, global: { plugins: [router] } })
    await type(jump, '3')
    expect(router.currentRoute.value.fullPath).toBe('/licensed/sources/a_licensed_book/page/3')
  })

  it.each(['abc', '0', '-3', '2.5', '1e2', ''])('stays where it is on %j, which is no PDF page', async typed => {
    const jump = mountJump()
    await type(jump, typed)
    expect(router.currentRoute.value.fullPath).toBe('/sources')
  })
})
