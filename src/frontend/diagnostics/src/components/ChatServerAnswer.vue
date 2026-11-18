<script setup lang="ts">
import { computed } from 'vue'
import type { ServerTurn } from '@/types/api/chat_types'
import DataTable from '@/components/base/DataTable.vue'

/**
 * What the search server answered when the chat used one of its tools directly, as it came (decision 98.c): an opened page
 * word for word, a page image, hits, the works. An answer other than found says so, in the server's own words.
 */
const props = defineProps<{
  server: ServerTurn
}>()

interface WorkEntry {
  work: string
  title?: string
  pages?: number
}

const answer = computed(() => props.server.answer)
// `works` answers with its list and no state; every other tool says found, nothing found, no image or error
const found = computed(() => !answer.value.state || answer.value.state === 'found')
const page = computed(() => (typeof answer.value.page === 'object' ? answer.value.page : null))
const asked = computed(() => Object.entries(props.server.args)
  .filter(([, value]) => value !== null && value !== undefined)
  .map(([name, value]) => `${name} ${String(value)}`)
  .join(' · '))
const works = computed(() => (props.server.tool === 'works' ? (answer.value.result ?? []) as WorkEntry[] : []))
</script>

<template>
  <div class="server-answer" :data-tool="server.tool">
    <p class="asked"><span class="tool">{{ server.tool }}</span><span v-if="asked" class="args"> · {{ asked }}</span></p>
    <p v-if="!found" class="not-found">
      {{ answer.state }}<template v-if="answer.why || answer.error">: {{ answer.why ?? answer.error }}</template>
    </p>
    <template v-else-if="server.tool === 'open_page'">
      <p class="page-head">
        <strong>{{ answer.title }}</strong> · page {{ page?.label }}<template v-if="page?.printed && page.printed !== page.label"> (printed {{ page.printed }})</template>
      </p>
      <!-- the page word for word, as the chat received it: text, never Markdown -->
      <pre class="page-text">{{ answer.text }}</pre>
    </template>
    <template v-else-if="server.tool === 'page_image'">
      <img v-if="server.image_src" class="page-image" :src="server.image_src" :alt="`page ${page?.label ?? ''} as the server sent it`">
      <p v-else class="not-found">The image is not kept in the turn log: ask again to see it.</p>
    </template>
    <ol v-else-if="answer.hits" class="hits ruled">
      <li v-for="(hit, at) in answer.hits" :key="at" class="hit">
        <RouterLink
          v-if="hit.view"
          :to="{ name: 'page', params: { kb: hit.view.knowledge_base, work: hit.view.source_id, page: hit.view.pdf_page } }"
        >
          {{ hit.title ?? hit.work }}
        </RouterLink>
        <span v-else>{{ hit.title ?? hit.work }}</span>
        <span class="place"> · p. {{ hit.page?.label }}<template v-if="hit.section"> · {{ hit.section }}</template></span>
        <p v-if="hit.snippet" class="snippet">{{ hit.snippet }}</p>
      </li>
    </ol>
    <DataTable v-else-if="works.length" table-class="works ruled">
      <tbody>
        <tr v-for="work in works" :key="work.work">
          <td>{{ work.title ?? work.work }}</td>
          <td class="pages">{{ work.pages ?? '' }}</td>
        </tr>
      </tbody>
    </DataTable>
    <pre v-else class="page-text">{{ JSON.stringify(answer, null, 1) }}</pre>
  </div>
</template>

<style scoped>
.asked,
.place,
.snippet,
.not-found {
  color: var(--color-text-secondary);
}

.tool {
  color: var(--color-text-primary);
}

.asked,
.page-head {
  margin-bottom: var(--space-xs);
}

.page-text {
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 24rem;
  overflow-y: auto;
}

.page-image {
  max-width: 100%;
  border: 1px solid var(--color-border);
}

.hits {
  padding-left: var(--space-lg);
}

.hit {
  margin-bottom: var(--space-xs);
}

.hit a {
  color: var(--color-accent);
  text-decoration: none;
}

.works td {
  padding: 2px var(--space-md) 2px 0;
}

.pages {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
</style>
