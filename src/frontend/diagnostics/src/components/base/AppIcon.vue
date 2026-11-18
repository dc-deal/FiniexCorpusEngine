<script setup lang="ts">
import { computed } from 'vue'
import { ICONS, type IconName } from '@/icon_registry'

/**
 * An icon by what it means, drawn from the registry. It takes the colour of the element it sits in and
 * its size from that element's font, and it is hidden from a screen reader: an icon travels with a
 * word, and the word is what is read out.
 */
const props = defineProps<{
  name: IconName
}>()

const drawing = computed(() => ICONS[props.name])
</script>

<template>
  <component :is="drawing" class="app-icon" :data-icon="name" aria-hidden="true" />
</template>

<style scoped>
.app-icon {
  width: 1.2em;
  height: 1.2em;
  flex: none;
  vertical-align: text-bottom;
}
</style>
