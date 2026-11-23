<script setup lang="ts">
import { computed, ref } from 'vue'

/**
 * Text with its lines numbered, one look wherever numbered text stands (decision 221.a): a page's raw reading (228.a, the
 * operator on accounting p. 338: "line 86? then please line numbers in the read-only editor too") and a code file (#12, as its
 * citation counts its lines). The numbers stand in a gutter beside the text, never in it, so the text copied is the text as
 * stored; a long line wraps under its own text. The lines asked for (a click on an error, a citation's range) are marked with
 * the accent's bar; a line may carry a mark of its own besides, a validator's error as a compiler marks one (A.a):
 * `error-block` the block it names, `error-named` the fault's own line, `error-looked` one a person has looked at.
 */
const props = defineProps<{
  text: string
  marked?: { first: number, last: number } | null
  marks?: ReadonlyMap<number, string>
}>()

const root = ref<HTMLElement | null>(null)
const lines = computed(() => props.text.split('\n'))

function isMarked(line: number): boolean {
  return !!props.marked && line >= props.marked.first && line <= props.marked.last
}

/** Brings a line into view, centred: the jump a reader asked for. */
function scrollToLine(line: number): void {
  root.value?.querySelector(`[data-line="${line}"]`)?.scrollIntoView?.({ block: 'center', behavior: 'auto' })
}

defineExpose({ scrollToLine })
</script>

<template>
  <pre ref="root" class="numbered-text" :style="{ '--gutter': `${String(lines.length).length}ch` }"><span v-for="(line, at) in lines" :key="at" class="numbered-line" :class="[{ marked: isMarked(at + 1) }, marks?.get(at + 1)]" :data-line="at + 1" :data-mark="marks?.get(at + 1)">{{ at < lines.length - 1 ? `${line}\n` : line }}</span></pre>
</template>

<style scoped>
.numbered-text {
  white-space: pre-wrap;
  word-break: break-word;
}

/* each line with its number in a gutter the selection leaves out; a long line wraps under its own text */
.numbered-line {
  display: block;
  padding-left: calc(var(--gutter) + var(--space-sm));
  text-indent: calc(-1 * (var(--gutter) + var(--space-sm)));
}

.numbered-line::before {
  content: attr(data-line);
  display: inline-block;
  width: var(--gutter);
  margin-right: var(--space-sm);
  text-align: right;
  text-indent: 0;
  color: var(--color-text-secondary);
  user-select: none;
}

/* the lines asked for, marked as the block on show is */
.numbered-line.marked {
  background-color: var(--color-bg-elevated);
  box-shadow: inset 2px 0 0 var(--color-accent);
}

/* a validator's error, as a compiler marks one: the block it names tinted, a bar in the error's role at the gutter, the named
   line stronger and its number in the role too, so the mark survives greyscale by its bar and weight */
.numbered-line.error-block,
.numbered-line.error-named {
  background-color: color-mix(in srgb, var(--color-error) 8%, transparent);
  box-shadow: inset 3px 0 0 var(--color-error);
}

.numbered-line.error-named {
  background-color: color-mix(in srgb, var(--color-error) 18%, transparent);
}

.numbered-line.error-named::before {
  color: var(--color-error);
  font-weight: bold;
}

/* an error a person has looked at recedes: its block keeps a quiet bar, never the error's colour */
.numbered-line.error-looked {
  color: var(--color-text-secondary);
  box-shadow: inset 3px 0 0 var(--color-text-secondary);
}

/* the line a click asked for stays marked over an error's tint, so the jump is seen */
.numbered-line.marked.error-block,
.numbered-line.marked.error-named {
  outline: 1px solid var(--color-accent);
  outline-offset: -1px;
}
</style>
