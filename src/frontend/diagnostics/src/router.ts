import { createRouter, createWebHashHistory } from 'vue-router'
import CallsView from '@/views/CallsView.vue'
import ErrorClassesView from '@/views/ErrorClassesView.vue'
import HtmlWorkView from '@/views/HtmlWorkView.vue'
import IssuesView from '@/views/IssuesView.vue'
import OverviewView from '@/views/OverviewView.vue'
import PagesView from '@/views/PagesView.vue'
import PromptsView from '@/views/PromptsView.vue'
import PageView from '@/views/PageView.vue'
import RunsView from '@/views/RunsView.vue'
import RunView from '@/views/RunView.vue'
import SearchView from '@/views/SearchView.vue'
import ShelfView from '@/views/ShelfView.vue'
import SourcesView from '@/views/SourcesView.vue'
import WorkPagesView from '@/views/WorkPagesView.vue'
import type { KnowledgeBase } from '@/types/api/source_types'

declare module 'vue-router' {
  interface RouteMeta {
    /** The view's name in the menu, the header and the browser tab, until the view names itself (a work's title). */
    label?: string
    /** A view of two panes side by side, which takes the wider content container (decision 160). */
    wide?: boolean
  }
}

// A work is addressed within its knowledge base, as the API addresses it: an id alone is not a key (decision 80.a). The
// match is case-sensitive like the API's, so '#/FREE/...' finds no view instead of a refusal (review, 2026-11-04).
const WORK = '/:kb(free|licensed)/sources/:work'

/**
 * The URL holds only what a ticket links to, the thing on show; everything else is stored settings.
 * Hash history, so the API server serves one index.html and needs no route of its own for the UI's paths.
 */
export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/overview' },
    { path: '/overview', name: 'overview', component: OverviewView, meta: { label: 'Overview' } },
    // the pages behind a figure of the overview, its filters in the address (`?knowledge_base=free&state=issue`)
    { path: '/pages', name: 'pages', component: PagesView, meta: { label: 'Pages' } },
    { path: '/sources', name: 'sources', component: SourcesView, meta: { label: 'Sources' } },
    // every work of both knowledge bases, how far it is converted and why pages did not pass (129.a, 22.a)
    { path: '/shelf', name: 'shelf', component: ShelfView, meta: { label: 'Shelf' } },
    {
      path: WORK,
      name: 'work',
      component: WorkPagesView,
      sensitive: true,
      meta: { label: 'Work' },
      props: route => ({ kb: route.params.kb as KnowledgeBase, work: String(route.params.work) }),
    },
    {
      path: `${WORK}/page/:page(\\d+)`,
      name: 'page',
      component: PageView,
      sensitive: true,
      // the image the reader received beside its reading: two panes side by side
      meta: { label: 'Page', wide: true },
      props: route => ({ kb: route.params.kb as KnowledgeBase, work: String(route.params.work), page: Number(route.params.page) }),
    },
    // an HTML work by its headings, and one section's chunks (the operator's 6.a); only the free knowledge base has HTML works
    {
      path: '/:kb(free)/html/:work',
      name: 'html-work',
      component: HtmlWorkView,
      sensitive: true,
      meta: { label: 'HTML work' },
      props: route => ({ kb: route.params.kb as KnowledgeBase, work: String(route.params.work) }),
    },
    // a section `s14`, or a heading dropped as noise `d3`, shown in its article whole (the operator, 10 Nov); loaded when opened,
    // since its sanitiser is needed nowhere else
    {
      path: '/:kb(free)/html/:work/:section([sd]\\d+)',
      name: 'html-section',
      component: () => import('@/views/HtmlArticleView.vue'),
      sensitive: true,
      // each section's original beside its chunks: two panes side by side
      meta: { label: 'Article', wide: true },
      props: route => ({ kb: route.params.kb as KnowledgeBase, work: String(route.params.work), section: String(route.params.section) }),
    },
    // a licensed EPUB work by its headings, and one section with its images (123.a, the operator's P1.a); only the licensed
    // knowledge base has EPUB works, and an app started with --public-only answers them 404
    {
      path: '/:kb(licensed)/epub/:work',
      name: 'epub-work',
      component: () => import('@/views/EpubWorkView.vue'),
      sensitive: true,
      meta: { label: 'EPUB work' },
      props: route => ({ kb: route.params.kb as KnowledgeBase, work: String(route.params.work) }),
    },
    {
      path: '/:kb(licensed)/epub/:work/:section(s\\d+)',
      name: 'epub-section',
      component: () => import('@/views/EpubSectionView.vue'),
      sensitive: true,
      meta: { label: 'Section' },
      props: route => ({ kb: route.params.kb as KnowledgeBase, work: String(route.params.work), section: String(route.params.section) }),
    },
    { path: '/issues', name: 'issues', component: IssuesView, meta: { label: 'Issues' } },
    // the findings grouped by kind, block class and work: what kind of error recurs, and where
    { path: '/errors', name: 'errors', component: ErrorClassesView, meta: { label: 'Errors' } },
    // the chat, compact (decision 100.a): the one view whose requests spend money. Loaded when opened, since its
    // Markdown and sanitising libraries are needed nowhere else
    // its label says which search answers there, as the search's says its own (the operator, 16 Nov: a question typed into the
    // keyword search was expected to find what the chat's hybrid search finds)
    { path: '/chat', name: 'chat', component: () => import('@/views/ChatView.vue'), meta: { label: 'Chat · semantic (hybrid)' } },
    // the search server's call log: who asked what, which pages answered, how long it took (19.a)
    { path: '/calls', name: 'calls', component: CallsView, meta: { label: 'Calls' } },
    // every run of the pipeline, and one run whole: the place of a replay's trace in the review demo (21.a)
    { path: '/runs', name: 'runs', component: RunsView, meta: { label: 'Runs' } },
    // every version of the reader's and the judge's instructions; `?version=judge/2` marks one (148.a)
    { path: '/prompts', name: 'prompts', component: PromptsView, meta: { label: 'Prompts' } },
    {
      path: '/:kb(free|licensed)/runs/:run(\\d+)',
      name: 'run',
      component: RunView,
      sensitive: true,
      meta: { label: 'Run' },
      props: route => ({ kb: route.params.kb as KnowledgeBase, run: Number(route.params.run) }),
    },
    // the question in the address (`?q=…&corpus=…`), so a search can be linked like a page
    // no model at all, neither embeddings nor a language model (the operator, 16 Nov: "search without LLMs"); the naming rule from
    // then: `search` is called search (BM25), `semantic_search` semantic (hybrid)
    { path: '/search', name: 'search', component: SearchView, meta: { label: 'Search · BM25, no model' } },
    // Addresses handed out before the knowledge base was part of them, when only free works were served.
    { path: '/sources/:work', redirect: to => ({ name: 'work', params: { kb: 'free', work: to.params.work } }) },
    {
      path: '/sources/:work/page/:page(\\d+)',
      redirect: to => ({ name: 'page', params: { kb: 'free', work: to.params.work, page: to.params.page } }),
    },
    { path: '/bin', redirect: '/issues' },
  ],
})
