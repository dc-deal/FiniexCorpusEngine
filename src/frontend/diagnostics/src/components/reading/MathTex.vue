<script setup lang="ts">
import { computed } from 'vue'
import katex from 'katex'

/**
 * LaTeX typeset by KaTeX, pinned to the version the core checks formulas with (0.19.1), so a formula renders here as it
 * was checked. KaTeX builds its markup from the LaTeX and escapes every character it does not typeset, and with `trust`
 * off it renders no link, class or style the LaTeX asks for. Beside the chat's Markdown, sanitised in `render_markdown`, it
 * is the one `v-html` in this UI. A formula KaTeX
 * refuses is shown in place with its error, never hidden.
 */
const props = defineProps<{
  latex: string
  display?: boolean
}>()

const html = computed(() => katex.renderToString(props.latex, {
  displayMode: props.display ?? false,
  throwOnError: false,
  trust: false,
  strict: 'ignore',
  output: 'htmlAndMathml',
}))
</script>

<template>
  <!-- eslint-disable-next-line vue/no-v-html -- KaTeX's own markup, built and escaped by KaTeX (see above) -->
  <span class="math" :class="{ display }" v-html="html" />
</template>

<style scoped>
.math.display {
  display: block;
  overflow-x: auto;
}
</style>
