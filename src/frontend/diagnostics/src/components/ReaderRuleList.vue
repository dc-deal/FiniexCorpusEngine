<script setup lang="ts">
import type { ReaderRule } from '@/types/api/page_types'

/**
 * The rules a judge proposed for the reader (decision 202.a, judge/4's), read-only and never applied: each its kind, the
 * block that asked for it, the rule in the judge's words, and the class, attribute and value of the vocabulary it names,
 * where it names one. A proposal is where a reader prompt's next version would start, as a measured prototype; nothing
 * here changes a reading.
 */
defineProps<{
  rules: ReaderRule[]
}>()

// the vocabulary a rule names, in one run: "class figure · attribute marker = a"
function vocabularyOf(rule: ReaderRule): string {
  const attribute = rule.attribute ? `attribute ${rule.attribute}${rule.value ? ` = ${rule.value}` : ''}` : ''
  return [rule.block_class ? `class ${rule.block_class}` : '', attribute].filter(Boolean).join(' · ')
}
</script>

<template>
  <div class="reader-rules" data-part="reader-rules">
    <p class="part-label">Proposals for the reader, never applied:</p>
    <ul class="rules ruled">
      <li v-for="(rule, at) in rules" :key="at" class="rule" :data-rule="at">
        <span class="rule-kind">{{ rule.kind.replace(/_/g, ' ') }}</span>
        <span v-if="rule.block" class="rule-block">{{ rule.block }}</span>
        <span v-if="vocabularyOf(rule)" class="rule-vocabulary" data-part="rule-vocabulary">{{ vocabularyOf(rule) }}</span>
        <span v-if="rule.rule" class="rule-text">{{ rule.rule }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.reader-rules {
  padding: var(--space-xs) 0 var(--space-xs) calc(1em + var(--space-sm));
}

/* whose words follow: a bold name, as a finding's voices have it (178.a) */
.part-label {
  color: var(--color-text-secondary);
  font-weight: bold;
}

.rules {
  list-style: none;
  max-width: 100ch;
}

.rule {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0 var(--space-sm);
  padding: 1px 0;
}

.rule-kind,
.rule-block,
.rule-vocabulary {
  color: var(--color-text-secondary);
  white-space: nowrap;
}
</style>
