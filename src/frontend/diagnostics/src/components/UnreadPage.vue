<script setup lang="ts">
import LabelledLine from '@/components/base/LabelledLine.vue'
import LabelledLines from '@/components/base/LabelledLines.vue'
import PageLadderLines from '@/components/PageLadderLines.vue'
import StateMark from '@/components/StateMark.vue'
import type { PageDetail } from '@/types/api/page_types'

/**
 * A page no reader has read (the operator's V2.a, 20 Nov: "the work, then the page, then the image; the detail view says that
 * nothing was read, nothing extracted"): its state and what serves it, its own ladder, the text served, and its image, the
 * PDF's own as the librarian gives it. Nothing of a reading stands here, which it has not.
 */
defineProps<{
  page: PageDetail
  imageUrl: string
}>()
</script>

<template>
  <div class="unread-page" data-part="unread-page">
    <LabelledLines class="summary page-facts" data-part="page-facts" :label-chars="10">
      <LabelledLine label="Check"><StateMark :state="page.check.state" /></LabelledLine>
      <LabelledLine label="Route"><span class="route">{{ page.route_why }}</span></LabelledLine>
      <LabelledLine v-if="page.ladder" label="Coverage" data-part="page-coverage"><PageLadderLines :ladder="page.ladder" /></LabelledLine>
    </LabelledLines>
    <figure class="own-image" data-part="own-image">
      <img v-if="page.image.available" :src="imageUrl" :width="page.image.width ?? undefined" :height="page.image.height ?? undefined"
           :alt="`PDF page ${page.pdf_page}`">
      <figcaption>{{ page.image.available ? page.image.said : page.image.why_not }}</figcaption>
    </figure>
  </div>
</template>

<style scoped>
.route,
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
