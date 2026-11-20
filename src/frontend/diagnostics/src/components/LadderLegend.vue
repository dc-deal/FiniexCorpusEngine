<script setup lang="ts">
import DetailList from '@/components/base/DetailList.vue'
import HintPanel from '@/components/base/HintPanel.vue'
import type { Rung } from '@/types/api/ladder_types'

/**
 * What each level of the coverage ladder counts (U1.a): the registry's hint, the API's words for each level beneath its lead,
 * as the routes' legend gives the route levels'.
 */
defineProps<{
  rungs: Rung[]
}>()

const emit = defineEmits<{ close: [] }>()
</script>

<template>
  <HintPanel id="ladder" @close="emit('close')">
    <DetailList class="ladder-legend" data-part="ladder-legend">
      <template v-for="rung in rungs" :key="rung.level">
        <dt :data-level="rung.level">{{ rung.level }}</dt>
        <dd>{{ rung.means }}</dd>
      </template>
    </DetailList>
  </HintPanel>
</template>
