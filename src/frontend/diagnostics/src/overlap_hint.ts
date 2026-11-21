import type { components } from '@/types/api/diagnostics_api'

type Splitter = components['schemas']['Splitter']

/**
 * What a chunk's dashed text means, in the splitter's own figures (the operator, 10 Nov: "rather show it as a hint"): one
 * sentence for an HTML section's chunks and a PDF page's chunks in its "as served" mode (W4, 21 Nov), so both say it alike.
 */
/**
 * What a chunk is, for a PDF page "as served" chunk first (the operator, 21 Nov): how the splitter cuts the page's quoted text,
 * and what a part and the dashed text mean, in the splitter's own figures.
 */
export function chunkHint(splitter: Splitter | null | undefined): string {
  if (!splitter) return ''
  return `The splitter (${splitter.splitter}, ${splitter.chunk_size.toLocaleString('en')} characters a chunk, ${splitter.chunk_overlap}`
    + ' shared) cuts the page\'s quoted text, its quoted blocks in order, into chunks, as semantic search embeds them. A block a'
    + ' border cuts stands in each chunk with its part, marked "(part)"; the text two chunks share stands in both, dashed. A block'
    + ' never quoted is in no chunk and not shown here. Formulas stand as the LaTeX the index holds.'
}

export function overlapHint(splitter: Splitter | null | undefined): string {
  if (!splitter) return ''
  return `dashed: text shared with the chunk before. The splitter (${splitter.splitter}, ${splitter.chunk_size.toLocaleString('en')}`
    + ` characters a chunk, ${splitter.chunk_overlap} shared) repeats up to ${splitter.chunk_overlap} characters across a border,`
    + ' so a sentence cut there stays findable in both chunks. Formulas stand here as the LaTeX the index holds.'
}
