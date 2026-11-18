"""Query translation and routing (phase 4): one structured model call reads the question.

Questions arrive casual, with typos and everyday words ("test my bot"), while the sources use
terms of art (backtesting, walk-forward). Some should not be searched at all. One call to a chat
model, with `with_structured_output` into `QueryPlan`, combines four course techniques
(docs/phase_04_query_translation_and_routing.md):

- **logical routing** (rag_from_scratch 10, `RouteQuery`): search, or decline as off-topic or
  harmful, before anything is retrieved or paid for;
- **query structuring** (rag_from_scratch 11): the shelf, which becomes a metadata filter;
- **query rewriting**: a standalone search query in the sources' words;
- **step-back** (rag_from_scratch 5-9, "Step Back"; Zheng et al. 2023): a second, more general
  query for the concept the question rests on, searched next to the rewrite and fused by RRF. The
  course asks for it in a call of its own, with few-shot examples; here it is one more field of the
  same call, so it adds no call and no latency (decided 2026-09-30, the operator's two-tier idea);
- the two flags that pick the next step: `is_broad` triggers **multi-query** (rag_from_scratch 5,
  a second call), `needs_clarification` a follow-up question instead of an answer.

One call rather than one per technique, because all of them read the same question, and every
extra call adds latency and cost. Each field is still one named technique, measured on its own.

No question from the evaluation datasets appears in a prompt here, not even as an example; a
contract test checks it. Otherwise the router would be tuned to the exam.
"""

import time
from typing import Literal

import openai
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from backend.providers import chat_models
from backend.search import retrieval


class QueryPlan(BaseModel):
    """How to handle one user question: whether to search, where, and with which query."""

    route: Literal['search', 'off_topic', 'harmful'] = Field(
        description=(
            "'search' for anything about trading, finance, accounting, or building and running "
            "software. 'off_topic' for anything else. 'harmful' when the user asks for help with "
            "something illegal, or with deceiving, defrauding or attacking others. Judge what is "
            "actually asked for, not single words."))
    needs_clarification: bool = Field(
        description=(
            'True only if no useful answer is possible without something only the user can tell: '
            'their market, their strategy, their situation. If a general answer from the sources '
            'would already help, false: that answer can still end with a follow-up question. A '
            'broad question is not an unclear one.'))
    shelf: Literal['trading_finance', 'architecture', 'both'] = Field(
        description="The shelf that holds the answer; 'both' when the question needs both, or when unsure.")
    search_query: str = Field(
        description=(
            'The question as a short, standalone English search query, in the words textbooks and '
            'papers use: fix typos, spell out abbreviations, name the concept. Never an answer. For '
            "'off_topic' and 'harmful', the question unchanged."))
    concept_query: str | None = Field(
        description=(
            'A step back from the question: a short, standalone English search query for the '
            'underlying concept, worded the way a textbook would define or explain it. For a '
            'how-to or a practical question, the concept it rests on. null when the question '
            "itself already asks what a concept is, and for 'off_topic' and 'harmful'."))
    keywords: list[str] = Field(
        description=(
            'Two to five terms of art for a keyword search: the names of the concepts, methods or '
            'instruments the answer is about, spelled as the sources would spell them. No generic '
            "words (definition, how, trading, strategy). Empty for 'off_topic' and 'harmful'."))
    is_broad: bool = Field(
        description=(
            'True only when the question asks for several distinct things, or for a list. A single '
            'concept, however deep, is not broad.'))


class SearchQueries(BaseModel):
    """Alternative search queries for one question."""

    queries: list[str] = Field(description='The alternative versions of the question, one per entry.')


ROUTER_SYSTEM = """You prepare one question for a search over a small knowledge base. You never \
answer the question.

The person asking is a software developer who builds and runs trading bots. Read the question in \
that context, unless it is clearly about something else.

The knowledge base has two shelves:
- trading_finance: two textbooks (OpenStax Principles of Finance, Principles of Accounting), \
Wikipedia articles on trading topics, a classic trader's memoir (Lefèvre), and two research papers, \
one on position sizing with the Kelly criterion and one on validating trading strategies with \
walk-forward testing.
- architecture: Google's Site Reliability Engineering book (running production software \
reliably), and an article on accounting for software developers (Kleppmann)."""

ROUTER_PROMPT = ChatPromptTemplate.from_messages([('system', ROUTER_SYSTEM), ('human', '{question}')])

# The course's multi-query prompt (rag_from_scratch 5), unchanged but for the number of versions,
# which comes from the configuration. The course splits the answer at newlines; structured output
# returns a list instead, so numbering and blank lines cannot turn into search queries.
MULTI_QUERY_TEMPLATE = """You are an AI language model assistant. Your task is to generate {versions}
different versions of the given user question to retrieve relevant documents from a vector
database. By generating multiple perspectives on the user question, your goal is to help
the user overcome some of the limitations of the distance-based similarity search.
Original question: {question}"""

MULTI_QUERY_PROMPT = ChatPromptTemplate.from_template(MULTI_QUERY_TEMPLATE)

# What each route means for the answer (the coarse behaviour classes of the dataset).
BEHAVIOUR = {'off_topic': 'decline_off_topic', 'harmful': 'decline_harmful'}


def router(llm) -> Runnable:
    """The routing chain: prompt → model → QueryPlan, with the raw message kept for its token counts."""
    return ROUTER_PROMPT | chat_models.structured(llm, QueryPlan)


def expander(llm) -> Runnable:
    """The multi-query chain: prompt → model → SearchQueries."""
    return MULTI_QUERY_PROMPT | chat_models.structured(llm, SearchQueries)


def fallback_plan(question: str) -> QueryPlan:
    """What happens when the router gives no usable plan: the plain phase 3 search over everything."""
    return QueryPlan(route='search', needs_clarification=False, shelf='both', search_query=question,
                     concept_query=None, keywords=[], is_broad=False)


def _call(chain: Runnable, inputs: dict) -> dict:
    """Invoke a structured chain; return the parsed object (or None), token counts, time and error."""
    began = time.perf_counter()
    try:
        output = chain.invoke(inputs)
    except (openai.LengthFinishReasonError, openai.ContentFilterFinishReasonError) as stopped:
        return _stopped_call(stopped, time.perf_counter() - began)
    seconds = time.perf_counter() - began
    raw = output.get('raw')
    usage = getattr(raw, 'usage_metadata', None) or {}
    error = None
    if output.get('parsed') is None:
        # A reasoning model that spent its budget returns content null with finish_reason
        # 'length' and no error; say which it was instead of a bare "no plan".
        metadata = getattr(raw, 'response_metadata', None) or {}
        finish = metadata.get('finish_reason') or metadata.get('stop_reason')  # OpenAI's word, Anthropic's word
        error = f"no parsable output (finish_reason={finish}): {output.get('parsing_error')}"
    return {
        'parsed': output.get('parsed'),
        'seconds': round(seconds, 3),
        'input_tokens': usage.get('input_tokens', 0),
        'output_tokens': usage.get('output_tokens', 0),
        'reasoning_tokens': (usage.get('output_token_details') or {}).get('reasoning', 0),
        'error': error,
    }


def _stopped_call(stopped: openai.OpenAIError, seconds: float) -> dict:
    """A call the model ended without parsable output, as `_call` reports any other failure.

    Structured output runs through OpenAI's `parse()` helper, which *raises* when the output budget
    runs out (finish_reason 'length') instead of returning content null. Found 2026-10-01: the
    generator wrote 6,000 tokens of text for a follow-up question, and the exception reached the
    interface. The start of the text is kept in the error, for diagnosis.
    """
    completion = getattr(stopped, 'completion', None)
    usage = getattr(completion, 'usage', None)
    details = getattr(usage, 'completion_tokens_details', None)
    content = ''
    if completion is not None and completion.choices:
        content = completion.choices[0].message.content or ''
    return {
        'parsed': None,
        'seconds': round(seconds, 3),
        'input_tokens': getattr(usage, 'prompt_tokens', 0) or 0,
        'output_tokens': getattr(usage, 'completion_tokens', 0) or 0,
        'reasoning_tokens': getattr(details, 'reasoning_tokens', 0) or 0,
        'error': f'{type(stopped).__name__}: stopped before the output was complete '
                 f'({len(content)} characters, starting {content[:200]!r})',
    }


def plan_query(chain: Runnable, question: str) -> dict:
    """Route one question.

    Returns:
        `plan` (a QueryPlan; the fallback plan when the model gave none), `fell_back`, and the
        call's `seconds`, token counts and `error`.
    """
    call = _call(chain, {'question': question})
    plan = call.pop('parsed')
    return {**call, 'plan': plan or fallback_plan(question), 'fell_back': plan is None}


def expand_query(chain: Runnable, search_query: str, versions: int) -> dict:
    """Ask for alternative versions of a broad question (multi-query).

    The rewritten search query is expanded, not the raw question: it already carries the
    domain reading and the terms of art.

    Returns:
        `queries` (possibly empty), and the call's `seconds`, token counts and `error`.
    """
    call = _call(chain, {'question': search_query, 'versions': versions})
    parsed = call.pop('parsed')
    queries = [q.strip() for q in (parsed.queries if parsed else []) if q.strip()]
    return {**call, 'queries': queries}


def behaviour(plan: QueryPlan) -> str:
    """The coarse behaviour the plan leads to: answer, clarify, or one of the two declines.

    Whether an answer is direct, broad, partial or 'not found' is not the router's to know: that
    depends on what the search finds.
    """
    if plan.route in BEHAVIOUR:
        return BEHAVIOUR[plan.route]
    return 'clarify' if plan.needs_clarification else 'answer'


def shelf_filter(plan: QueryPlan) -> dict | None:
    """The Chroma metadata filter for the plan's shelf; None searches both shelves."""
    return None if plan.shelf == 'both' else {'shelf': plan.shelf}


def search(plan: QueryPlan, k: int, use_shelf_filter: bool, extra_queries: list[str] | None = None,
           use_concept_query: bool = False, use_keyword_search: bool = False, bm25_on_keywords: bool = False,
           store=None, keyword_index=None, with_signal: bool = False, trace: dict | None = None,
           demote_sections=frozenset()):
    """Retrieve for a plan: nothing for a decline, one search, or several fused by RRF.

    Args:
        plan: The router's plan.
        k: How many chunks to return (each query searches k, the fused list is cut to k).
        use_shelf_filter: Whether the plan's shelf restricts the search.
        extra_queries: Multi-query versions, searched next to the plan's own query.
        use_concept_query: Whether the plan's step-back query is searched too, when it has one.
        use_keyword_search: Whether BM25 runs next to the vector search (phase 5, hybrid).
        bm25_on_keywords: Whether BM25 searches the plan's keywords instead of the query sentences
            (the course's `title_search` idea, rag_from_scratch 11: a succinct keyword version of
            the query for a second index). Falls back to the sentences when there are no keywords.
        store: The vector store; the persistent index when None.
        keyword_index: The BM25 index; the one built from the persistent index when None.
        with_signal: Also return the best vector similarity (the relevance floor's input).
        trace: A dict to fill with every ranked list and the fusion, each list labelled with the
            part of the plan it searched (phase 10). It changes nothing in the result.
        demote_sections: Section titles whose chunks yield their rank to all others before the cut (phase 6).

    Returns:
        The chunks, or (chunks, best similarity) with `with_signal`.
    """
    if plan.route != 'search':
        return ([], None) if with_signal else []
    filters = shelf_filter(plan) if use_shelf_filter else None
    concept = [plan.concept_query] if use_concept_query and (plan.concept_query or '').strip() else []
    queries = [plan.search_query, *concept, *(extra_queries or [])]
    roles = ['search_query', *['concept_query'] * len(concept),
             *[f'multi-query {n}' for n in range(1, len(extra_queries or []) + 1)]]
    if use_keyword_search:
        keywords = [' '.join(plan.keywords)] if bm25_on_keywords and plan.keywords else None
        found = retrieval.hybrid_retrieve(queries, k=k, filters=filters, store=store, keyword_index=keyword_index,
                                          keyword_queries=keywords, with_signal=with_signal, trace=trace,
                                          demote_sections=demote_sections)
        if trace is not None:
            for entry, role in zip(trace['lists'], roles + (['keywords'] if keywords else roles)):
                entry['role'] = role
        return found
    lists = [retrieval.retrieve(query, k=k, filters=filters, store=store) for query in queries]
    fused = retrieval.demoted(lists[0] if len(lists) == 1 else retrieval.reciprocal_rank_fusion(lists), demote_sections)[:k]
    if trace is not None:
        retrieval.record_lists(trace, [('vector', q, found) for q, found in zip(queries, lists)], fused)
        for entry, role in zip(trace['lists'], roles):
            entry['role'] = role
    if with_signal:
        return fused, max((found[0]['similarity'] for found in lists if found), default=None)
    return fused
