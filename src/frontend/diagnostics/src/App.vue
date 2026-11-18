<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch, watchEffect } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute, useRouter } from 'vue-router'
import AppButton from '@/components/base/AppButton.vue'
import AppIcon from '@/components/base/AppIcon.vue'
import { useFrameStore } from '@/stores/frame_store'

/**
 * The frame: the tool's name as the app config gives it (decision 149.c), the overview and the name of the view on show,
 * and a menu holding every other view in four groups (the operator, 2026-11-10: a row of ten links was too big). The groups name
 * what a person comes for: to ask, to see what is held, to check the readings, to follow the runs and the calls.
 */
const MENU = [
  { group: 'Ask', routes: ['chat', 'search'] },
  { group: 'Holding', routes: ['sources', 'shelf'] },
  { group: 'Checks', routes: ['issues', 'errors', 'prompts'] },
  { group: 'Operations', routes: ['runs', 'calls'] },
] as const

const route = useRoute()
const router = useRouter()
const frame = useFrameStore()
const { info, error: infoError, named } = storeToRefs(frame)
const open = ref(false)
const menuRoot = ref<HTMLElement | null>(null)
const menuButton = ref<InstanceType<typeof AppButton> | null>(null)

// a link's word is its route's label, so the menu, the header and the tab say the same
const groups = MENU.map(({ group, routes }) => ({
  group,
  links: routes.map(name => ({ name, label: router.resolve({ name }).meta.label ?? name })),
}))

// a view of two panes side by side takes the wider container (160)
const wide = computed(() => route.meta.wide === true)

// the view's own name where it gave one for this address, else its route's label
const viewName = computed(() => (named.value?.path === route.path ? named.value.name : route.meta.label) ?? null)

void frame.loadInfo()

// `Capstone · Finance 2e p. 5`; with neither known yet, the page keeps the title it was served with
watchEffect(() => {
  const title = [info.value?.title, viewName.value].filter(Boolean).join(' · ')
  if (title) document.title = title
})

// the menu closes once it has done its work, and whenever the reader turns elsewhere
watch(() => route.fullPath, () => {
  open.value = false
})

function onKey(event: KeyboardEvent): void {
  if (!open.value || event.key !== 'Escape') return
  open.value = false
  ;(menuButton.value?.$el as HTMLElement | undefined)?.focus()
}

function onPointer(event: PointerEvent): void {
  if (open.value && menuRoot.value && !menuRoot.value.contains(event.target as Node)) open.value = false
}

onMounted(() => {
  document.addEventListener('keydown', onKey)
  document.addEventListener('pointerdown', onPointer)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKey)
  document.removeEventListener('pointerdown', onPointer)
})
</script>

<template>
  <!-- the bar's background spans the window; its row stands in the content's own container, so the two line up (160) -->
  <header class="frame-header">
    <div class="frame-row">
      <div ref="menuRoot" class="frame-menu-root">
        <AppButton
          ref="menuButton"
          variant="quiet"
          glyph
          class="menu-button"
          aria-label="Menu"
          title="Menu"
          aria-controls="frame-menu"
          :aria-expanded="open ? 'true' : 'false'"
          :marked="open"
          @click="open = !open"
        >
          <AppIcon name="menu" />
        </AppButton>
        <nav v-if="open" id="frame-menu" class="frame-menu" aria-label="Views">
          <section v-for="group in groups" :key="group.group" class="menu-group" :data-group="group.group">
            <h2 class="menu-group-title">{{ group.group }}</h2>
            <ul class="menu-links">
              <li v-for="link in group.links" :key="link.name">
                <RouterLink :to="{ name: link.name }">{{ link.label }}</RouterLink>
              </li>
            </ul>
          </section>
        </nav>
      </div>
      <span v-if="info" class="frame-title">
        <!-- the space inside the interpolation: the template drops one that leads a conditional element -->
        {{ info.title }}<span v-if="info.subtitle" class="frame-subtitle">{{ ` ${info.subtitle}` }}</span>
      </span>
      <!-- a name that did not load is said, with the API's sentence in the hover, and every view still works -->
      <span v-else-if="infoError" class="frame-subtitle" :title="infoError.message">name not loaded</span>
      <RouterLink to="/overview" class="frame-overview">Overview</RouterLink>
      <span v-if="route.name !== 'overview' && viewName" class="frame-view" :title="viewName">{{ viewName }}</span>
    </div>
  </header>
  <main class="frame-main" :class="{ wide }">
    <RouterView />
  </main>
</template>

<style scoped>
.frame-header {
  border-bottom: 1px solid var(--color-border);
  background-color: var(--color-bg-surface);
}

/* One content container for every view (decision 160): at most --content-max-width, centred, the page's gutter inside it,
   so a row stays readable and the eye does not travel across a wide screen; a view of two panes side by side, a page
   beside its reading or an article's original beside its chunks, takes the wider token. The header's row keeps the same
   width as the view below it, so the two line up. */
.frame-row,
.frame-main {
  max-width: var(--content-max-width);
  margin-inline: auto;
}

/* only the view's analysis takes the wide container (183): the header's row keeps the standard width, lined up with the
   view's record zone */
.frame-main.wide {
  max-width: var(--content-max-width-wide);
}

.frame-row {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-sm) var(--space-md);
}

.frame-menu-root {
  position: relative;
}

.frame-title {
  font-weight: bold;
  white-space: nowrap;
}

.frame-subtitle {
  font-weight: normal;
  color: var(--color-text-secondary);
}

.frame-overview {
  color: var(--color-accent);
  text-decoration: none;
}

.frame-overview:hover {
  text-decoration: underline;
}

/* the view on show is the one place this link is not an invitation */
.frame-overview.router-link-active {
  color: var(--color-text-primary);
}

/* the name of the view on show: plain ink, cut with an ellipsis where a work's title is long, whole in its hover */
.frame-view {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.frame-view::before {
  content: '›';
  margin-right: var(--space-sm);
  color: var(--color-text-secondary);
}

/* the panel opens beneath the button, over the view, in four columns of groups */
.frame-menu {
  position: absolute;
  top: calc(100% + var(--space-xs));
  left: 0;
  z-index: 10;
  display: grid;
  grid-template-columns: repeat(4, max-content);
  gap: var(--space-lg);
  padding: var(--space-md);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background-color: var(--color-bg-elevated);
  box-shadow: var(--shadow-overlay);
}

.menu-group-title {
  margin: 0 0 var(--space-xs);
  font-weight: normal;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.menu-links {
  margin: 0;
  padding: 0;
  list-style: none;
}

.menu-links li + li {
  margin-top: var(--space-xs);
}

.menu-links a {
  color: var(--color-accent);
  text-decoration: none;
}

.menu-links a:hover {
  text-decoration: underline;
}

.menu-links a.router-link-active {
  color: var(--color-text-primary);
}

.frame-main {
  padding: var(--space-md);
}
</style>
