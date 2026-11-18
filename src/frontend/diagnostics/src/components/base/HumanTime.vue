<script setup lang="ts">
import { computed } from 'vue'
import { sayClock, sayTime } from '@/human_time'

/**
 * A time as a person says it (`human_time`), in a `<time>` element that keeps the machine's value, its full form in the
 * reader's own zone in the hover. Under a heading that already names the day (`clock`), a time of another day says only
 * its clock. Nothing is shown for a time that is not there.
 */
const props = defineProps<{
  at: string | null | undefined
  clock?: boolean
}>()

const said = computed(() => (props.clock ? sayClock(props.at) : sayTime(props.at)))
</script>

<template>
  <time v-if="at" class="human-time" :datetime="at" :title="said.title">{{ said.text }}</time>
</template>
