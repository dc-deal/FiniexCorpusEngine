import { computed, onBeforeUnmount, ref, watch, type ComputedRef } from 'vue'

/**
 * The whole seconds since a start a person waits on (the operator, 21 Nov: "when I ask AI I need an hourglass while it
 * runs"), counted up each second while there is a start, 0 while there is none. Taken from the start's own time, so a view
 * opened again on a call still out counts on from where it stands, not from 0.
 */
export function useElapsed(since: () => number | null): ComputedRef<number> {
  const now = ref(Date.now())
  let timer: ReturnType<typeof setInterval> | undefined
  watch(since, start => {
    clearInterval(timer)
    timer = undefined
    now.value = Date.now()
    if (start !== null) timer = setInterval(() => { now.value = Date.now() }, 1000)
  }, { immediate: true })
  onBeforeUnmount(() => clearInterval(timer))
  return computed(() => {
    const start = since()
    return start === null ? 0 : Math.max(0, Math.floor((now.value - start) / 1000))
  })
}
