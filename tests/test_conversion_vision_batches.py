import dataclasses
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import anthropic
import pymupdf
import pytest
from anthropic.types.messages import MessageBatchIndividualResponse

from backend.conversion.contract import page_contract
from backend.conversion.reading import page_render, reader_requests, reading_cells, vision_batches
from backend.conversion.store import reading_store
from backend.providers import anthropic_client

CONVERSION = Path(vision_batches.__file__).parents[1]  # conversion/, its modules in concern folders since 208.b
EXAMPLE_PAGE = Path(__file__).resolve().parent / 'fixtures' / 'page_contract' / 'openstax-finance-2e_p0179.page.md'
PAGE_TEXT = 'A sentence of the page that the console must never show.'
BLOCKED = 'Output blocked by content filtering policy'


# ---------------------------------------------------------------- the fake API

def page_text(form='markdown', work='public-work', pdf_page=1, size=(1688, 2184), page_class='paragraph') -> str:
    """A small page in a form; the class 'sidebar' makes it malformed, since the contract has no such class."""
    front = {'contract': 'page/1', 'work': work, 'pdf_page': str(pdf_page), 'image_size': f'{size[0]}x{size[1]}', 'printed_label': '7',
             'page_kind': 'body'}
    if form == 'json':
        return json.dumps({'front': [{'name': name, 'value': value} for name, value in front.items()],
                           'blocks': [{'id': 'b01', 'class': page_class, 'attrs': [{'name': 'bbox', 'value': '10 10 200 50'}], 'body': PAGE_TEXT}]})
    lines = [f'{name}: "{value}"' for name, value in front.items()]
    return '\n'.join(['---', *lines, '---', '', f'::: {{#b01 .{page_class} bbox="10 10 200 50"}}', PAGE_TEXT, ':::', ''])


def answer_of(entry: dict, page_class='paragraph') -> str:
    return page_text(entry['form'], entry['work'], entry['pdf_page'], tuple(entry['image_size']), page_class)


class Usage:
    def __init__(self, **values):
        self.values = values

    def to_dict(self) -> dict:
        return dict(self.values)


def message_of(text: str, stop_reason='end_turn', model='claude-haiku-5-5') -> SimpleNamespace:
    # A thinking block first: 5.5 models can begin with one.
    return SimpleNamespace(id='msg_1', model=f'{model}-20261001', stop_reason=stop_reason, stop_details=None,
                           content=[SimpleNamespace(type='thinking', thinking='hm'), SimpleNamespace(type='text', text=text)],
                           usage=Usage(input_tokens=4900, output_tokens=1000, cache_creation_input_tokens=0, cache_read_input_tokens=4500))


def succeeded(text: str, stop_reason='end_turn') -> SimpleNamespace:
    return SimpleNamespace(type='succeeded', message=message_of(text, stop_reason))


def errored(message=BLOCKED, error_type='invalid_request_error') -> SimpleNamespace:
    return SimpleNamespace(type='errored', error=SimpleNamespace(error=SimpleNamespace(type=error_type, message=message)))


class FakeBatches:
    def __init__(self):
        self.created, self.deleted, self.results_by_batch, self.running, self.gone = [], [], {}, [], set()
        self.processing_status = 'ended'
        self.before_create, self.create_error = None, None

    def create(self, requests):
        if self.before_create:
            self.before_create()
        if self.create_error:
            raise self.create_error
        batch_id = f'msgbatch_{len(self.created)}'
        self.created.append((batch_id, requests))
        return SimpleNamespace(id=batch_id)

    def retrieve(self, batch_id):
        return SimpleNamespace(id=batch_id, processing_status=self.processing_status, request_counts=SimpleNamespace(processing=1, succeeded=0))

    def results(self, batch_id):
        for custom_id, outcome in self.results_by_batch[batch_id]:
            if isinstance(outcome, Exception):
                raise outcome
            yield SimpleNamespace(custom_id=custom_id, result=outcome)

    def delete(self, batch_id):
        if batch_id in self.gone:
            raise anthropic.NotFoundError('gone', response=SimpleNamespace(request=None, status_code=404, headers={}), body=None)
        self.deleted.append(batch_id)

    def list(self, limit=100):
        return [SimpleNamespace(id=batch_id, processing_status='in_progress') for batch_id in self.running]


class FakeStream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *details):
        return False

    def get_final_message(self):
        return self.message


class FakeMessages:
    def __init__(self):
        self.batches = FakeBatches()
        self.counted, self.streamed = [], []
        self.stream_answer = None

    def count_tokens(self, **params):
        self.counted.append(params)
        has_image = not isinstance(params['messages'][0]['content'], str)
        return SimpleNamespace(input_tokens=5000 + (4761 if has_image else 0) + (700 if 'format' in params['output_config'] else 0))

    def stream(self, **params):
        self.streamed.append(params)
        form = 'json' if 'format' in params['output_config'] else 'markdown'
        outcome = self.stream_answer(params) if self.stream_answer else message_of(page_text(form), model=params['model'])
        if isinstance(outcome, Exception):
            raise outcome
        return FakeStream(outcome)


class FakeClient:
    def __init__(self):
        self.messages = FakeMessages()
        self.models = SimpleNamespace(retrieve=lambda model: SimpleNamespace(id=model, display_name=model.upper()))


def bad_request(text: str) -> anthropic.BadRequestError:
    return anthropic.BadRequestError(text, response=SimpleNamespace(request=None, status_code=400, headers={}), body=None)


# ---------------------------------------------------------------- a runner in a temporary world

@pytest.fixture
def world(tmp_path, monkeypatch):
    """The runner with its stores in tmp_path, a public PDF of its own, one work of two pages, the four cells, a fake client."""
    for mirror in ('licensed', 'free'):
        monkeypatch.setitem(reading_store.ROOTS, mirror, tmp_path / mirror / 'vision')
    free_archive, licensed_archive = tmp_path / 'raw', tmp_path / 'private'
    free_archive.mkdir()
    licensed_archive.mkdir()
    with pymupdf.open() as document:
        for number in (1, 2, 3):
            document.new_page(width=612, height=792).insert_text((72, 72), f'Public page {number}.')
        document.save(free_archive / 'public.pdf')
        document.save(licensed_archive / 'private.pdf')
    monkeypatch.setattr(reading_cells, 'FREE_ARCHIVE', free_archive)
    monkeypatch.setattr(reading_cells, 'LICENSED_ARCHIVE', licensed_archive)
    monkeypatch.setattr(reading_cells, 'PROVENANCE', tmp_path / 'provenance.json')
    source = tmp_path / 'pages.json'
    write_pages(source, 'public.pdf', (1, 2))
    monkeypatch.setattr(reading_cells, 'CELLS', {name: dataclasses.replace(cell, page_source=source) for name, cell in reading_cells.CELLS.items()})
    monkeypatch.setattr(vision_batches, 'SMOKE_PLAN', tuple((name, 'public-work:p0001') for name in reading_cells.CELLS))
    monkeypatch.setattr(vision_batches, 'FREE_CHECK_PAGE', 'public-work:p0001')
    client = FakeClient()
    monkeypatch.setattr(anthropic_client, 'client', lambda: client)
    return SimpleNamespace(client=client, batches=client.messages.batches, source=source, tmp=tmp_path,
                           free=reading_store.open_store('free'), licensed=reading_store.open_store('licensed'))


def write_pages(source: Path, file_name: str, pdf_pages: tuple, card='A card of the work.') -> None:
    source.write_text(json.dumps({'work_cards': {'public-work': card}, 'pages': [
        {'file': file_name, 'pdf_page': number, 'work': 'public-work', 'gold': False, 'class_note': 'a note', 'expected_output_tokens': 1200}
        for number in pdf_pages]}), encoding='utf-8')


def run(*argv: str) -> None:
    args = vision_batches.build_parser().parse_args(argv)
    args.run(args)


def plan(cell='MP-HM', **options) -> tuple[list, Counter]:
    return vision_batches.plan_entries(reading_cells.CELLS[cell], vision_batches.Documents(), **options)


def finish(world, outcome_for=None) -> None:
    """Every batch still open ends with these outcomes, and is collected."""
    outcome_for = outcome_for or (lambda entry: succeeded(answer_of(entry)))
    for manifest in world.licensed.manifests():
        if manifest['status'] == 'submitted':
            world.batches.results_by_batch[manifest['batch_id']] = [(entry['custom_id'], outcome_for(entry)) for entry in manifest['requests']]
    run('collect')


def sent(world) -> list:
    return [request for _, requests in world.batches.created for request in requests]


def old_entry(custom_id='r0123', **changes) -> dict:
    """A request as the manifests of contract v1.1 hold it: no kind, no work, no user hash, form 'image'."""
    entry = {'reading_key': 'ab' * 32, 'custom_id': custom_id, 'cell': 'M1', 'page_id': 'P1', 'file': 'public.pdf', 'pdf_page': 1, 'mirror': 'free',
             'model': 'claude-haiku-5-5', 'resolution': 'hi', 'form': 'image', 'replicate': 0, 'attempt': 0, 'max_tokens': 16000,
             'image_sha256': 'c' * 64, 'image_size': [1687, 2184], 'image_bytes': 1000, 'system_sha256': 'd' * 64, 'mode': 'batch', 'estimate_usd': 0.01}
    entry.update(changes)
    return {name: value for name, value in entry.items() if value is not None}


def old_manifest(status: str, requests: list, **extra) -> dict:
    return {'local_id': f'2026-10-29T200824_00_{status}', 'status': status, 'created_at': '2026-10-29T20:08:24+00:00', 'cells': ['M1'],
            'estimate_usd': 0.25, 'requests': requests, 'cap_usd': 5.0, 'batch_id': f'msgbatch_old_{status}', **extra}


# ---------------------------------------------------------------- the guard

def status_of(spent=0.0, open_estimate=0.0, unknown=()):
    return {'spent_usd': spent, 'open_estimate_usd': open_estimate, 'unknown_running_batches': list(unknown)}


def test_the_guard_counts_spend_and_running_batches_with_a_margin():
    vision_batches.guard(status_of(spent=1.0, open_estimate=1.0), new_estimate=1.0, cap=5.0)  # 1 + 1.3 x 2 = 3.6
    with pytest.raises(SystemExit, match='refused'):
        vision_batches.guard(status_of(spent=2.0, open_estimate=1.0), new_estimate=1.5, cap=5.0)  # 2 + 1.3 x 2.5 = 5.25


def test_a_running_batch_nobody_knows_stops_every_submission():
    with pytest.raises(SystemExit, match='no manifest knows'):
        vision_batches.guard(status_of(unknown=['msgbatch_x']), new_estimate=0.0, cap=100.0)


def test_the_default_cap_stays_5_usd():
    assert vision_batches.DEFAULT_CAP_USD == 5.0
    assert vision_batches.build_parser().parse_args(['submit', '--cells', 'MP-HM']).cap == 5.0


def test_packs_respect_the_request_and_byte_limits():
    entries = [{'image_bytes': 1_000_000} for _ in range(250)]
    packs = vision_batches.packs(entries)
    assert sum(len(p) for p in packs) == 250
    assert all(sum(e['image_bytes'] * 4 // 3 + vision_batches.REQUEST_OVERHEAD_BYTES for e in p) <= vision_batches.PACK_BYTES for p in packs)
    assert all(len(p) <= vision_batches.PACK_REQUESTS for p in packs)


def test_the_overhead_of_a_request_covers_its_longest_text():
    longest = len(reader_requests.system_prompt('json')) + len(json.dumps(page_contract.json_schema())) + 2000
    assert longest < vision_batches.REQUEST_OVERHEAD_BYTES


def test_every_client_is_built_by_anthropic_client():
    # The one place with an explicit key, timeout and no hidden retries (pilot plan, contract test 6).
    paths = list(CONVERSION.glob('**/*.py'))
    assert len(paths) > 20  # every module of every concern folder, not one folder's
    for path in paths:
        assert 'anthropic.Anthropic(' not in path.read_text(encoding='utf-8'), path.name


def test_debug_logging_of_request_bodies_stops_the_runner(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_LOG', 'debug')
    with pytest.raises(SystemExit, match='ANTHROPIC_LOG'):
        vision_batches.quiet_sdk_logs()


# ---------------------------------------------------------------- planning

def test_an_entry_carries_its_kind_form_work_and_image_size(world):
    entries, skipped = plan('MP-SJ')
    assert len(entries) == 2 and not skipped
    entry = entries[0]
    assert (entry['kind'], entry['form'], entry['work'], entry['image_size']) == ('reading', 'json', 'public-work', [1688, 2184])
    assert (entry['cell'], entry['model'], entry['resolution'], entry['attempt'], entry['mode']) == ('MP-SJ', 'claude-sonnet-5-5', 'hi', 0, 'batch')
    assert entry['page_id'] == 'public-work:p0001' and entry['mirror'] == 'free' and entry['estimate_usd'] > 0


def test_each_cell_asks_its_own_question(world):
    keys = [entry['reading_key'] for name in reading_cells.CELLS for entry in plan(name)[0]]
    assert len(keys) == 8 and len(set(keys)) == 8


def test_the_same_plan_twice_has_the_same_keys(world):
    assert [e['reading_key'] for e in plan()[0]] == [e['reading_key'] for e in plan()[0]]


def test_the_parameters_come_from_the_bytes_the_key_was_computed_on(world, monkeypatch):
    entry = plan('MP-HJ')[0][0]
    prompts = world.tmp / 'prompts_changed_later'
    prompts.mkdir()
    (prompts / 'rules.txt').write_text('edited after the plan', encoding='utf-8')
    monkeypatch.setattr(reader_requests, 'RULES_PROMPT', prompts / 'rules.txt')
    params = vision_batches.params_for(entry)
    assert reader_requests.sha256_text(params['system'][0]['text']) == entry['system_sha256']
    image, turn = params['messages'][0]['content']
    assert reader_requests.sha256_text(turn['text']) == entry['user_sha256']
    assert turn['text'].startswith('work: public-work\npdf_page: 1\nimage_size: 1688x2184\n\nWork card: A card of the work.')
    assert image['transformations'] == {'oversized_image': 'error'}
    assert params['output_config']['format']['schema'] == page_contract.json_schema() and params['output_config']['effort'] == 'high'
    assert params['max_tokens'] == entry['max_tokens'] and params['model'] == entry['model']


def test_a_markdown_cell_sends_no_schema(world):
    assert 'format' not in vision_batches.params_for(plan('MP-HM')[0][0])['output_config']


def test_a_file_the_provenance_list_holds_back_is_skipped(world):
    (world.tmp / 'provenance.json').write_text(json.dumps({'files': {'public.pdf': {'send': False}}}), encoding='utf-8')
    entries, skipped = plan()
    assert entries == [] and skipped == {'held by provenance': 2}


def test_a_changed_card_is_a_new_question(world):
    run('submit', '--cells', 'MP-HM')
    finish(world)
    assert plan()[0] == []
    write_pages(world.source, 'public.pdf', (1, 2), card='The card was revised.')
    assert len(plan()[0]) == 2


# ---------------------------------------------------------------- records

@pytest.mark.parametrize('cell', ['MP-HM', 'MP-HJ'])
def test_an_answer_is_parsed_in_its_form_and_the_record_keeps_the_check_without_page_text(world, cell):
    entry = plan(cell)[0][0]
    record, text = vision_batches.record_for(entry, 'succeeded', message_of(answer_of(entry)))
    assert record['result_class'] == 'ok' and record['stop_reason'] == 'end_turn' and PAGE_TEXT in text
    assert record['contract']['valid'] and record['contract']['blocks'] == 1 and record['contract']['printed_label'] == '7'
    assert (record['kind'], record['form'], record['work'], record['image_size']) == ('reading', entry['form'], 'public-work', [1688, 2184])
    assert record['user_sha256'] == entry['user_sha256'] and record['error_message'] is None
    assert PAGE_TEXT not in json.dumps(record)


def test_the_cost_of_a_record_comes_from_its_usage(world):
    entry = plan()[0][0]
    record, _ = vision_batches.record_for(entry, 'succeeded', message_of(answer_of(entry)))
    assert record['cost_usd'] == pytest.approx(anthropic_client.cost_usd('claude-haiku-5-5', 4900, 1000, batch=True, cache_read_tokens=4500))


@pytest.mark.parametrize('cell', ['MP-HM', 'MP-HJ'])
def test_the_reading_must_echo_what_it_was_given(world, cell):
    entry = plan(cell)[0][0]
    for wrong in ({'pdf_page': 9}, {'work': 'another-work'}, {'size': (1000, 1000)}):
        text = page_text(entry['form'], **{'work': 'public-work', 'pdf_page': 1, 'size': (1688, 2184), **wrong})
        record, _ = vision_batches.record_for(entry, 'succeeded', message_of(text))
        assert record['result_class'] == 'malformed', wrong
        assert not record['contract']['valid']


@pytest.mark.parametrize('stop_reason, text, expected', [
    ('refusal', '', 'refused'),
    ('max_tokens', '---\ncontract: page/1', 'truncated'),
    ('pause_turn', 'anything', 'unexpected'),
    ('end_turn', '', 'no_page'),
    ('end_turn', 'I cannot help with this page.', 'no_page'),
])
@pytest.mark.parametrize('cell', ['MP-HM', 'MP-HJ'])
def test_every_answer_falls_into_one_class(world, cell, stop_reason, text, expected):
    entry = plan(cell)[0][0]
    record, stored_text = vision_batches.record_for(entry, 'succeeded', message_of(text, stop_reason))
    assert record['result_class'] == expected and stored_text == text


def test_a_cut_markdown_answer_still_reports_the_blocks_it_closed(world):
    entry = plan()[0][0]
    whole = answer_of(entry)
    record, _ = vision_batches.record_for(entry, 'succeeded', message_of(whole + '::: {#b02 .paragraph bbox="1 1 9 9"}\nCut off he', 'max_tokens'))
    assert record['result_class'] == 'truncated'
    assert record['contract']['blocks'] == 2 and 'block is not closed' in ' '.join(record['contract']['errors'])


def test_an_answer_the_parser_falls_over_is_kept_and_stops_nothing(world, monkeypatch):
    entry = plan('MP-HJ')[0][0]

    def fall_over(*args, **kwargs):
        raise KeyError('name')

    monkeypatch.setattr(page_contract, 'parse', fall_over)
    record, text = vision_batches.record_for(entry, 'succeeded', message_of('{"front": [{"x": 1}], "blocks": []}'))
    assert record['result_class'] == 'no_page' and text
    assert record['contract']['errors'] == ['the parser failed: KeyError']


def test_a_json_answer_of_the_wrong_shape_does_not_stop_a_collect(world):
    run('submit', '--cells', 'MP-HJ')
    finish(world, lambda entry: succeeded('{"front": [{"x": 1}], "blocks": [{"y": 2}]}'))
    assert world.licensed.manifests()[0]['status'] == 'collected'
    assert sum(world.licensed.manifests()[0]['classes'].values()) == 2


# ---------------------------------------------------------------- the kinds of request

def test_a_new_kind_plugs_in_through_the_table_without_touching_the_flow(world, monkeypatch):
    def check(entry, text, stop_reason):
        return 'ok', {'verdict': text, 'judged': entry['judged_key']}

    kind = vision_batches.RequestKind(params=lambda entry: {'model': entry['model'], 'judged': entry['judged_key']}, check=check,
                                      record_field='verdict', extra_fields=('judged_key',))
    monkeypatch.setitem(vision_batches.KINDS, 'judge', kind)
    entry = {**plan()[0][0], 'kind': 'judge', 'judged_key': 'k1', 'reading_key': 'ef' * 32, 'custom_id': 'r' + 'ef' * 20, 'cell': 'JUDGE'}
    assert vision_batches.params_for(entry) == {'model': 'claude-haiku-5-5', 'judged': 'k1'}
    vision_batches.send_entries(world.client, [entry], Counter(), cap=5.0)
    assert sent(world)[0]['params'] == {'model': 'claude-haiku-5-5', 'judged': 'k1'}
    finish(world, lambda _: succeeded('fine'))
    record = world.free.reading('ef' * 32)
    assert record['kind'] == 'judge' and record['result_class'] == 'ok' and record['judged_key'] == 'k1'
    assert record['verdict'] == {'verdict': 'fine', 'judged': 'k1'} and 'contract' not in record
    assert world.free.ledger()[-1]['kind'] == 'judge'


def test_an_entry_without_a_kind_is_a_reading():
    assert vision_batches.kind_of({}) is vision_batches.KINDS['reading']
    assert vision_batches.kind_of({'kind': 'reading'}) is vision_batches.KINDS['reading']


# ---------------------------------------------------------------- submit

def test_the_manifest_is_written_before_the_batch_is_created(world):
    seen = []
    world.batches.before_create = lambda: seen.append([m['status'] for m in world.licensed.manifests()])
    run('submit', '--cells', 'MP-HM,MP-SJ')
    assert seen == [['submitting']]
    manifest = world.licensed.manifests()[0]
    assert manifest['status'] == 'submitted' and manifest['batch_id'] == 'msgbatch_0' and manifest['cells'] == ['MP-HM', 'MP-SJ']
    assert {entry['custom_id'] for entry in manifest['requests']} == {request['custom_id'] for request in sent(world)}
    assert len(sent(world)) == 4


def test_a_dry_run_says_the_estimate_and_buys_nothing(world, capsys):
    run('submit', '--cells', 'MP-HM,MP-SM', '--dry-run')
    out = capsys.readouterr().out
    assert 'requests 4' in out and 'estimate' in out and 'dry run' in out
    assert world.batches.created == [] and world.licensed.manifests() == []


def test_an_unknown_cell_stops_the_submission(world):
    with pytest.raises(SystemExit, match='unknown cells'):
        run('submit', '--cells', 'M1')


@pytest.mark.parametrize('outcome', [
    succeeded('PAGE'), succeeded('{broken', 'max_tokens'), succeeded('', 'refusal'), succeeded('I cannot.'), succeeded('x', 'pause_turn'),
    errored(), errored('overloaded', 'overloaded_error'), SimpleNamespace(type='expired'), SimpleNamespace(type='canceled'),
], ids=['page', 'truncated', 'refused', 'no_page', 'unexpected', 'blocked', 'overloaded', 'expired', 'canceled'])
def test_a_stored_reading_of_any_class_blocks_buying_it_again(world, outcome):
    run('submit', '--cells', 'MP-HM')
    finish(world, lambda entry: outcome)
    assert len(sent(world)) == 2
    run('submit', '--cells', 'MP-HM')
    assert len(sent(world)) == 2


def test_a_malformed_reading_blocks_buying_it_again_too(world):
    run('submit', '--cells', 'MP-HM')
    finish(world, lambda entry: succeeded(answer_of(entry, 'sidebar')))
    assert {record['result_class'] for record in world.free.readings()} == {'malformed'}
    run('submit', '--cells', 'MP-HM')
    assert len(sent(world)) == 2


def test_an_open_batch_holds_its_pages(world, capsys):
    run('submit', '--cells', 'MP-HM')
    run('submit', '--cells', 'MP-HM')
    assert len(sent(world)) == 2 and "'in an open batch': 2" in capsys.readouterr().out


def test_the_guard_counts_the_open_batch_on_the_next_submission(world, capsys):
    run('submit', '--cells', 'MP-SM')
    open_estimate = world.licensed.manifests()[0]['estimate_usd']
    # Enough for the new cell alone, too little with the open batch beside it.
    with pytest.raises(SystemExit, match='refused'):
        run('submit', '--cells', 'MP-SJ', '--cap', str(1.3 * open_estimate * 1.5))
    assert len(world.batches.created) == 1
    run('submit', '--cells', 'MP-SJ', '--cap', '5')
    assert len(world.batches.created) == 2


def test_the_ledgers_of_both_mirrors_count_as_spent(world):
    world.free.append_ledger({'cost_usd': 2.0})
    world.licensed.append_ledger({'cost_usd': 2.99})  # two Sonnet pages are about 0.02 USD, so only the sum of both passes the cap
    with pytest.raises(SystemExit, match='refused'):
        run('submit', '--cells', 'MP-SM')
    assert world.batches.created == []


def test_an_unknown_running_batch_stops_a_submission(world):
    world.batches.running = ['msgbatch_nobody_knows']
    with pytest.raises(SystemExit, match='no manifest knows'):
        run('submit', '--cells', 'MP-HM')
    assert world.batches.created == []


def test_a_failed_create_is_recorded_and_stops(world):
    world.batches.create_error = RuntimeError('network')
    with pytest.raises(SystemExit, match='create failed'):
        run('submit', '--cells', 'MP-HM')
    assert world.licensed.manifests()[0]['status'] == 'create_failed'


# ---------------------------------------------------------------- stage 1 retry

def malformed_on_first_page(entry: dict) -> SimpleNamespace:
    return succeeded(answer_of(entry, 'sidebar' if entry['pdf_page'] == 1 else 'paragraph'))


def test_a_retry_re_reads_only_the_malformed_page_as_attempt_1_with_a_new_key(world):
    run('submit', '--cells', 'MP-HM')
    finish(world, malformed_on_first_page)
    first_key = next(entry['reading_key'] for entry in world.licensed.manifests()[0]['requests'] if entry['pdf_page'] == 1)
    run('submit', '--cells', 'MP-HM', '--retry-malformed')
    assert len(sent(world)) == 3
    retry = next(manifest for manifest in world.licensed.manifests() if manifest['batch_id'] == 'msgbatch_1')['requests']
    assert [(entry['pdf_page'], entry['attempt']) for entry in retry] == [(1, 1)]
    assert retry[0]['reading_key'] != first_key and retry[0]['custom_id'] != reader_requests.custom_id(first_key)
    assert retry[0]['image_sha256'] == world.free.reading(first_key)['image_sha256']
    assert retry[0]['system_sha256'] == world.free.reading(first_key)['system_sha256']


def test_a_page_today_s_validator_accepts_is_not_retried_though_its_record_says_malformed(world, monkeypatch):
    run('submit', '--cells', 'MP-HM')
    finish(world, malformed_on_first_page)
    monkeypatch.setattr(vision_batches, 'check_reading', lambda entry, text, stop_reason: ('ok', None))  # a corrected validator
    run('submit', '--cells', 'MP-HM', '--retry-malformed')
    assert len(sent(world)) == 2
    assert {record['result_class'] for record in world.free.readings()} == {'malformed', 'ok'}  # the records stay as they were


def test_recheck_counts_the_class_moves_under_today_s_validator_and_spends_nothing(world, monkeypatch, capsys):
    run('submit', '--cells', 'MP-HM')
    finish(world, malformed_on_first_page)
    created = len(world.batches.created)
    monkeypatch.setattr(vision_batches, 'check_reading', lambda entry, text, stop_reason: ('ok', None))
    run('recheck', '--cells', 'MP-HM')
    out = capsys.readouterr().out
    assert 'malformed -> ok 1' in out and 'ok -> ok 1' in out
    report =json.loads(next(world.free.path('reports', 'x').parent.glob('recheck_*.json')).read_text(encoding='utf-8'))
    assert report['moves'] == {'malformed -> ok': 1, 'ok -> ok': 1} and len(world.batches.created) == created


def test_the_first_reading_stays_when_the_retry_is_stored(world):
    run('submit', '--cells', 'MP-HM')
    finish(world, malformed_on_first_page)
    run('submit', '--cells', 'MP-HM', '--retry-malformed')
    finish(world)
    records = {(record['pdf_page'], record['attempt']): record['result_class'] for record in world.free.readings()}
    assert records == {(1, 0): 'malformed', (1, 1): 'ok', (2, 0): 'ok'}


def test_a_page_is_retried_once_even_when_the_retry_is_malformed_too(world):
    run('submit', '--cells', 'MP-HM')
    finish(world, malformed_on_first_page)
    run('submit', '--cells', 'MP-HM', '--retry-malformed')
    finish(world, lambda entry: succeeded(answer_of(entry, 'sidebar')))
    assert len(sent(world)) == 3
    run('submit', '--cells', 'MP-HM', '--retry-malformed')
    assert len(sent(world)) == 3


def test_a_retry_tells_the_reader_what_the_format_check_refused(world):
    # Decision 113.a: retried without a hint, 10 of round 6's 15 pages came back with exactly the same error.
    run('submit', '--cells', 'MP-HM')
    finish(world, malformed_on_first_page)
    run('submit', '--cells', 'MP-HM', '--retry-malformed')
    retry = next(manifest for manifest in world.licensed.manifests() if manifest['batch_id'] == 'msgbatch_1')['requests'][0]
    turn = world.free.get_prompt(retry['user_sha256'])
    assert 'The format check refused your previous reading of this page:' in turn and "unknown class 'sidebar'" in turn
    first = next(entry for entry in world.licensed.manifests()[0]['requests'] if entry['pdf_page'] == 1)
    assert turn.startswith(world.free.get_prompt(first['user_sha256']))  # the same turn, the hint beside it


def test_a_page_retried_without_a_hint_before_gets_one_hinted_attempt_more(world, monkeypatch):
    run('submit', '--cells', 'MP-HM')
    finish(world, malformed_on_first_page)
    hint = vision_batches.format_hint
    monkeypatch.setattr(vision_batches, 'format_hint', lambda errors: None)  # a retry as it was sent before 113.a
    run('submit', '--cells', 'MP-HM', '--retry-malformed')
    finish(world, lambda entry: succeeded(answer_of(entry, 'sidebar')))
    # Put back this one function only: monkeypatch.undo() would also take away the fake stores and the offline guard, and
    # the next call would reach the real ones (it did once, 2026-11-08, stopped by the spend guard).
    monkeypatch.setattr(vision_batches, 'format_hint', hint)
    run('submit', '--cells', 'MP-HM', '--retry-malformed')
    hinted = next(manifest for manifest in world.licensed.manifests() if manifest['batch_id'] == 'msgbatch_2')['requests']
    assert [(entry['pdf_page'], entry['attempt']) for entry in hinted] == [(1, 2)]
    assert 'The format check refused' in world.free.get_prompt(hinted[0]['user_sha256'])
    finish(world, lambda entry: succeeded(answer_of(entry, 'sidebar')))
    run('submit', '--cells', 'MP-HM', '--retry-malformed')
    assert len(sent(world)) == 4  # and no further attempt after the hinted one


# The filter rule is absolute: no splitting, no paraphrasing, no second model after a block, no arguing in the prompt.
@pytest.mark.parametrize('outcome', [
    succeeded('', 'refusal'), succeeded('I cannot read this page.'), errored(), errored('the batch was too big'),
    errored('overloaded', 'overloaded_error'), succeeded('---\ncontract: page/1', 'max_tokens'), succeeded('x', 'pause_turn'),
    SimpleNamespace(type='expired'), SimpleNamespace(type='canceled'),
], ids=['refused', 'no_page', 'blocked', 'errored_invalid', 'errored_overloaded', 'truncated', 'unexpected', 'expired', 'canceled'])
def test_a_retry_never_re_sends_a_page_that_is_not_malformed(world, outcome):
    run('submit', '--cells', 'MP-HM')
    finish(world, lambda entry: outcome)
    assert 'malformed' not in {record['result_class'] for record in world.free.readings()}
    run('submit', '--cells', 'MP-HM', '--retry-malformed')
    assert len(sent(world)) == 2
    assert plan(retry_malformed=True)[0] == []


def test_a_retry_leaves_a_good_page_and_an_unread_page_alone(world):
    run('submit', '--cells', 'MP-HM')
    finish(world)
    entries, skipped = plan(retry_malformed=True)
    assert entries == [] and skipped == {'not malformed (ok)': 2}
    entries, skipped = plan('MP-SM', retry_malformed=True)
    assert entries == [] and skipped == {'not malformed (not read)': 2}


def test_a_retry_counts_against_the_cap_and_an_open_batch(world):
    run('submit', '--cells', 'MP-SM')
    finish(world, lambda entry: succeeded(answer_of(entry, 'sidebar')))
    with pytest.raises(SystemExit, match='refused'):
        run('submit', '--cells', 'MP-SM', '--retry-malformed', '--cap', '0.001')
    assert len(sent(world)) == 2
    run('submit', '--cells', 'MP-SM', '--retry-malformed')
    run('submit', '--cells', 'MP-SM', '--retry-malformed')
    assert len(sent(world)) == 4


@pytest.mark.parametrize('outcome', [succeeded('', 'refusal'), errored()], ids=['refused', 'blocked'])
def test_a_page_blocked_in_one_cell_goes_to_no_second_model(world, outcome):
    run('submit', '--cells', 'MP-HM')
    finish(world, lambda entry: outcome if entry['pdf_page'] == 1 else succeeded(answer_of(entry)))
    entries, skipped = plan('MP-SM')
    assert [entry['pdf_page'] for entry in entries] == [2] and skipped == {'blocked before': 1}


def test_a_malformed_page_blocked_in_another_cell_is_not_retried(world):
    run('submit', '--cells', 'MP-HM')
    finish(world, malformed_on_first_page)
    run('submit', '--cells', 'MP-SM')
    finish(world, lambda entry: errored() if entry['pdf_page'] == 1 else succeeded(answer_of(entry)))
    entries, skipped = plan('MP-HM', retry_malformed=True)
    assert entries == [] and skipped['blocked before'] == 1


@pytest.mark.parametrize('record, blocked', [
    ({'result_class': 'refused'}, True),
    ({'result_class': 'errored', 'error_type': 'invalid_request_error', 'error_message': BLOCKED}, True),
    ({'result_class': 'errored', 'error_type': 'invalid_request_error'}, True),  # as the pilot stored it, without the message
    ({'result_class': 'errored', 'error_type': 'invalid_request_error', 'error_message': 'max_tokens: too large'}, False),
    ({'result_class': 'errored', 'error_type': 'overloaded_error', 'error_message': 'Overloaded'}, False),
    ({'result_class': 'truncated'}, False),
    ({'result_class': 'no_page'}, False),
    ({'result_class': 'malformed'}, False),
    ({'result_class': 'ok'}, False),
])
def test_what_counts_as_a_block(record, blocked):
    assert vision_batches.is_block(record) is blocked


def test_a_block_of_the_old_pilot_holds_too(world):
    world.free.save_reading('ab' * 32, {'result_class': 'errored', 'error_type': 'invalid_request_error', 'file': 'public.pdf', 'pdf_page': 2,
                                        'form': 'image', 'model': 'claude-sonnet-5-5'}, None)
    entries, skipped = plan('MP-HM')
    assert [entry['pdf_page'] for entry in entries] == [1] and skipped == {'blocked before': 1}


# ---------------------------------------------------------------- collect

def test_collect_stores_the_message_of_an_errored_result_cut_to_200_characters(world, capsys):
    long_message = BLOCKED + ' ' + 'x' * 500
    run('submit', '--cells', 'MP-HM')
    finish(world, lambda entry: errored(long_message))
    record = world.free.readings()[0]
    assert record['result_class'] == 'errored' and record['error_type'] == 'invalid_request_error'
    assert record['error_message'] == long_message[:200] and len(record['error_message']) == 200 and record['cost_usd'] == 0.0
    assert BLOCKED not in capsys.readouterr().out


def test_the_console_of_a_collect_holds_classes_and_costs_only(world, capsys):
    run('submit', '--cells', 'MP-HM')
    finish(world, lambda entry: errored() if entry['pdf_page'] == 1 else succeeded(answer_of(entry)))
    out = capsys.readouterr().out
    assert "{'errored': 1, 'ok': 1}" in out and 'USD' in out
    assert PAGE_TEXT not in out and BLOCKED not in out


def test_collect_writes_text_record_and_ledger_for_every_result(world):
    run('submit', '--cells', 'MP-HJ')
    finish(world)
    keys = {entry['reading_key'] for entry in world.licensed.manifests()[0]['requests']}
    assert {row['reading_key'] for row in world.free.ledger()} == keys
    for key in keys:
        assert world.free.reading(key)['result_class'] == 'ok'
        assert PAGE_TEXT in world.free.path('readings', key[:2], key + '.md').read_text(encoding='utf-8')
    manifest = world.licensed.manifests()[0]
    assert manifest['status'] == 'collected' and manifest['classes'] == {'ok': 2} and manifest['missing'] == [] and manifest['cost_usd'] > 0


def test_collect_twice_changes_nothing(world):
    run('submit', '--cells', 'MP-HM')
    finish(world)
    before = world.free.ledger(), world.licensed.manifests()
    run('collect')
    assert (world.free.ledger(), world.licensed.manifests()) == before


def test_a_collect_that_died_half_way_counts_nothing_twice(world):
    run('submit', '--cells', 'MP-HM')
    manifest = world.licensed.manifests()[0]
    first, second = manifest['requests']
    world.batches.results_by_batch['msgbatch_0'] = [(first['custom_id'], succeeded(answer_of(first))), (second['custom_id'], ConnectionError('gone'))]
    with pytest.raises(ConnectionError):
        run('collect')
    stored_at = world.free.reading(first['reading_key'])['stored_at']
    assert world.licensed.manifests()[0]['status'] == 'submitted'
    finish(world)
    assert sorted(row['reading_key'] for row in world.free.ledger()) == sorted([first['reading_key'], second['reading_key']])
    assert world.free.reading(first['reading_key'])['stored_at'] == stored_at
    assert world.licensed.manifests()[0]['status'] == 'collected'


def test_a_cost_is_in_the_ledger_before_the_record_that_stops_a_second_pass(world, monkeypatch):
    run('submit', '--cells', 'MP-HM')
    monkeypatch.setattr(reading_store.Store, 'save_reading', lambda *args: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError):
        finish(world)
    assert len(world.free.ledger()) == 1


def test_collect_reads_the_shapes_of_the_sdks_own_models(world):
    # The fakes above could lie about the SDK; here the results are built by its own response types (anthropic 2.3.0).
    run('submit', '--cells', 'MP-HM')
    first, second = world.licensed.manifests()[0]['requests']
    message = {'id': 'msg_1', 'type': 'message', 'role': 'assistant', 'model': 'claude-haiku-5-5-20261001', 'stop_reason': 'end_turn', 'stop_sequence': None,
               'stop_details': {'type': 'refusal', 'category': None, 'explanation': None},
               'content': [{'type': 'thinking', 'thinking': 'hm', 'signature': 'x'}, {'type': 'text', 'text': answer_of(first), 'citations': None}],
               'usage': {'input_tokens': 4900, 'output_tokens': 1000, 'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 4500}}
    results = [MessageBatchIndividualResponse.construct(custom_id=first['custom_id'], result={'type': 'succeeded', 'message': message}),
               MessageBatchIndividualResponse.construct(custom_id=second['custom_id'], result={
                   'type': 'errored', 'error': {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': BLOCKED}}})]
    world.batches.results = lambda batch_id: iter(results)
    run('collect')
    good, blocked = world.free.reading(first['reading_key']), world.free.reading(second['reading_key'])
    assert good['result_class'] == 'ok' and good['usage']['cache_read_input_tokens'] == 4500 and good['stop_details']['type'] == 'refusal'
    assert blocked['result_class'] == 'errored' and blocked['error_type'] == 'invalid_request_error' and blocked['error_message'] == BLOCKED


def test_a_batch_still_running_stays_open(world, capsys):
    run('submit', '--cells', 'MP-HM')
    world.batches.processing_status = 'in_progress'
    run('collect')
    assert world.licensed.manifests()[0]['status'] == 'submitted' and 'in_progress' in capsys.readouterr().out


def test_delete_removes_a_fully_stored_batch_and_only_that(world):
    run('submit', '--cells', 'MP-HM')
    first, second = world.licensed.manifests()[0]['requests']
    world.batches.results_by_batch['msgbatch_0'] = [(first['custom_id'], succeeded(answer_of(first)))]
    run('collect', '--delete')
    manifest = world.licensed.manifests()[0]
    assert manifest['status'] == 'collected' and manifest['missing'] == [second['custom_id']] and world.batches.deleted == []
    run('collect', '--delete')
    assert world.batches.deleted == []


def test_delete_after_a_clean_collect(world):
    run('submit', '--cells', 'MP-HM')
    for manifest in world.licensed.manifests():
        world.batches.results_by_batch[manifest['batch_id']] = [(entry['custom_id'], succeeded(answer_of(entry))) for entry in manifest['requests']]
    run('collect', '--delete')
    assert world.batches.deleted == ['msgbatch_0'] and world.licensed.manifests()[0]['status'] == 'deleted'


# ---------------------------------------------------------------- manifests of the old contract

def test_status_reads_old_manifests(world, capsys):
    world.licensed.save_manifest(old_manifest('collected', [old_entry()], classes={'ok': 1}, cost_usd=0.2, missing=[]))
    run('status')
    out = capsys.readouterr().out
    assert 'msgbatch_old_collected' in out and "{'ok': 1}" in out and 'spent 0.0000' in out


def test_collect_delete_works_on_an_old_manifest(world, capsys):
    world.licensed.save_manifest(old_manifest('collected', [old_entry()], classes={'ok': 1}, cost_usd=0.2, missing=[]))
    run('collect', '--delete')
    assert world.batches.deleted == ['msgbatch_old_collected'] and world.licensed.manifests()[0]['status'] == 'deleted'
    assert 'deleted at Anthropic' in capsys.readouterr().out
    run('collect', '--delete')
    assert world.batches.deleted == ['msgbatch_old_collected']


def test_a_batch_already_gone_at_anthropic_is_marked_and_stops_nothing(world):
    world.licensed.save_manifest(old_manifest('collected', [old_entry()], missing=[]))
    world.batches.gone = {'msgbatch_old_collected'}
    run('collect', '--delete')
    manifest = world.licensed.manifests()[0]
    assert manifest['status'] == 'deleted' and manifest['gone_at_anthropic'] is True


@pytest.mark.parametrize('entry', [old_entry(), old_entry(form=None)], ids=['form image', 'no form'])
def test_a_result_of_an_old_entry_is_kept_unchecked_and_crashes_nothing(world, entry):
    world.licensed.save_manifest(old_manifest('submitted', [entry]))
    world.batches.results_by_batch['msgbatch_old_submitted'] = [(entry['custom_id'], succeeded('<page>text of the old contract</page>'))]
    run('collect')
    record = world.free.reading(entry['reading_key'])
    assert record['result_class'] == 'unchecked' and record['contract'] is None and record['kind'] == 'reading'
    assert record['work'] is None and world.licensed.manifests()[0]['status'] == 'collected'


@pytest.mark.parametrize('outcome, expected', [
    (succeeded('', 'refusal'), 'refused'), (succeeded('<page>', 'max_tokens'), 'truncated'), (errored(), 'errored'), (SimpleNamespace(type='expired'), 'expired'),
])
def test_other_results_of_an_old_entry_keep_their_class(world, outcome, expected):
    entry = old_entry(form=None)
    world.licensed.save_manifest(old_manifest('submitted', [entry]))
    world.batches.results_by_batch['msgbatch_old_submitted'] = [(entry['custom_id'], outcome)]
    run('collect')
    assert world.free.reading(entry['reading_key'])['result_class'] == expected


def test_an_old_open_batch_still_counts_in_the_guard(world):
    world.licensed.save_manifest(old_manifest('submitted', [old_entry()]))
    status = vision_batches.spend_status(world.client)
    assert status['open_estimate_usd'] == 0.25 and status['unknown_running_batches'] == []


def test_an_old_running_batch_is_known_to_the_guard(world):
    world.licensed.save_manifest(old_manifest('submitted', [old_entry()]))
    world.batches.running = ['msgbatch_old_submitted']
    assert vision_batches.spend_status(world.client)['unknown_running_batches'] == []


# ---------------------------------------------------------------- free checks

def test_free_checks_count_both_forms_with_the_real_parameters_and_buy_nothing(world, capsys):
    run('free-checks')
    messages = world.client.messages
    assert messages.streamed == [] and world.batches.created == [] and world.free.ledger() == []
    models = {call['model'] for call in messages.counted}
    assert models == {'claude-haiku-5-5', 'claude-sonnet-5-5'}
    assert all('max_tokens' not in call for call in messages.counted)
    with_image = [call for call in messages.counted if not isinstance(call['messages'][0]['content'], str)]
    assert all(call['messages'][0]['content'][0]['transformations'] == {'oversized_image': 'error'} for call in with_image)
    schemas = [call['output_config'] for call in with_image if 'format' in call['output_config']]
    assert len(schemas) >= 2 and all(config['format']['schema'] == page_contract.json_schema() and 'effort' in config for config in schemas)
    assert {call['thinking']['type'] for call in with_image} == {'disabled', 'between_tools'}
    out = capsys.readouterr().out
    assert 'markdown' in out and 'json' in out and 'written to' in out


def test_free_checks_report_what_each_part_costs(world):
    run('free-checks')
    report = json.loads(next(world.free.path('reports', 'x').parent.glob('free_checks_*.json')).read_text(encoding='utf-8'))
    rows = {(row['model'], row['form']): row for row in report['counts']}
    assert len(rows) == 4 and set(report['models']) == {'claude-haiku-5-5', 'claude-sonnet-5-5'}
    row = rows['claude-sonnet-5-5', 'json']
    assert row['image_tokens'] == 4761 and row['schema_tokens'] == 700 and row['patches'] == 4758 and row['size'] == [1688, 2184]
    assert row['estimated_text_tokens'] == reader_requests.SYSTEM_PROMPT_TOKENS['json'] + reader_requests.JSON_SCHEMA_TOKENS + reader_requests.USER_TURN_TOKENS
    assert 'schema_tokens' not in rows['claude-sonnet-5-5', 'markdown']


def test_free_checks_refuse_a_licensed_page(world):
    write_pages(world.source, 'private.pdf', (1, 2))
    with pytest.raises(SystemExit, match='public pages only'):
        run('free-checks')
    assert world.client.messages.counted == []


# ---------------------------------------------------------------- the smoke test

def test_the_real_smoke_plan_covers_each_cell_once_and_stays_under_its_cap():
    cells = reading_cells.CELLS
    assert sorted(name for name, _ in vision_batches.SMOKE_PLAN) == sorted(cells)
    total = 0.0
    for name, page_id in vision_batches.SMOKE_PLAN:
        page = next(item for item in reading_cells.pages_for(cells[name]) if item['id'] == page_id)
        total += reader_requests.estimate_usd(cells[name].model, page_render.patches(1688, 2184), page['expected_output_tokens'], cells[name].form, batch=False)
    assert total < vision_batches.SMOKE_CAP_USD == 0.10
    assert any(page['id'] == vision_batches.FREE_CHECK_PAGE for page in reading_cells.pages_for(cells['MP-HM']))


def test_the_smoke_test_reads_once_per_cell_stores_first_and_prints_its_controls(world, capsys):
    run('smoke')
    streamed = world.client.messages.streamed
    assert len(streamed) == 4 and len(world.free.readings()) == 4 and len(world.free.ledger()) == 4
    assert sorted((params['model'], 'format' in params['output_config']) for params in streamed) == [
        ('claude-haiku-5-5', False), ('claude-haiku-5-5', True), ('claude-sonnet-5-5', False), ('claude-sonnet-5-5', True)]
    assert all(params['messages'][0]['content'][0]['transformations'] == {'oversized_image': 'error'} for params in streamed)
    for record in world.free.readings():
        assert record['cell'] == 'SMOKE' and record['mode'] == 'standard' and record['result_class'] == 'ok' and record['seconds'] is not None
    out = capsys.readouterr().out
    for name in reading_cells.CELLS:
        assert name in out
    assert 'model_ok=True' in out and 'image_ok=True' in out and 'thinking=' in out and 'cache w/r=' in out and 'written to' in out
    assert PAGE_TEXT not in out
    assert next(world.free.path('reports', 'x').parent.glob('smoke_*.json')).exists()


def test_the_smoke_test_is_billed_at_the_standard_price(world):
    run('smoke')
    haiku = next(record for record in world.free.readings() if record['model'] == 'claude-haiku-5-5')
    assert haiku['cost_usd'] == pytest.approx(anthropic_client.cost_usd('claude-haiku-5-5', 4900, 1000, batch=False, cache_read_tokens=4500))


def test_a_second_smoke_run_buys_nothing_and_shows_the_stored_controls(world, capsys):
    run('smoke')
    capsys.readouterr()
    run('smoke')
    out = capsys.readouterr().out
    assert len(world.client.messages.streamed) == 4 and len(world.free.ledger()) == 4
    assert out.count('(stored before)') == 4 and 'total 0.0000 USD' in out


def test_the_smoke_test_refuses_a_licensed_page(world):
    write_pages(world.source, 'private.pdf', (1, 2))
    with pytest.raises(SystemExit, match='public pages only'):
        run('smoke')
    assert world.client.messages.streamed == []


def test_the_smoke_test_refuses_an_estimate_above_its_cap(world, monkeypatch):
    monkeypatch.setattr(vision_batches, 'SMOKE_CAP_USD', 0.0001)
    with pytest.raises(SystemExit, match='above its cap'):
        run('smoke')
    assert world.client.messages.streamed == []


def test_the_smoke_test_stops_at_an_unknown_running_batch(world):
    world.batches.running = ['msgbatch_nobody_knows']
    with pytest.raises(SystemExit, match='no manifest knows'):
        run('smoke')
    assert world.client.messages.streamed == []


def test_a_block_in_the_smoke_test_is_stored_and_never_read_again(world, capsys):
    world.client.messages.stream_answer = lambda params: bad_request(BLOCKED)
    run('smoke')
    assert len(world.client.messages.streamed) == 4
    record = world.free.readings()[0]
    assert record['result_class'] == 'errored' and record['error_type'] == 'invalid_request_error' and record['error_message'] == BLOCKED
    assert vision_batches.is_block(record)
    run('smoke')
    assert len(world.client.messages.streamed) == 4


def test_a_rejected_request_is_not_remembered_so_a_fixed_one_can_go(world):
    world.client.messages.stream_answer = lambda params: bad_request('output_config.format: invalid schema')
    with pytest.raises(SystemExit, match='nothing stored'):
        run('smoke')
    assert world.free.readings() == [] and world.free.ledger() == []
    world.client.messages.stream_answer = None
    run('smoke')
    assert len(world.free.readings()) == 4


# ---------------------------------------------------------------- the command line

def test_the_command_line_has_the_commands_the_docstring_names():
    parser = vision_batches.build_parser()
    args = parser.parse_args(['submit', '--cells', 'MP-HM,MP-HJ', '--cap', '2', '--dry-run', '--retry-malformed'])
    assert (args.cells, args.cap, args.dry_run, args.retry_malformed, args.run) == ('MP-HM,MP-HJ', 2.0, True, True, vision_batches.submit)
    assert not parser.parse_args(['submit', '--cells', 'X']).retry_malformed
    assert parser.parse_args(['collect', '--delete']).delete and parser.parse_args(['collect']).run == vision_batches.collect
    assert parser.parse_args(['status']).run == vision_batches.status
    assert parser.parse_args(['free-checks']).run == vision_batches.free_checks and parser.parse_args(['smoke']).run == vision_batches.smoke
    for command in ('free-checks', 'smoke', 'submit --cells', 'collect', 'status'):
        assert f'python -m backend.conversion.reading.vision_batches {command}' in vision_batches.__doc__


def test_the_old_contract_is_gone_from_the_code():
    for name in ('reader_requests.py', 'vision_batches.py', 'reading_cells.py'):
        text = (CONVERSION / 'reading' / name).read_text(encoding='utf-8')
        assert 'reader_prompt_v1_1' not in text and 'pilot_cells' not in text and 'page_contract.check' not in text
    assert not list(CONVERSION.glob('**/pilot_cells.py'))


def test_a_cell_s_readings_are_found_by_what_their_keys_hold_not_by_the_cell_label(world, monkeypatch):
    run('submit', '--cells', 'MP-HM')
    finish(world)
    twin = dataclasses.replace(reading_cells.CELLS['MP-HM'], name='TWIN')  # the same question under another name
    monkeypatch.setattr(reading_cells, 'CELLS', {**reading_cells.CELLS, 'TWIN': twin})
    found = vision_batches.readings_of(['TWIN'], world.free)
    assert sorted(record['pdf_page'] for record in found) == [1, 2] and {record['cell'] for record in found} == {'MP-HM'}
    assert vision_batches.readings_of(['MP-HJ'], world.free) == []  # another form is another question


@pytest.mark.parametrize('text, expected', [
    ("I can't transcribe this page word for word, as it is copyrighted material. I could summarise it instead.", 'refused'),
    ('I am not able to provide a verbatim copy of this page.', 'refused'),
    ('Here is the page.\n\nIt has two paragraphs about risk.', 'no_page'),
])
def test_an_answer_without_a_page_file_that_declines_the_page_is_refused(text, expected):
    entry = {'form': 'markdown', 'work': 'w', 'pdf_page': 1, 'image_size': [1688, 2184]}
    assert vision_batches.check_reading(entry, text, 'end_turn')[0] == expected


def test_a_page_file_that_mentions_copyright_stays_a_page(world):
    entry = {'form': 'markdown', 'work': 'public-work', 'pdf_page': 1, 'image_size': [1688, 2184]}
    text = page_text().replace(PAGE_TEXT, 'Copyright 2019. We cannot reproduce the verbatim table here.')
    assert 'Copyright' in text and vision_batches.check_reading(entry, text, 'end_turn')[0] == 'ok'


def judged_issues(world, monkeypatch, findings_by_page: dict) -> dict:
    """Both pages read; the judge's verdict per page as given, by pdf page: [finding, ...] or None for no issue."""
    from backend.conversion.store import reading_export

    run('submit', '--cells', 'MP-HM')
    finish(world)
    keys = {record['pdf_page']: record['reading_key'] for record in world.free.readings() if record.get('kind', 'reading') == 'reading'}
    states = {keys[page]: {'state': 'issue', 'verdict': {'findings': findings}} for page, findings in findings_by_page.items() if findings}
    monkeypatch.setattr(reading_export, 'check_states', lambda store, cells: states)
    return keys


def test_a_page_the_judge_found_bad_on_a_quoted_block_is_read_again_told_the_findings(world, monkeypatch):
    keys = judged_issues(world, monkeypatch, {1: [{'block': 'b01', 'kind': 'wrong_value', 'evidence': 'printed 6,000, written 4,000'}],
                                             2: None})
    entries, skipped = plan(retry_issues=True)
    assert [(entry['pdf_page'], entry['attempt'], entry['retry_of']) for entry in entries] == [(1, 1, keys[1])]
    assert skipped == {'no issue of the judge': 1}
    told = world.free.get_prompt(entries[0]['user_sha256'])
    assert 'b01, a wrong value: printed 6,000, written 4,000' in told and told.endswith('keep everything else as it is.')


def test_a_finding_only_on_a_block_never_quoted_reads_nothing_again(world, monkeypatch):
    from backend.conversion.store import served_readings

    monkeypatch.setattr(served_readings, 'NOT_QUOTED', served_readings.NOT_QUOTED | {'paragraph'})  # b01 counts as never quoted
    judged_issues(world, monkeypatch, {1: [{'block': 'b01', 'kind': 'invented', 'evidence': 'a description'}], 2: None})
    entries, skipped = plan(retry_issues=True)
    assert entries == [] and skipped['findings on blocks never quoted'] == 1


def test_a_re_read_is_bought_once_and_never_re_read_after_its_own_issue(world, monkeypatch):
    judged_issues(world, monkeypatch, {1: [{'block': None, 'kind': 'omission', 'evidence': 'a line'}], 2: None})
    run('submit', '--cells', 'MP-HM', '--retry-issues')
    finish(world)
    retried = next(record for record in world.free.readings() if record.get('retry_of'))
    assert retried['attempt'] == 1 and retried['pdf_page'] == 1
    from backend.conversion.store import reading_export
    monkeypatch.setattr(reading_export, 'check_states', lambda store, cells: {retried['reading_key']: {
        'state': 'issue', 'verdict': {'findings': [{'block': 'b01', 'kind': 'wrong_word', 'evidence': 'x'}]}}})
    entries, skipped = plan(retry_issues=True)
    assert entries == [] and skipped['re-read after an issue before'] == 1


def test_a_reading_is_checked_once_per_run_and_each_caller_gets_its_own_copy(monkeypatch):
    # decision 214.a: the validator cannot change within a process and a reading's text is its key's; the same text and
    # page give the same answer without a second parse, and a changed text is checked again
    from backend.conversion.contract import page_contract

    calls = []
    real = page_contract.parse
    monkeypatch.setattr(page_contract, 'parse', lambda *args, **kwargs: calls.append(1) or real(*args, **kwargs))
    monkeypatch.setattr(vision_batches, '_CHECKED', {})
    entry = {'form': 'markdown', 'work': 'w', 'pdf_page': 3, 'image_size': [1688, 2184]}
    first = vision_batches.check_reading(entry, 'not a page file', 'end_turn')
    first[1]['blocks'] = 'changed by a caller' if first[1] else None
    second = vision_batches.check_reading(entry, 'not a page file', 'end_turn')
    assert len(calls) == 1 and second[0] == first[0] and (second[1] or {}).get('blocks') != 'changed by a caller'
    vision_batches.check_reading(entry, 'another text', 'end_turn')
    assert len(calls) == 2
