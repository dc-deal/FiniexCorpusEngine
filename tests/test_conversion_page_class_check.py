import json

import pytest

from backend.conversion.reading import page_class_check, vision_batches


@pytest.mark.parametrize('text, expected', [
    (json.dumps({'classes': []}), ('ok', {'classes': []})),
    (json.dumps({'classes': ['table', 'formula', 'table']}), ('ok', {'classes': ['formula', 'table']})),
    (json.dumps({'classes': ['table', 'poem']}), ('ok', {'classes': ['table']})),
    ('not json', ('malformed', None)),
    (json.dumps({'kinds': []}), ('malformed', None)),
])
def test_an_answer_keeps_only_known_kinds(text, expected):
    assert page_class_check.check_answer({}, text, 'end_turn') == expected


def test_a_cut_or_refused_answer_is_not_a_verdict():
    assert page_class_check.check_answer({}, '{"classes": [', 'max_tokens') == ('truncated', None)
    assert page_class_check.check_answer({}, '', 'refusal') == ('refused', None)


def test_the_request_asks_for_classes_only_through_the_schema_and_caches_the_prompt():
    params = page_class_check.message_params(model=page_class_check.MODEL, system_text='The prompt.', page_png=b'png', pdf_page=3)
    assert params['output_config']['format'] == {'type': 'json_schema', 'schema': page_class_check.SCHEMA}
    assert params['system'][0]['cache_control'] == {'type': 'ephemeral'} and params['max_tokens'] == page_class_check.MAX_TOKENS
    assert [part['type'] for part in params['messages'][0]['content']] == ['text', 'image']


def test_a_changed_prompt_or_image_is_a_new_question():
    base = dict(file_name='a.pdf', pdf_page=1, model=page_class_check.MODEL, system_sha='s1', image_sha='i1')
    key = page_class_check.check_key(**base)
    assert key == page_class_check.check_key(**base)
    assert key != page_class_check.check_key(**{**base, 'system_sha': 's2'}) != page_class_check.check_key(**{**base, 'image_sha': 'i2'})


def test_the_runner_knows_the_kind_and_keeps_its_answer_field():
    kind = vision_batches.KINDS['classcheck']
    assert kind.record_field == 'answer' and kind.check is page_class_check.check_answer
    assert vision_batches.kind_of({'kind': 'classcheck'}) is kind
