<script setup lang="ts">
import { computed } from 'vue'
import type { LibrarianField } from '@/types/api/librarian_types'

/**
 * One argument of a tool's form, its control by its kind as the API parts the input schema (L1.a): a checkbox, a number
 * with its bounds, a choice of the schema's values, a list as comma-separated words, else a line of text. Named by the
 * argument's own name, as a client sends it, the server's default beside it.
 */
const props = defineProps<{
  field: LibrarianField
  value: string | boolean
}>()

const emit = defineEmits<{ update: [value: string | boolean] }>()

const text = computed(() => (typeof props.value === 'string' ? props.value : ''))
const numeric = computed(() => props.field.kind === 'integer' || props.field.kind === 'number')
// the server's own default beside the field, where it has one and the field is no checkbox
const serverDefault = computed(() => {
  const given = props.field.server_default
  if (given === null || given === undefined || props.field.kind === 'boolean') return null
  return Array.isArray(given) ? given.join(', ') : String(given)
})
</script>

<template>
  <label class="field" :data-field="field.name" :data-kind="field.kind">
    <span class="field-name">{{ field.name }}<span v-if="field.required" class="required" aria-hidden="true"> *</span></span>
    <input
      v-if="field.kind === 'boolean'"
      type="checkbox"
      class="control"
      :checked="value === true"
      @change="emit('update', ($event.target as HTMLInputElement).checked)"
    >
    <select v-else-if="field.kind === 'choice'" class="control" :value="text" @change="emit('update', ($event.target as HTMLSelectElement).value)">
      <option v-for="choice in field.choices" :key="choice" :value="choice">{{ choice }}</option>
    </select>
    <input
      v-else
      class="control"
      :type="numeric ? 'number' : 'text'"
      :value="text"
      :required="field.required"
      :min="field.minimum ?? undefined"
      :max="field.maximum ?? undefined"
      :step="field.kind === 'integer' ? 1 : numeric ? 'any' : undefined"
      :placeholder="field.kind === 'list' ? 'comma-separated' : undefined"
      @input="emit('update', ($event.target as HTMLInputElement).value)"
    >
    <span class="field-default" data-part="field-default">{{ serverDefault ? `default ${serverDefault}` : '' }}</span>
    <span v-if="field.description" class="field-description">{{ field.description }}</span>
  </label>
</template>

<style scoped>
/* a row: the argument's name in a column as wide as the longest a tool has ("concept_query"), its control, its default */
.field {
  display: grid;
  grid-template-columns: 15ch minmax(0, 40rem) max-content;
  align-items: center;
  gap: var(--space-xs) var(--space-sm);
}

.field-name {
  font-weight: bold;
  white-space: nowrap;
}

.required,
.field-default,
.field-description {
  color: var(--color-text-secondary);
}

.field-description {
  grid-column: 2 / -1;
}

.control:not([type='checkbox']) {
  width: 100%;
}

.control[type='checkbox'] {
  justify-self: start;
}

/* a narrow screen: the name above its control, its default beneath */
@media (max-width: 40rem) {
  .field {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
