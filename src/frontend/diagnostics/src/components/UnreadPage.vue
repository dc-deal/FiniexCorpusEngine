<script setup lang="ts">
import type { PageDetail } from '@/types/api/page_types'

/**
 * A page no reader has read (the operator's V2.a, 20 Nov: "the work, then the page, then the image; the detail view says that
 * nothing was read, nothing extracted"): its image, the PDF's own as the librarian gives it, beneath the record's rows, which
 * say its state, what serves it and its own ladder as on every page (H1.a). Nothing of a reading stands here, which it has not.
 */
defineProps<{
  page: PageDetail
  imageUrl: string
}>()
</script>

<template>
  <figure class="own-image" data-part="own-image">
    <img v-if="page.image.available" :src="imageUrl" :width="page.image.width ?? undefined" :height="page.image.height ?? undefined"
         :alt="`PDF page ${page.pdf_page}`">
    <figcaption>{{ page.image.available ? page.image.said : page.image.why_not }}</figcaption>
  </figure>
</template>

<style scoped>
figcaption {
  color: var(--color-text-secondary);
}

/* the page as the PDF holds it, as wide as the record allows, its proportions kept */
.own-image {
  margin: var(--space-md) 0 0;
}

.own-image img {
  display: block;
  max-width: 100%;
  height: auto;
  border: 1px solid var(--color-border);
}
</style>
