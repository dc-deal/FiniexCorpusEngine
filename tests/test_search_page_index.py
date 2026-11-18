import importlib
import json
import math
import sys
from pathlib import Path

import pytest

from backend.configuration import data_paths
from backend.conversion.store.reading_store import REPO
from backend.search import coverage_gate, page_index

LEGACY = data_paths.LICENSED_WORKING / 'legacy_markdown'
PROSE = ' '.join(['The circuit breaker opens after repeated timeouts and stays open for a while.'] * 4)


def work(*pages: str, index: str = '') -> str:
    return '\n'.join(f'<!-- page {number} -->\n{body}' for number, body in pages) + (f'\n## Index\n{index}' if index else '')


def test_the_tokenizer_keeps_identifiers_with_their_parts_and_drops_possessives():
    assert page_index.tokenize("The venue's dry_run uses MT5, a x") == ['the', 'venue', 'dry_run', 'dry', 'run', 'uses', 'mt5']


def test_a_page_without_a_number_counts_by_its_ordinal_and_its_line_is_measured():
    pages = page_index.pages_of(work(('None', PROSE), ('None', PROSE)), 'w', 'w.md')
    assert [(page.page, page.line) for page in pages] == [('1', 2), ('2', 4)]


def test_structural_pages_and_a_late_back_index_are_left_out():
    contents = '\n'.join(f'Chapter {n} .... {n * 10}' for n in range(1, 40))
    text = work(('1', contents), ('2', PROSE), ('3', PROSE)) + '\n' * 2
    text += '\n'.join(['filler line of the book'] * 60) + '\n## Index\nbreaker, 12, 40, 77\n'
    pages = page_index.pages_of(text, 'w', 'w.md')
    assert [page.page for page in pages] == ['2', '3'] and all('Index' not in page.text for page in pages)


def test_postings_give_the_same_scores_as_scoring_every_page():
    pages = [page_index.Page('w', str(n), 1, text, 'w.md') for n, text in enumerate([
        PROSE, 'retry with backoff and jitter ' * 30, PROSE + ' retry ' * 3, 'idempotent requests may be retried safely ' * 20])]
    index = page_index.PageIndex(pages)
    query = 'retry retry breaker timeouts'
    docs = [page_index.tokenize(page.text) for page in pages]
    average = sum(map(len, docs)) / len(docs)
    expected = []
    for number, words in enumerate(docs):
        score = 0.0
        for term in page_index.tokenize(query):
            if term in words:
                n = sum(1 for doc in docs if term in doc)
                idf = math.log(1 + (len(docs) - n + 0.5) / (n + 0.5))
                f = words.count(term)
                score += idf * f * (page_index.K1 + 1) / (f + page_index.K1 * (1 - page_index.B + page_index.B * len(words) / average))
        if score > 0:
            expected.append((score, number))
    expected.sort(reverse=True)
    assert [(round(score, 12), page.page) for score, page in index.search(query, 10)] == [(round(s, 12), str(n)) for s, n in expected]


def test_the_snippet_opens_at_the_longest_query_word():
    text = 'Some words first. ' * 10 + 'Then the idempotency key decides. ' + 'More words after. ' * 10
    assert page_index.snippet(text, 'the idempotency').startswith(text[text.find('idempotency') - 40:][:20])


def test_a_probe_comes_from_the_middle_third_and_needs_six_uncommon_words():
    lines = ['Short line.'] + [f'Line number {n} talks about volatility clustering regimes and stationarity tests in markets' for n in range(30)]
    probe = coverage_gate.build_probe('\n'.join(lines))
    assert probe is not None and len(probe.split()) == 8 and 'the' not in probe.lower().split()


@pytest.mark.slow
def test_the_port_gives_the_predecessor_s_scores_and_order():
    config = LEGACY / 'predecessor.json'
    if not config.exists():
        pytest.skip('no predecessor on this machine')
    tools = Path(json.loads(config.read_text(encoding='utf-8'))['tools'])
    sys.path.insert(0, str(tools))
    try:
        predecessor = importlib.import_module('books_search')
    finally:
        sys.path.remove(str(tools))
    chunks = predecessor.load_chunks()
    index = page_index.PageIndex(page_index.load_works(LEGACY, {}))
    for query in ('circuit breaker retry give up', 'minimum backtest length', 'kelly criterion fraction of capital',
                  'order book liquidity spread', 'idempotent consumer duplicate messages'):
        theirs = [(round(score, 9), chunks[i][0], chunks[i][1]) for score, i in predecessor.rank(chunks, query, 10)]
        ours = [(round(score, 9), page.work, page.page) for score, page in index.search(query, 10)]
        assert ours == theirs, query


@pytest.mark.slow
def test_every_legacy_work_is_reached_by_its_own_probe():
    if not (LEGACY / 'keys.json').exists():
        pytest.skip('the licensed works are not on this machine')
    result = coverage_gate.run_gate(LEGACY, json.loads((LEGACY / 'keys.json').read_text(encoding='utf-8'))['keys'])
    assert result['reached'] == result['works'] == 55 and result['rank_1'] >= 53


def test_a_numbered_marker_is_the_pdf_page_and_an_unnumbered_or_epub_one_is_not():
    numbered = page_index.pages_of(work(('7', PROSE)), 'w', 'w.md')
    unnumbered = page_index.pages_of(work(('None', PROSE)), 'w', 'w.md')
    from_epub = page_index.pages_of(work(('7', PROSE)), 'w', 'w.md', numbers_are_pdf_pages=False)
    assert (numbered[0].pdf, unnumbered[0].pdf, from_epub[0].pdf) == ('7', None, None)


def test_a_page_knows_the_heading_in_effect_and_its_last_line():
    text = '# Part One\n' + work(('1', PROSE), ('2', '## Stability\n' + PROSE))
    first, second = page_index.pages_of(text, 'w', 'w.md')
    assert (first.section, second.section) == ('Part One', 'Stability')
    assert first.line_end == second.line - 2


def test_a_filtered_search_ranks_on_the_whole_index():
    pages = [page_index.Page('a', '1', 1, 'retry backoff jitter ' * 30, 'a.md', knowledge_base='free'),
             page_index.Page('b', '1', 1, 'retry ' * 3 + PROSE, 'b.md', knowledge_base='licensed')]
    index = page_index.PageIndex(pages)
    whole = {page.work: score for score, page in index.search('retry', 5)}
    only_b = {page.work: score for score, page in index.search('retry', 5, lambda page: page.knowledge_base == 'licensed')}
    assert only_b == {'b': whole['b']}


def test_the_gate_over_pages_reaches_each_work_by_its_own_probe():
    lines = lambda topic: '\n'.join(f'Line {n} discusses {topic} carefully with distinctive vocabulary throughout these paragraphs' for n in range(30))
    pages = [page_index.Page('alpha', '1', 1, lines('volatility clustering regimes'), 'a'),
             page_index.Page('beta', '1', 1, lines('idempotent consumers deduplicate messages'), 'b')]
    result = coverage_gate.run_gate_pages(pages)
    assert result['reached'] == result['works'] == 2
