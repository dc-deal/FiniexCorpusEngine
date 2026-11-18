"""The second reader: another company's model through OpenRouter, for pages the default reader could not give (63.a)."""

import json
from types import SimpleNamespace

import httpx
import openai
import pymupdf
import pytest

from backend.conversion.checks import check_run
from backend.conversion.reading import reader_requests, reading_cells, second_reader, vision_batches
from backend.conversion.store import reading_store
from backend.providers import openrouter_client

MODEL = 'openai/gpt-6.1-terra'
DEVIATION = second_reader.DEVIATIONS['blocked']


def response(text: str = 'a page', finish_reason: str = 'stop', cost: float = 0.012):
    usage = SimpleNamespace(model_dump=lambda: {'prompt_tokens': 7000, 'completion_tokens': 1800, 'cost': cost})
    return SimpleNamespace(id='gen-1', model=MODEL, provider='OpenAI', usage=usage,
                           choices=[SimpleNamespace(finish_reason=finish_reason, message=SimpleNamespace(content=text))])


class Completions:
    def __init__(self, answers):
        self.answers, self.bodies = list(answers), []

    def create(self, **body):
        self.bodies.append(body)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def cell(tmp_path, monkeypatch):
    """A free second reader's cell of two blocked pages of a small PDF, a store outside the repository, OpenRouter faked."""
    pdf = tmp_path / 'w_book.pdf'
    document = pymupdf.open()
    for number in (1, 2):
        document.new_page().insert_text((72, 72), f'page {number}')
    document.save(pdf)
    source = tmp_path / 'pages.json'
    source.write_text(json.dumps({'work_cards': {'w': 'A card.'}, 'pages': [
        {'file': 'w_book.pdf', 'pdf_page': number, 'work': 'w', 'gold': False, 'class_note': '', 'expected_output_tokens': 1900,
         'deviation': DEVIATION} for number in (1, 2)]}), encoding='utf-8')
    named = reading_cells.Cell('FREE-2ND-TERRA', MODEL, 'hi', 'markdown', source, mode='openrouter')
    store = reading_store.Store(tmp_path / 'vision')
    monkeypatch.setattr(reading_cells, 'known_cells', lambda: {named.name: named})
    monkeypatch.setattr(reading_cells, 'source_of', lambda file_name: ('free', pdf))
    monkeypatch.setattr(second_reader, 'open_store', lambda mirror: store)
    monkeypatch.setattr(vision_batches, 'open_store', lambda mirror: store)
    monkeypatch.setattr(vision_batches, 'check_reading', lambda entry, text, stop: ('ok' if stop == 'end_turn' else 'truncated', {}))
    monkeypatch.setattr(openrouter_client, 'model_prices', lambda ids: {MODEL: {'input': 1.0, 'output': 5.0}})
    monkeypatch.setattr(openrouter_client, 'key_usage', lambda: 9.3)
    return named, store


def run(monkeypatch, answers, **options):
    completions = Completions(answers)
    monkeypatch.setattr(second_reader, 'client', lambda: SimpleNamespace(chat=SimpleNamespace(completions=completions)))
    args = SimpleNamespace(**{'knowledge_base': 'free', 'reader': 'TERRA', 'limit': 0, 'key_cap': 28.0, 'dry_run': False, **options})
    return second_reader.read(args), completions


def test_a_second_reading_is_stored_with_its_deviation_and_paid_by_the_course_key_not_the_claude_credit(cell, monkeypatch):
    _, store = cell
    result, completions = run(monkeypatch, [response(), response(finish_reason='length')])
    assert result['classes'] == {'ok': 1, 'truncated': 1}
    records = [record for record in store.readings() if record.get('kind') == 'reading']
    assert {record['deviation'] for record in records} == {DEVIATION} and {record['provider'] for record in records} == {'openrouter'}
    assert store.spent_usd() == 0.0 and store.spent_usd('openrouter') == pytest.approx(0.024)
    body = completions.bodies[0]
    assert body['model'] == MODEL and body['messages'][0]['content'] == reader_requests.system_prompt('markdown')
    assert body['messages'][1]['content'][0]['type'] == 'image_url' and body['extra_body'] == {'usage': {'include': True}}


def test_a_page_already_read_is_never_bought_again(cell, monkeypatch):
    run(monkeypatch, [response(), response()])
    result, completions = run(monkeypatch, [])
    assert result['pages'] == 0 and completions.bodies == []


def test_a_passing_failure_is_not_stored_so_the_page_can_be_asked_again(cell, monkeypatch):
    _, store = cell
    timeout = openai.APITimeoutError(request=httpx.Request('POST', 'https://openrouter.ai/api/v1/chat/completions'))
    result, _ = run(monkeypatch, [timeout, response()])
    assert result['classes'] == {'passing failure, not stored': 1, 'ok': 1}
    assert len([record for record in store.readings() if record.get('kind') == 'reading']) == 1


def test_the_reader_stops_before_the_course_key_passes_its_cap(cell, monkeypatch):
    _, store = cell
    monkeypatch.setattr(openrouter_client, 'key_usage', lambda: 27.99)  # one page's estimate would pass 28
    _, completions = run(monkeypatch, [response(), response()])
    assert completions.bodies == [] and not [record for record in store.readings() if record.get('kind') == 'reading']


def test_pages_read_side_by_side_are_each_stored_once(cell, monkeypatch):
    _, store = cell
    result, completions = run(monkeypatch, [response(), response()], workers=2)
    assert result['classes'] == {'ok': 2} and len(completions.bodies) == 2
    assert len({record['pdf_page'] for record in store.readings() if record.get('kind') == 'reading'}) == 2


def test_side_by_side_requests_reserve_their_estimate_so_together_they_never_pass_the_cap(cell, monkeypatch):
    estimate = run(monkeypatch, [], dry_run=True)[0]['estimate_usd'] / 2  # one page's estimate
    monkeypatch.setattr(openrouter_client, 'key_usage', lambda: 28.0 - 1.5 * estimate)  # room for one page, not for two
    _, completions = run(monkeypatch, [response(), response()], workers=2)
    assert len(completions.bodies) == 1


def test_a_second_reading_has_its_own_key_and_no_claude_parameter_in_it():
    spec = second_reader.reading_spec(image_sha='i', model=MODEL, system_sha='s', user_sha='u')
    other = second_reader.reading_spec(image_sha='i', model='google/gemini-4-argon', system_sha='s', user_sha='u')
    assert 'anthropic_version' not in json.dumps(spec) and spec['mode'] == 'openrouter'
    assert reader_requests.reading_key(spec) != reader_requests.reading_key(other)


def test_free_pages_get_a_second_reader_when_malformed_and_licensed_ones_only_when_blocked_or_declined():
    assert set(second_reader.REASONS['free']) == {'blocked', 'refused', 'malformed'}
    assert set(second_reader.REASONS['licensed']) == {'blocked', 'refused'}


def test_every_page_of_a_second_reader_s_cell_goes_to_the_judge(cell, tmp_path):
    named, store = cell
    policy = check_run.policy_of(store, [named.name])
    assert policy.sample_per_work >= check_run.EVERY_PAGE


def test_every_candidate_pilot_reads_the_same_pages_first():
    pages = [{'file': f'{name}.pdf', 'pdf_page': n} for name in 'abc' for n in range(1, 6)]
    assert second_reader.pilot_order(pages) == second_reader.pilot_order(list(reversed(pages)))


def test_a_route_the_key_may_not_use_is_not_stored_but_a_moderation_refusal_is(cell, monkeypatch):
    _, store = cell
    request = httpx.Request('POST', 'https://openrouter.ai/api/v1/chat/completions')
    no_route = openai.NotFoundError('0 endpoints out of 2 requested are available matching your guardrail', body=None,
                                    response=httpx.Response(404, request=request))
    flagged = openai.PermissionDeniedError('flagged by moderation', body=None, response=httpx.Response(403, request=request))
    result, _ = run(monkeypatch, [no_route, flagged])
    assert result['classes'] == {'passing failure, not stored': 1, 'errored': 1}
    (record,) = [record for record in store.readings() if record.get('kind') == 'reading']
    assert record['error_type'] == 'http_403'


def test_only_a_second_reading_the_judge_found_ok_is_chosen_and_only_once(cell, monkeypatch, tmp_path):
    from backend.conversion.store import pipeline_db, reading_export

    named, store = cell
    run(monkeypatch, [response(), response()])
    keys = sorted(record['reading_key'] for record in store.readings() if record.get('kind') == 'reading')
    monkeypatch.setattr(pipeline_db, 'PATHS', {'free': tmp_path / 'pipeline.sqlite'})
    monkeypatch.setattr(reading_export, 'check_states', lambda store, cells: {keys[0]: {'state': 'ok'}, keys[1]: {'state': 'issue'}})
    args = SimpleNamespace(knowledge_base='free', reader='TERRA')
    assert second_reader.choose(args) == {'chosen': 1, 'not chosen: issue': 1}
    (choice,) = pipeline_db.chosen('free').values()
    assert choice['reading_key'] == keys[0] and choice['why'] == f'second reader ({MODEL}): {DEVIATION}'
    assert second_reader.choose(args) == {'already chosen': 1, 'not chosen: issue': 1}


def test_a_stopped_work_s_pages_stay_in_the_cell_naming_the_reader_whose_check_stopped_it():
    # 130.a and 288.a: the list is the cell, and the cell's report keeps the stop; leaving the pages out lost it (17 Nov).
    # The stop is a reader's: the page names the cells that stopped its work.
    blocked = {'text_file': None, 'error_type': 'invalid_request_error'}
    rows = [{'file': 'open.pdf', 'pdf_page': 1, **blocked}, {'file': 'stopped.pdf', 'pdf_page': 1, **blocked},
            {'file': 'stopped.pdf', 'pdf_page': 2, **blocked}]
    listed = {(row['file'], row['pdf_page']): {'file': row['file'], 'pdf_page': row['pdf_page'], 'work': row['file'][:-4],
                                               'expected_output_tokens': 1800, 'work_card': 'a card'} for row in rows}
    chosen, reasons, held = second_reader.select(rows, listed, 'free', {'stopped': {'FREE-2ND-MISTRAL'}})
    assert [(page['file'], page['pdf_page'], page.get('stopped_by')) for page in chosen] == [
        ('open.pdf', 1, None), ('stopped.pdf', 1, ['FREE-2ND-MISTRAL']), ('stopped.pdf', 2, ['FREE-2ND-MISTRAL'])]
    assert reasons == {'blocked': 3} and held == {'stopped': 2}


def test_a_page_whose_second_reading_a_stop_holds_back_joins_the_cell_under_its_first_reason(monkeypatch):
    # 288.a: a judge-passed second reading of a blocked page is held back by its reader's stop; another reader may read it
    held_back = {'file': 'stopped.pdf', 'pdf_page': 3, 'deviation': second_reader.DEVIATIONS['refused']}
    other = {'file': 'stopped.pdf', 'pdf_page': 4, 'deviation': None}
    monkeypatch.setattr(second_reader.served_readings, 'text_layer_why', lambda row: 'stopped')
    listed = {(row['file'], row['pdf_page']): {'file': row['file'], 'pdf_page': row['pdf_page'], 'work': 'stopped',
                                               'expected_output_tokens': 1800, 'work_card': 'a card'}
              for row in (held_back, other)}
    chosen, reasons, _ = second_reader.select([held_back, other], listed, 'free', {'stopped': {'FREE-2ND-MISTRAL'}})
    assert [(page['pdf_page'], page['deviation']) for page in chosen] == [(3, second_reader.DEVIATIONS['refused'])]
    assert reasons == {'refused': 1}


def test_a_page_a_second_reading_serves_stays_in_the_cell_so_the_sample_gate_counts_it(monkeypatch):
    # 18 Nov: chosen pages left the list, and a reader's gate on a work counted only the bad pages left behind
    served = {'file': 'w.pdf', 'pdf_page': 1, 'deviation': second_reader.DEVIATIONS['blocked']}
    default = {'file': 'w.pdf', 'pdf_page': 2, 'deviation': None}
    monkeypatch.setattr(second_reader.served_readings, 'text_layer_why', lambda row: None)
    listed = {(row['file'], row['pdf_page']): {'file': row['file'], 'pdf_page': row['pdf_page'], 'work': 'w',
                                               'expected_output_tokens': 1800, 'work_card': 'a card'}
              for row in (served, default)}
    chosen, reasons, _ = second_reader.select([served, default], listed, 'free', {})
    assert [(page['pdf_page'], page.get('served')) for page in chosen] == [(1, True)]  # a default reading is not listed
    assert reasons == {'blocked': 1}


def test_a_page_whose_second_reading_is_served_is_never_read_again(cell, monkeypatch):
    source = reading_cells.known_cells()['FREE-2ND-TERRA'].page_source
    listing = json.loads(source.read_text(encoding='utf-8'))
    listing['pages'][0]['served'] = True
    source.write_text(json.dumps(listing), encoding='utf-8')
    result, completions = run(monkeypatch, [response()])
    assert result['pages'] == 1 and len(completions.bodies) == 1


def test_a_page_of_a_stopped_work_is_not_read_again_by_the_reader_stopped_there_but_by_another(cell, monkeypatch):
    # 130.a: a second reading by the stopped reader would buy nothing; 288.a: another reader reads it
    source = reading_cells.known_cells()['FREE-2ND-TERRA'].page_source
    listing = json.loads(source.read_text(encoding='utf-8'))
    listing['pages'][0]['stopped_by'] = ['FREE-2ND-TERRA']
    listing['pages'][1]['stopped_by'] = ['FREE-2ND-MISTRAL']
    source.write_text(json.dumps(listing), encoding='utf-8')
    result, completions = run(monkeypatch, [response()])
    assert result['pages'] == 1 and len(completions.bodies) == 1
