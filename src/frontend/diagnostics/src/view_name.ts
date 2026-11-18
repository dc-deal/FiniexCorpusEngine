import { watch } from 'vue'
import { useRouter } from 'vue-router'
import { useFrameStore } from '@/stores/frame_store'

/**
 * A view names itself for the header and the browser tab once its data says what it is, such as `Finance 2e p. 5`; until
 * then the frame shows the route's label. The name is taken with the address it was given at, and only when it changes:
 * a view on its way out sees the next address but no new name of its own, so it cannot lend its name to the next view.
 */
export function useViewName(name: () => string | null): void {
  const frame = useFrameStore()
  const router = useRouter()
  watch(name, value => {
    if (value) frame.nameView(router.currentRoute.value.path, value)
  }, { immediate: true })
}
