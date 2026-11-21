import type { components } from '@/types/api/diagnostics_api'

type Splitter = components['schemas']['Splitter']

/**
 * What a chunk's dashed text means, in the splitter's own figures (the operator, 10 Nov: "rather show it as a hint"): one
 * sentence for an HTML section's chunks and a PDF page's chunks in its "as served" mode (W4, 21 Nov), so both say it alike.
 */
export function overlapHint(splitter: Splitter | null | undefined): string {
  if (!splitter) return ''
  return `dashed: text shared with the chunk before. The splitter (${splitter.splitter}, ${splitter.chunk_size.toLocaleString('en')}`
    + ` characters a chunk, ${splitter.chunk_overlap} shared) repeats up to ${splitter.chunk_overlap} characters across a border,`
    + ' so a sentence cut there stays findable in both chunks. Formulas stand here as the LaTeX the index holds.'
}
