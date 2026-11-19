import { ref, watch } from 'vue'
import type { Ref } from 'vue'
import { useSettingsStore } from '@/stores/settings_store'
import type { FacetSelection } from '@/types/facet_types'

/**
 * A facet bar's state, kept with the stored settings so a reload (F5) shows the list the reader left (Y1.a: ported from the
 * FiniexViewer, whose rules the frontend follows, 260.a; it keeps them in its arrangement, this app in `settings.v1`).
 *
 * `FacetBar` holds no state and neither does this: the three refs belong to the view, and the composable only seeds them
 * from what was stored and writes them back. That keeps the bar reusable and puts the stored shape in exactly one place.
 *
 * **All three are kept, not only the facets.** A search REMOVES rows, so it narrows like a facet. A sort does not change
 * the set, but it is part of what the reader was looking at.
 */
export interface FacetState {
  selection: Ref<FacetSelection>
  search: Ref<string>
  sort: Ref<string>
}

export interface FacetStateOptions {
  /**
   * Applied where the reader never touched the bar, and from then on an ordinary selection: a chip shows it, the count says
   * what it leaves out, `clear` removes it, and a CLEARED bar stays cleared after a reload rather than getting the default
   * back. A default is never a filter the reader cannot see.
   */
  defaultSelection?: FacetSelection
  /**
   * What a narrowing is made FOR, such as one work's pages. A narrowing stored for another scope is dropped on the way in,
   * and one in force is dropped when the scope moves; the sort is kept in both cases, because it says how the reader likes
   * to read, not what.
   */
  scope?: () => string | null
}

/**
 * @param bar Names the bar's entry in the stored settings: one per bar, never shared.
 * @param defaultSort The sort of a bar nobody has sorted.
 */
export function useFacetState(bar: string, defaultSort: string, options: FacetStateOptions = {}): FacetState {
  const settings = useSettingsStore()
  const scope = options.scope ?? (() => null)
  const defaults = (): FacetSelection => ({ ...(options.defaultSelection ?? {}) })

  const stored = settings.settings.bars[bar]
  const current = stored && (stored.scope ?? null) === scope() ? stored : null

  const selection = ref<FacetSelection>(current?.selection ? { ...current.selection } : defaults())
  const search = ref(current?.search ?? '')
  const sort = ref(stored?.sort || defaultSort)

  watch(scope, () => {
    selection.value = defaults()
    search.value = ''
  })

  // written on a change only: a bar nobody touched stores nothing, so its defaults can still change with the build
  watch([selection, search, sort], () => {
    settings.setFacets(bar, {
      selection: { ...selection.value },
      search: search.value,
      sort: sort.value,
      scope: scope(),
    })
  }, { deep: true })

  return { selection, search, sort }
}
