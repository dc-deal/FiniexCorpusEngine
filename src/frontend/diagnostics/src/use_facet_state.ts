import { ref, watch } from 'vue'
import type { Ref } from 'vue'
import { useSettingsStore } from '@/stores/settings_store'
import type { FacetSelection } from '@/types/facet_types'

/**
 * A facet bar's state, kept with the stored settings so a reload (F5) shows the list the reader left (Y1.a: derived from the
 * FiniexViewer's, whose rules the frontend follows, 260.a; it keeps them in its arrangement, this app in `settings.v1`).
 *
 * `FacetBar` holds no state and neither does this: the three refs belong to the view, and the composable only seeds them
 * from what was stored and writes them back. That keeps the bar reusable and puts the stored shape in exactly one place.
 *
 * **All three are kept, not only the facets.** A search REMOVES rows, so it narrows like a facet. A sort does not change
 * the set, but it is part of what the reader was looking at.
 *
 * Left out of the viewer's (stage C, 19 Nov): a default selection and a scope a narrowing is made for. No view here uses
 * either: the sources list and the calls start unnarrowed, and the two lists whose narrowing belongs to something, the
 * issues and a work's pages, keep it in the address instead (24.a).
 */
export interface FacetState {
  selection: Ref<FacetSelection>
  search: Ref<string>
  sort: Ref<string>
}

/**
 * @param bar Names the bar's entry in the stored settings: one per bar, never shared.
 * @param defaultSort The sort of a bar nobody has sorted.
 */
export function useFacetState(bar: string, defaultSort: string): FacetState {
  const settings = useSettingsStore()
  const stored = settings.settings.bars[bar]

  const selection = ref<FacetSelection>({ ...(stored?.selection ?? {}) })
  const search = ref(stored?.search ?? '')
  const sort = ref(stored?.sort || defaultSort)

  // written on a change only: a bar nobody touched stores nothing, so its default sort can still change with the build
  watch([selection, search, sort], () => {
    settings.setFacets(bar, { selection: { ...selection.value }, search: search.value, sort: sort.value })
  }, { deep: true })

  return { selection, search, sort }
}
