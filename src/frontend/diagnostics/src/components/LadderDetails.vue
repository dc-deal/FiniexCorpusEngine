<script setup lang="ts">
import { computed } from 'vue'
import DetailList from '@/components/base/DetailList.vue'
import FoldSection from '@/components/base/FoldSection.vue'
import HumanTime from '@/components/base/HumanTime.vue'
import type { Ladder } from '@/types/api/ladder_types'

/**
 * A ladder's details, folded until asked for and then remembered (U1.a, the operator: "an expandable details part"): what
 * serves the text, by route; why a file is held from providers or not served; passed readings the search does not serve,
 * by why; the pages planned and passed; when the core built the shelf the first four levels come from. Every figure the API's.
 */
const props = defineProps<{
  ladder: Ladder
}>()

const unit = computed(() => props.ladder.unit)
const number = (value: number): string => value.toLocaleString('en')
const routes = computed(() => Object.entries(props.ladder.by_route ?? {}))
const unplaced = computed(() => Object.entries(props.ladder.unplaced ?? {}))
</script>

<template>
  <FoldSection class="ladder-details" title="details" remember="ladder.details" data-part="ladder-details">
    <DetailList>
      <template v-for="[route, count] in routes" :key="route">
        <dt :data-route="route">text by {{ route }}</dt>
        <dd>{{ number(count) }} {{ unit }}</dd>
      </template>
      <template v-if="ladder.held">
        <dt>held</dt>
        <dd data-part="held">{{ ladder.held }}</dd>
      </template>
      <template v-if="ladder.not_served">
        <dt>not served</dt>
        <dd data-part="not-served">{{ ladder.not_served }}</dd>
      </template>
      <template v-for="[why, count] in unplaced" :key="why">
        <dt>passed, not served</dt>
        <dd>{{ number(count) }}: {{ why }}</dd>
      </template>
      <template v-if="typeof ladder.planned === 'number'">
        <dt>planned</dt>
        <dd>{{ number(ladder.planned) }} {{ unit }}</dd>
      </template>
      <template v-if="typeof ladder.passed === 'number'">
        <dt>passed</dt>
        <dd>{{ number(ladder.passed) }} {{ unit }}</dd>
      </template>
      <template v-if="ladder.built_at">
        <dt>shelf built</dt>
        <dd><HumanTime :at="ladder.built_at" /></dd>
      </template>
    </DetailList>
  </FoldSection>
</template>
