<script setup lang="ts">
import { computed } from 'vue'
import AppButton from '@/components/base/AppButton.vue'
import FoldSection from '@/components/base/FoldSection.vue'
import SchemaField from '@/components/librarian/SchemaField.vue'
import type { FormValues } from '@/librarian_form'
import type { LibrarianField } from '@/types/api/librarian_types'

/**
 * A tool's form, built from its input schema as the API parts it (the operator's L1.a): a field per argument, in the
 * schema's order; the fields the API folds (a caller's own translation) in a fold beneath, under the API's title; then Run.
 * A new tool or argument appears by itself.
 */
const props = withDefaults(defineProps<{
  fields: LibrarianField[]
  values: FormValues
  foldedTitle?: string | null
  running?: boolean
}>(), { foldedTitle: null, running: false })

const emit = defineEmits<{ 'update:values': [values: FormValues], submit: [] }>()

const open = computed(() => props.fields.filter(field => !field.folded))
const folded = computed(() => props.fields.filter(field => field.folded))

function set(name: string, value: string | boolean): void {
  emit('update:values', { ...props.values, [name]: value })
}
</script>

<template>
  <form class="schema-form" data-part="schema-form" @submit.prevent="emit('submit')">
    <div v-if="open.length" class="fields" data-part="fields">
      <SchemaField v-for="field in open" :key="field.name" :field="field" :value="values[field.name] ?? ''" @update="set(field.name, $event)" />
    </div>
    <p v-else class="no-fields">This tool takes no arguments.</p>
    <FoldSection v-if="folded.length" class="folded" :title="foldedTitle ?? 'more'" data-part="folded-fields">
      <div class="fields">
        <SchemaField v-for="field in folded" :key="field.name" :field="field" :value="values[field.name] ?? ''" @update="set(field.name, $event)" />
      </div>
    </FoldSection>
    <AppButton type="submit" data-part="run" :disabled="running">Run</AppButton>
  </form>
</template>

<style scoped>
.schema-form {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-sm);
  max-width: 100%;
}

.fields {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.no-fields {
  color: var(--color-text-secondary);
}
</style>
