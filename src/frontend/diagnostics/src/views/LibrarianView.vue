<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import ApiFailure from '@/components/ApiFailure.vue'
import AppButton from '@/components/base/AppButton.vue'
import FoldSection from '@/components/base/FoldSection.vue'
import LoadingLine from '@/components/base/LoadingLine.vue'
import LibrarianAnswer from '@/components/librarian/LibrarianAnswer.vue'
import SchemaForm from '@/components/librarian/SchemaForm.vue'
import { argumentsFromQuery, argumentsOf, queryOf, valuesOf, type FormValues } from '@/librarian_form'
import { useLibrarianStore } from '@/stores/librarian_store'

/**
 * The Librarian (the operator's L1.a, 21 Nov, in place of the chat): what an MCP client gets from each of the librarian's
 * tools, bare, for a person and for debugging. Every tool a tab, in the server's staggered order; each with its own
 * description, a line on what it costs and takes, a form built from its input schema, Run, and the answer as the
 * librarian gave it, the raw JSON one click away. Every call goes over MCP to the running librarian, as an IDE session's
 * does, its client named "view" in the call log. The address names the tool and the arguments of its last run, so F5 and a
 * pasted link make the same call again.
 */
const route = useRoute()
const router = useRouter()
const store = useLibrarianStore()
const { info, infoError, calls, callErrors, running, runningSince } = storeToRefs(store)

void store.loadInfo()

const tools = computed(() => info.value?.tools ?? [])
const tool = computed(() => tools.value.find(one => one.name === route.query.tool) ?? tools.value[0] ?? null)
const values = computed<FormValues>({
  get: () => (tool.value ? store.forms[tool.value.name] ?? valuesOf(tool.value.fields) : {}),
  set: given => {
    if (tool.value) store.keepForm(tool.value.name, given)
  },
})

// an address that names a tool and every argument it requires is a call: its arguments in the form, the call made once.
// The page's own address names its first tab, `works`, which requires nothing: a client's first call, free and local
watch([tool, () => route.query], ([chosen, query]) => {
  if (!chosen || (query.tool ?? tools.value[0]?.name) !== chosen.name) return
  const args = argumentsFromQuery(chosen.fields, query)
  if (!args) return
  store.keepForm(chosen.name, valuesOf(chosen.fields, args))
  void store.run(chosen.name, args)
}, { immediate: true })

function choose(name: string): void {
  void router.push({ name: 'librarian', query: { tool: name } })
}

// Run makes the call again, on purpose; the address then names it
function run(): void {
  const chosen = tool.value
  if (!chosen) return
  const args = argumentsOf(chosen.fields, values.value)
  void store.run(chosen.name, args, true)
  void router.push({ name: 'librarian', query: queryOf(chosen.name, args) })
}
</script>

<template>
  <section class="librarian">
    <h1 class="view-title">Librarian</h1>
    <p class="lead" data-part="lead">
      What an MCP client gets from each of the librarian's tools, called over MCP<template v-if="info?.url"> at
        <code>{{ info.url }}</code></template> as an IDE session calls them; the calls stand in the
      <RouterLink :to="{ name: 'calls' }">Calls</RouterLink> as client “view”.
    </p>
    <ApiFailure v-if="infoError" :error="infoError" @retry="store.loadInfo()" />
    <LoadingLine v-else-if="!info" />
    <template v-else>
      <p v-if="info.why_not" class="why-not" role="alert" data-part="why-not">{{ info.why_not }}</p>
      <!-- the tools in the server's staggered order, a tab each, first in their row so they stay under the pointer -->
      <nav v-if="tools.length" class="tabs" aria-label="The librarian's tools" data-part="tabs">
        <AppButton v-for="one in tools" :key="one.name" size="compact" :active="tool?.name === one.name" :data-tab="one.name" @click="choose(one.name)">
          {{ one.label }}
        </AppButton>
      </nav>
      <div v-if="tool" class="tool" :data-tool="tool.name">
        <!-- the tool's code name, what a client calls, in the tab's head beside the view's name for it -->
        <p class="tool-name" data-part="tool-name">tool: <code>{{ tool.name }}</code></p>
        <!-- the tool's own description, as the server gives it to every client, and what it costs and takes in its words -->
        <FoldSection class="description" remember="librarian.description" title="What the server says" :count="tool.cost_said" data-part="description">
          <p class="description-text">{{ tool.description }}</p>
        </FoldSection>
        <SchemaForm v-model:values="values" :fields="tool.fields" :folded-title="tool.folded_title"
                    :running-since="running === tool.name ? runningSince : null" @submit="run" />
        <LoadingLine v-if="running === tool.name" />
        <ApiFailure v-else-if="callErrors[tool.name]" :error="callErrors[tool.name]!" @retry="run" />
        <LibrarianAnswer v-else-if="calls[tool.name]" :call="calls[tool.name]!" />
      </div>
    </template>
  </section>
</template>

<style scoped>
.librarian {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.lead,
.description-text,
.tool-name {
  color: var(--color-text-secondary);
  max-width: 100ch;
}

.why-not {
  color: var(--color-error);
}

.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
}

.tool {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.description-text {
  white-space: pre-line;
}
</style>
