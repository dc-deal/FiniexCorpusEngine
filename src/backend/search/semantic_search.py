"""The chat's retrieval chain as one service of the MCP server: route the question, then search by meaning and by keywords (98.c).

There is one retrieval. The MCP server offers it as the tool `semantic_search`, the chat calls it through the server like any
other client, and an IDE session gets the very pages the chat gets, so the chat is the server's control tool. What runs here is
the RAG sprint's measured chain, moved unchanged:

1. the router (`query_routing.plan_query`) decides the behaviour (search, clarify, decline) and translates the question: a
   rewritten search query, a step-back concept query and keywords (query translation, rag_from_scratch parts 5 to 8);
2. the hybrid search (`query_routing.search`): vectors over the chunks for both queries, BM25 over the router's keywords, fused by
   RRF (k = 60), as configured in `configs/app_config.json` under `retrieval`.

Each hit has the shape of a `search` hit (knowledge base, work, page, section, where, snippet, licence, route, reading key) and
carries what an answer needs on top: the chunk's full text, its similarity and its citation fields. The answer and the
word-for-word check of its quotes stay with the client: that is answering, not retrieval.

    service = SemanticSearch(work_keys)                 # the router, the vector store and BM25 are built on first use
    service.search('how is the amortization of a bond discount computed?', hits=10)
"""

import math

from backend.ingestion.chunking import count_tokens
from backend.search import page_index, query_routing

EMBEDDING_MODEL = 'text-embedding-3-small'  # the index's model (embedding_route.INDEX_MODEL names it with its maker)
EMBEDDING_USD_PER_TOKEN = 0.02 / 1_000_000  # its list price, the same through OpenAI and OpenRouter (read 2026-10-29)

STATES = ('found', 'nothing found', 'declined', 'error')


def page_of(citation: dict, chunk_id: str | None = None) -> dict:
    """A chunk's page as `search` and `open_page` name it (57.a): a PDF page where there is one, else the HTML section's
    label, `s` and its position from 1 (`free_html_pages`). Both read a source's sections with the same loader, so the
    section ordinal in a chunk id (`source:0008:000`) is the server's: section 0008 is page s9.

    Found live on 2026-11-05: the label was the section's anchor ('Definition'), and the chat's "open source 1" asked
    `open_page` for a page no tool names."""
    if citation.get('page_label'):  # a page named by its source, as a code file is (#12)
        return {'label': str(citation['page_label']), 'pdf': None, 'printed': None}
    if citation.get('pdf_page') is not None:
        printed = citation.get('printed_page')
        return {'label': str(citation['pdf_page']), 'pdf': str(citation['pdf_page']),
                'printed': None if printed is None else str(printed)}
    parts = (chunk_id or '').split(':')
    label = f's{int(parts[-2]) + 1}' if len(parts) >= 3 and parts[-2].isdigit() else None
    return {'label': label, 'pdf': None, 'printed': None}


def hit_of(result: dict, question: str, sources: dict) -> dict:
    """One chunk as a hit: the `search` fields, then the full text, similarity and citation an answer needs."""
    citation = result['citation']
    source = sources.get(citation.get('source_id'), {})
    page = page_of(citation, result['chunk_id'])
    where = citation.get('url') or (f"{source['path']}#page={page['pdf']}" if source.get('path') and page['pdf'] else source.get('path'))
    return {'score': result.get('similarity'), 'knowledge_base': citation.get('knowledge_base', 'free'),
            'work': source.get('work', citation.get('source_id')), 'title': citation.get('source_title'), 'page': page,
            'section': citation.get('section') or citation.get('chapter'), 'where': where,
            'snippet': page_index.snippet(result['text'], question), 'licence': citation.get('licence'),
            'route': citation.get('route'), 'reading_key': citation.get('reading_key'),
            'chunk_id': result['chunk_id'], 'similarity': result.get('similarity'), 'text': result['text'], 'citation': citation}


class SemanticSearch:
    """The chain, built once per process on its first question, so a server starts fast and keyword search needs no key."""

    def __init__(self, sources: dict, config: dict | None = None, router_chain=None, store=None, keyword_index=None,
                 frozen_plans: dict | None = None, private: bool = False, private_store=None, private_keywords=None,
                 kept: frozenset[str] = frozenset()):
        self.sources = sources  # source id -> {'work': the key `search` uses, 'path': the raw file}
        # The private base's index too (#8): only where the server gives the private base out and its index was built, so a
        # --public-only start and every measurement search the free index alone, as before
        self.private, self._private_store, self._private_keywords = private, private_store, private_keywords
        # A kept edition's chunks (E1.a, 20 Nov): they stay in the private index, so a switch embeds nothing, and are dropped
        # from its results here; the private chain asks for twice the hits then, so the dropped ones leave no gap
        self.kept = kept
        # Evaluation only: the router's plans of an earlier run, by question, so a comparison run differs from it only by the
        # change it measures; a question without one is routed live (phase 6, the neighbouring project's "freeze inputs").
        self.frozen_plans = frozen_plans or {}
        self._config, self._router, self._store, self._keywords = config, router_chain, store, keyword_index

    def _ready(self) -> None:
        from backend.chat import app_config
        from backend.search import retrieval

        if self._config is None:
            self._config = app_config.load()
        if self._router is None and self._config['router'].get('enabled', True):  # off: no model and no key (279.a)
            from backend.providers import chat_models

            self._router = query_routing.router(chat_models.chat_model(self._config['router']))
        if self._store is None:
            self._store = retrieval.default_store()
        if self._keywords is None:
            self._keywords = retrieval.default_keyword_index()
        if self.private and self._private_store is None:
            self._private_store = retrieval.licensed_store()
        if self.private and self._private_keywords is None:
            self._private_keywords = retrieval.licensed_keyword_index()

    def search(self, question: str, hits: int = 10, search_query: str | None = None, concept_query: str | None = None,
               keywords: list[str] | None = None, route: bool = True, only: dict | None = None, corpus: str = 'all',
               per_page: bool = False) -> dict:
        """Route the question and search for it; a decline searches nothing and says so. `only`: a metadata filter on both
        indexes' chunks (#12: a code work's chunks by their route). `corpus`: 'free' or 'licensed' searches that base alone,
        'all' both, merged by similarity (#14). `per_page`: one hit per page, the page's best passage, with the count of its
        other passages among the candidates (`more_on_page`, #15); PER_PAGE_WIDENING times the candidates are fetched so
        about `hits` pages come back. The chat keeps every passage: its phase 6 numbers were measured on them.

        The caller may translate the question itself (decision 279.a): a calling session is a model already. With any of
        `search_query`, `concept_query` or `keywords` the router is not asked and nothing is declined. Without them the router
        translates while the configuration has it on (`router.enabled`); with it off, the question searches as it stands.
        `route=False` keeps the router out of this one call whatever the configuration says (the view's bare semantic search,
        the operator's S1.a, 21 Nov): the question then searches as it stands, as a client without a translation of its own."""
        self._ready()
        limit = self._config['answer']['max_question_characters']
        if not question or not question.strip() or len(question) > limit:
            return {'state': 'error', 'error': f'a question of 1 to {limit} characters', 'question': question, 'hits': []}
        frozen = self.frozen_plans.get(question)
        nothing_spent = {'input_tokens': 0, 'output_tokens': 0, 'reasoning_tokens': 0}
        if frozen:
            routed = {'plan': query_routing.QueryPlan(**{k: v for k, v in frozen.items() if k != 'fell_back'}),
                      'fell_back': bool(frozen.get('fell_back')), **nothing_spent, 'translated_by': 'a frozen plan'}
        elif search_query or concept_query or keywords:
            plan = query_routing.fallback_plan((search_query or question).strip())
            routed = {'plan': plan.model_copy(update={'concept_query': concept_query or None, 'keywords': list(keywords or [])}),
                      'fell_back': False, **nothing_spent, 'translated_by': 'the caller'}
        elif self._router is None or not route:
            routed = {'plan': query_routing.fallback_plan(question), 'fell_back': False, **nothing_spent,
                      'translated_by': 'nobody: the router is off' if self._router is None else 'nobody: the caller asked for none'}
        else:
            routed = {**query_routing.plan_query(self._router, question), 'translated_by': 'the router'}
        plan = routed['plan']
        behaviour = query_routing.behaviour(plan)
        # What the router used, so a client can price the call (the chat does): its model and tokens; the query embeddings
        # follow once the bases searched are known (#14: a client totals what a session spent)
        usage = {'router': {'model': self._config['router']['model'] if routed['translated_by'] == 'the router' else None,
                            **{key: routed.get(key, 0) for key in ('input_tokens', 'output_tokens', 'reasoning_tokens')}},
                 'embedding': {'model': EMBEDDING_MODEL, 'tokens': 0, 'usd': 0.0}}
        answer = {'question': question, 'behaviour': behaviour,
                  'plan': {**plan.model_dump(), 'fell_back': routed['fell_back'], 'translated_by': routed['translated_by']},
                  'relevance': None, 'below_floor': None, 'search': {}, 'hits': [], 'usage': usage}
        if behaviour in ('decline_off_topic', 'decline_harmful'):
            return {**answer, 'state': 'declined'}
        settings = self._config['retrieval']
        trace: dict = {}
        fetch = max(1, math.ceil(hits * PER_PAGE_WIDENING) if per_page else hits)
        chain = dict(k=fetch, use_shelf_filter=settings['shelf_filter'], use_concept_query=settings['concept_query'],
                     use_keyword_search=settings['keyword_search'], bm25_on_keywords=settings['bm25_on_keywords'],
                     with_signal=True, demote_sections=frozenset(settings.get('demote_sections') or ()), only=only)
        lists, relevances, chains = [], [], 0
        if corpus in ('all', 'free'):
            results, relevance = query_routing.search(plan, store=self._store, keyword_index=self._keywords, trace=trace, **chain)
            lists.append(results)
            relevances.append(relevance)
            chains += 1
        if self.private and corpus in ('all', 'licensed'):
            # The same chain over the private index. Both indexes embed with the same model, so their similarities compare,
            # and the lists are merged by each passage's own similarity (#14, 23 Nov: merged by rank, a weak free hit stood
            # above a strong licensed one in every call a client made). The free chain's trace stays as it was.
            private_trace: dict = {}
            private_chain = {**chain, 'k': fetch * 2} if self.kept else chain
            private, private_relevance = query_routing.search(plan, store=self._private_store,
                                                              keyword_index=self._private_keywords, trace=private_trace,
                                                              **private_chain)
            if self.kept:
                private = [result for result in private if result['citation'].get('source_id') not in self.kept][:fetch]
            lists.append(private)
            relevances.append(private_relevance)
            chains += 1
            trace['licensed'] = private_trace
        # One base's list is ordered by similarity too (#15: a client found `corpus: "licensed"` still in the fused order,
        # a keyword-only passage at rank 6 above one of 0.639 at rank 8)
        merged = merge_by_similarity(lists)
        more = {}
        if per_page:
            merged, more = by_page(merged)
        results = merged[:max(1, hits)]
        relevance = max((value for value in relevances if value is not None), default=None)
        embedded = [plan.search_query, *([plan.concept_query] if settings['concept_query'] and plan.concept_query else [])]
        tokens = chains * sum(count_tokens(text) for text in embedded if text)
        usage['embedding'] = {'model': EMBEDDING_MODEL, 'tokens': tokens, 'usd': round(tokens * EMBEDDING_USD_PER_TOKEN, 8)}
        floor = settings['relevance_floor']
        return {**answer, 'corpus': corpus, 'state': 'found' if results else 'nothing found', 'relevance': relevance,
                'below_floor': relevance is None or relevance < floor, 'relevance_floor': floor, 'search': trace,
                'per_page': per_page,  # said either way (the client's third check: false left the key out)
                'hits': [{**hit_of(result, question, self.sources),
                          **({'more_on_page': more.get(result['chunk_id'], 0)} if per_page else {})} for result in results]}


PER_PAGE_WIDENING = 1.5  # candidates per hit when folding by page: measured on 23 Nov (below)


def by_page(results: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """The results with a page's later passages folded into its first (its best, as the list is ordered), and per kept
    passage how many of its page's passages were folded in (#15: a client got one page three times in ten hits).

    Measured on the 61 evaluation questions, the free base, the router kept out, the top 10: by passage as served (10
    candidates), the expected source in 41 of 45, MRR 0.756, 8.6 distinct pages; by page from 15 candidates, 41 of 45,
    MRR 0.754, 9.9 pages and more works; from 20 candidates, 40 of 45 (more candidates crowd the expected passage out)."""
    kept, more, first = [], {}, {}
    for result in results:
        citation = result.get('citation') or {}
        key = (citation.get('source_id'), page_of(citation, result['chunk_id'])['label'])
        if key in first:
            more[first[key]] += 1
            continue
        first[key] = result['chunk_id']
        more[result['chunk_id']] = 0
        kept.append(result)
    return kept, more


def merge_by_similarity(lists: list[list[dict]]) -> list[dict]:
    """Several bases' result lists as one, each passage at its own vector similarity (#14); a passage only the keyword search
    found, which has none, follows the rest in its own list's order. A passage two lists hold stands once.

    Measured on the 61 evaluation questions (23 Nov 2026, the router kept out, the top 10 of each merge): merged by rank,
    203 pairs of the two bases stood the wrong way round by more than 0.05 similarity, in 45 questions; by each passage's
    own similarity none, an expected source in the top 10 for 38 of 45 questions against 39, and the top three's mean
    similarity 0.554 against 0.466. Keeping each list's own order and merging at a running minimum of its similarities was
    tried first and measured worse (23 of 45): a list fused with keyword hits is not ordered by similarity, so its minimum
    falls at once and pulls the whole list down."""
    keyed = []
    for position, results in enumerate(lists):
        for rank, result in enumerate(results):
            similarity = result.get('similarity')
            keyed.append(((0, -similarity, 0, 0) if similarity is not None else (1, 0.0, rank, position), result))
    keyed.sort(key=lambda item: item[0])
    seen, merged = set(), []
    for _, result in keyed:
        if result['chunk_id'] not in seen:
            seen.add(result['chunk_id'])
            merged.append(result)
    return merged
