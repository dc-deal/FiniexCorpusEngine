<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import ApiFailure from '@/components/ApiFailure.vue'
import KnowledgeBaseMark from '@/components/KnowledgeBaseMark.vue'
import LabelledLine from '@/components/base/LabelledLine.vue'
import LabelledLines from '@/components/base/LabelledLines.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import NumberedText from '@/components/base/NumberedText.vue'
import PagerLinks from '@/components/base/PagerLinks.vue'
import { useCodeStore } from '@/stores/code_store'
import { useViewName } from '@/view_name'
import { recordRoute } from '@/edition_route'
import type { KnowledgeBase } from '@/types/api/source_types'

/**
 * One file of a book's companion code (#12, the operator's 3.a, 23 Nov) as the librarian serves it: what the core's catalog
 * says of its unit, then its text as the publisher gave it, numbered as a citation counts its lines, in the one numbered look
 * (NumberedText). No highlighting, since no maintained grammar of the language exists; no image and no reading, which a file
 * has not. The lines a hit names (`?lines=12-31`) are marked and scrolled to. The previous and next file stay under the
 * pointer. The code is licensed, so it never leaves this machine: no screenshot, test or file holds it.
 */
const props = defineProps<{
  kb: KnowledgeBase
  work: string
  label: string
  lines?: string | null
}>()

const store = useCodeStore()
const { pageError } = storeToRefs(store)
const codeText = ref<InstanceType<typeof NumberedText> | null>(null)

watch(() => [props.kb, props.work, props.label] as const, ([kb, work, label]) => {
  void store.loadPage(kb, work, label)
}, { immediate: true })

const shown = computed(() => store.pageOf(props.kb, props.work, props.label))
useViewName(() => (shown.value ? `${shown.value.name} · ${shown.value.title}` : null))
const bookRoute = computed(() => (shown.value?.companion ? recordRoute(shown.value.companion, props.kb) : null))

// the lines the address names, as a hit's `view_url` gives them: "12-31"
const marked = computed(() => {
  const found = /^(\d+)-(\d+)$/.exec(props.lines ?? '')
  return found ? { first: Number(found[1]), last: Number(found[2]) } : null
})

// once the file stands, the lines asked for come into view
watch(() => [shown.value, marked.value] as const, async ([page, range]) => {
  if (!page || !range) return
  await nextTick()
  codeText.value?.scrollToLine(range.first)
}, { immediate: true })

function neighbour(label: string | null | undefined, name: string | null | undefined) {
  return label ? { to: { name: 'code-page', params: { kb: props.kb, work: props.work, label } }, label: name ?? label } : null
}
</script>

<template>
  <section class="code-page">
    <p class="trail" data-part="trail">
      <RouterLink to="/sources">Sources</RouterLink>
      <template v-if="shown?.companion">
        <span class="trail-step" aria-hidden="true"> › </span>
        <RouterLink v-if="bookRoute" :to="bookRoute" data-part="trail-book">{{ shown.companion.title }}</RouterLink>
        <span v-else data-part="trail-book">{{ shown.companion.title }}</span>
      </template>
      <span class="trail-step" aria-hidden="true"> › </span>
      <RouterLink :to="{ name: 'code-work', params: { kb, work } }" data-part="trail-work">{{ shown?.title ?? work }}</RouterLink>
      <KnowledgeBaseMark :kb="kb" />
    </p>
    <ApiFailure v-if="pageError" :error="pageError" @retry="store.loadPage(kb, work, label)" />
    <LoadingLine v-else-if="!shown" />
    <template v-else>
      <PagerLinks
        :previous="neighbour(shown.previous, shown.previous_name)"
        :next="neighbour(shown.next, shown.next_name)"
        width="16rem"
        label="Previous and next file"
      >
        <span class="position" data-part="position">file {{ shown.position }} of {{ shown.files }}</span>
      </PagerLinks>
      <h1 class="view-title" data-part="file-name">{{ shown.name }}</h1>
      <p class="place" data-part="place">{{ shown.label }}</p>
      <!-- what the core's catalog says of its unit; the sentence a model's, derived, never quoted -->
      <LabelledLines :label-chars="14" class="unit" data-part="unit">
        <template v-if="shown.unit">
          <LabelledLine label="Unit">{{ shown.unit.unit }} · {{ shown.unit.category }}</LabelledLine>
          <LabelledLine label="What it does">
            {{ shown.unit.summary }} <span class="derived" data-part="derived">{{ shown.unit.summary_is ?? 'derived' }}, never quoted</span>
          </LabelledLine>
          <LabelledLine v-if="shown.unit.inputs?.length" label="Inputs">
            <template v-for="(input, at) in shown.unit.inputs" :key="input.name"><template v-if="at"> · </template>{{ input.name }} = {{ input.default }}</template>
          </LabelledLine>
          <LabelledLine v-if="shown.unit.aliases?.length" label="Also called">{{ shown.unit.aliases.join(' · ') }}</LabelledLine>
          <LabelledLine v-if="shown.unit.source_named" label="Source named">{{ shown.unit.source_named }}</LabelledLine>
        </template>
        <LabelledLine v-else label="Unit"><span class="none">not in the catalog</span></LabelledLine>
        <LabelledLine label="Lines">
          {{ shown.lines.first }}–{{ shown.lines.last }}<template v-if="marked"> · {{ marked.first }}–{{ marked.last }} asked for</template>
        </LabelledLine>
        <LabelledLine label="Route">
          {{ shown.route }}<template v-if="shown.code_language"> · {{ shown.code_language }}</template><template v-if="shown.licence"> · {{ shown.licence }}</template>
        </LabelledLine>
      </LabelledLines>
      <NumberedText ref="codeText" class="code-text" data-part="code" :text="shown.text" :marked="marked" />
    </template>
  </section>
</template>

<style scoped>
.trail {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-xs);
}

.trail a {
  color: var(--color-accent);
  text-decoration: none;
}

.trail a:hover {
  text-decoration: underline;
}

.trail-step,
.place,
.position,
.derived,
.none {
  color: var(--color-text-secondary);
}

.place {
  margin-bottom: var(--space-sm);
  overflow-wrap: anywhere;
}

.unit {
  margin-bottom: var(--space-md);
}

/* the file in a frame of its own, the publisher's text, never the view's */
.code-text {
  padding: var(--space-sm);
  border: 1px solid var(--color-border);
}
</style>
