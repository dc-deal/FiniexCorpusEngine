// ported from the FiniexViewer with its facet bar (Y1.a, 260.a); `facetOption` and `pickFacet` are this app's (stage C)
import { flushPromises, type VueWrapper } from '@vue/test-utils'

/**
 * A facet's value as its panel draws it, opening the panel first where it is not open yet: the panel is portalled, so its
 * values are read off the document. A view must be mounted attached to the document, and unmounted after its test, so no
 * panel of another test stays behind.
 */
export async function facetOption(wrapper: VueWrapper, facet: string, value: string): Promise<HTMLElement> {
  const selector = `.facet-option[data-facet="${facet}"][data-value="${value}"]`
  if (!document.querySelector(selector)) {
    await wrapper.find(`.facet-trigger[data-facet="${facet}"]`).trigger('click')
    await flushPromises()
  }
  const option = document.querySelector<HTMLElement>(selector)
  if (!option) throw new Error(`the facet '${facet}' offers no '${value}'`)
  return option
}

/** Picks a facet's value, or lets it go where it is picked, as a click in its panel does. */
export async function pickFacet(wrapper: VueWrapper, facet: string, value: string): Promise<void> {
  (await facetOption(wrapper, facet, value)).click()
  await flushPromises()
}

/** Types into a facet bar's search, opening it first: it stands folded into ⌕ until asked for. */
export async function searchFor(wrapper: VueWrapper, text: string): Promise<void> {
  const toggle = wrapper.find('.facet-search-toggle')
  if (toggle.exists()) await toggle.trigger('click')
  await wrapper.find('.facet-search').setValue(text)
  await flushPromises()
}

/**
 * Chooses a sort from the bar's menu the way a keyboard does: the trigger opens it, the entry is
 * picked. The menu is portalled, so its entries are read off the document.
 */
export async function sortBy(wrapper: VueWrapper, label: string): Promise<void> {
  await wrapper.find('.facet-sort-trigger').trigger('keydown', { key: 'Enter' })
  await flushPromises()
  const entry = [...document.querySelectorAll<HTMLElement>('.facet-sort')]
    .find(node => node.textContent?.includes(label))
  if (!entry) throw new Error(`the sort menu offers no '${label}'`)
  entry.click()
  await flushPromises()
}
