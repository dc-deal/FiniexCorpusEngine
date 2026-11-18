<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import AppButton from '@/components/base/AppButton.vue'
import DataTable from '@/components/base/DataTable.vue'
import DetailList from '@/components/base/DetailList.vue'
import HintPanel from '@/components/base/HintPanel.vue'
import HintToggle from '@/components/base/HintToggle.vue'
import AppIcon from '@/components/base/AppIcon.vue'
import { useSettingsStore } from '@/stores/settings_store'
import type { RouteLevel, RouteRow } from '@/types/api/page_types'

/**
 * A work's routes, folded to one line by default (decision 159.a): "Routes 617 checked · 6 noted · 6 fallback", each level
 * with its pages as the API counts them, the fallback always named and, where it serves any page, in the warning role with
 * its glyph, since formulas and tables may be garbled in a text layer. Open or folded is kept with the other settings.
 * Opened, one row per route (the operator, 10 Nov: "is this route a faulty one?"): its level, source, reader, why and pages,
 * checked first and the fallback last. A row chosen keeps only its pages in the list below; chosen again, it lets them go;
 * a route chosen while the table is folded, as a shelf's link chooses one, says so in the line and can be let go there.
 * What each level means is a hint on demand.
 */
const props = defineProps<{
  routes: RouteRow[]
  levels: RouteLevel[]
}>()

// the routes the page list keeps; none chosen keeps every page
const chosen = defineModel<string[]>({ required: true })

const settingsStore = useSettingsStore()
const { settings } = storeToRefs(settingsStore)
const hintOpen = ref(false)

// the levels the line names: those serving a page, and the fallback always, so its absence is said too
const named = computed(() => props.levels.filter(level => level.pages > 0 || level.level === 'fallback'))

function says(level: string | null): string | undefined {
  return props.levels.find(one => one.level === level)?.says
}

function toggle(route: string): void {
  chosen.value = chosen.value.includes(route) ? chosen.value.filter(one => one !== route) : [...chosen.value, route]
}
</script>

<template>
  <div class="route-table">
    <div class="routes-line">
      <AppButton
        variant="quiet"
        class="routes-toggle"
        :aria-expanded="settings.routesOpen ? 'true' : 'false'"
        aria-controls="routes-table"
        data-part="routes-toggle"
        @click="settingsStore.setRoutesOpen(!settings.routesOpen)"
      >
        <span class="fold-mark" aria-hidden="true">{{ settings.routesOpen ? '▾' : '▸' }}</span>Routes
      </AppButton>
      <span
        v-for="level in named"
        :key="level.level"
        class="level-count"
        :class="{ warn: level.level === 'fallback' && level.pages > 0 }"
        :data-level="level.level"
        :title="level.says"
      >
        <AppIcon v-if="level.level === 'fallback' && level.pages > 0" name="route-fallback" />
        {{ `${level.pages.toLocaleString('en')} ${level.level}` }}
      </span>
      <HintToggle v-model:open="hintOpen" id="routes" />
      <span v-if="chosen.length && !settings.routesOpen" class="route-filter" data-part="route-filter">
        {{ chosen.length === 1 ? 'one route chosen' : `${chosen.length} routes chosen` }}
        <AppButton variant="link" data-part="route-filter-clear" @click="chosen = []">show every route</AppButton>
      </span>
    </div>
    <!-- the registry's hint, the API's words for each level beneath its lead (179) -->
    <HintPanel v-if="hintOpen" id="routes" @close="hintOpen = false">
      <DetailList class="route-legend" data-part="routes-legend">
        <template v-for="one in levels" :key="one.level">
          <dt :data-level="one.level">{{ one.level }}</dt>
          <dd>{{ one.says }}</dd>
        </template>
      </DetailList>
    </HintPanel>
    <!-- the library's table (179); the box takes the margin, as the table itself is the library's element -->
    <DataTable v-if="settings.routesOpen" id="routes-table" class="routes-box" table-class="routes ruled">
      <template #head>
        <tr>
          <th>Level</th>
          <th>Source</th>
          <th>Reader</th>
          <th>Why</th>
          <th class="number">Pages</th>
        </tr>
      </template>
      <tbody>
        <!-- the whole row is the target; its button carries the click for a keyboard, and the click rises to the row -->
        <tr
          v-for="route in routes"
          :key="route.route"
          class="route-row"
          :class="{ chosen: chosen.includes(route.route) }"
          :data-route="route.route"
          :data-level="route.level ?? 'none'"
          @click="toggle(route.route)"
        >
          <td>
            <span class="level" :title="says(route.level)">
              <AppIcon v-if="route.level === 'fallback'" name="route-fallback" />
              {{ route.level ?? 'no level' }}
            </span>
          </td>
          <td>
            <AppButton variant="link" :active="chosen.includes(route.route)" :title="route.route">{{ route.source }}</AppButton>
          </td>
          <td class="secondary">{{ route.reader ?? '' }}</td>
          <td>{{ route.why ?? '' }}</td>
          <td class="number">{{ route.pages.toLocaleString('en') }}</td>
        </tr>
      </tbody>
    </DataTable>
  </div>
</template>

<style scoped>
.route-table {
  margin-bottom: var(--space-sm);
}

.routes-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-xs) var(--space-sm);
}

.fold-mark {
  display: inline-block;
  width: 1.5ch;
}

.level-count {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  color: var(--color-text-secondary);
}

.level-count + .level-count::before {
  content: '·';
  margin-right: var(--space-xs);
  color: var(--color-text-secondary);
}

/* the fallback serving pages stands out: the warning role on its count, its glyph and its word together */
.level-count.warn {
  color: var(--color-warning);
}

.route-filter {
  display: inline-flex;
  align-items: baseline;
  gap: var(--space-sm);
  color: var(--color-text-primary);
}

.routes-box {
  margin-top: var(--space-xs);
}

/* a route's cells sit on one baseline, its glyph beside its level */
.route-row > td {
  vertical-align: baseline;
}

.route-row {
  cursor: pointer;
}

.route-row:hover > td {
  background-color: var(--color-bg-hover);
}

/* a row the list is narrowed to: the pressed look, as a chosen toggle has it */
.route-row.chosen > td {
  background-color: var(--color-bg-active);
}

.level {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 0 var(--space-xs);
  white-space: nowrap;
}

/* the glyph no taller than the word, so a row or the line keeps its height */
.level :deep(.app-icon),
.level-count :deep(.app-icon) {
  width: 1em;
  height: 1em;
}

/* the fallback stands out: the warning role on its border, its glyph and its word together */
[data-level='fallback'] .level {
  border-color: var(--color-warning);
  color: var(--color-warning);
}

.secondary {
  color: var(--color-text-secondary);
}

.route-legend {
  color: var(--color-text-secondary);
}

.route-legend dt[data-level='fallback'] {
  color: var(--color-warning);
}
</style>
