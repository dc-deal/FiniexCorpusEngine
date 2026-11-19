<script setup lang="ts">
import AppIcon from '@/components/base/AppIcon.vue'
import HoverCard from '@/components/base/HoverCard.vue'
import { routeSaysWhy } from '@/route_why'

/** What a page row needs to say why it is served as it is. */
interface Served {
  error_message: string | null
  route: string
  route_level?: string | null
  route_why?: string | null
  from_text_layer: boolean
  check: { state: string }
}

/**
 * The Why of a page row, in every list of pages (decision 159.a): the provider's own sentence where it gave one, else, for a
 * route that is not served as checked, its level and why as the API parts them, the fallback with its glyph. The whole
 * route stands in the card under the pointer (203.a, the library's card where a browser tooltip stood), never repeated in
 * full on every row. A row of an export written before route levels says its whole route where it is worth saying, as
 * before (the operator's 25.a). A row that says nothing has no card.
 */
const props = defineProps<{
  row: Served
}>()

function showsWhy(): boolean {
  return props.row.route_level ? props.row.route_level !== 'checked' : routeSaysWhy(props.row)
}
</script>

<template>
  <HoverCard v-if="row.error_message || showsWhy()" title="Route" :rows="[{ label: 'level', value: row.route_level }, { label: 'route', value: row.route }]">
    <span class="route-why" :data-level="row.route_level ?? undefined">
      <template v-if="row.error_message">{{ row.error_message }}</template>
      <template v-else>
        <AppIcon v-if="row.route_level === 'fallback'" name="route-fallback" />
        {{ row.route_level ? (row.route_why ?? row.route) : row.route }}
      </template>
    </span>
  </HoverCard>
  <span v-else class="route-why" :data-level="row.route_level ?? undefined" />
</template>

<style scoped>
.route-why {
  color: var(--color-text-secondary);
}

.route-why :deep(.app-icon) {
  width: 1em;
  height: 1em;
  vertical-align: -0.125em;
}
</style>
