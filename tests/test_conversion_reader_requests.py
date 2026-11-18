import base64
import copy
import re

import pytest

from backend.conversion.contract import page_contract
from backend.conversion.reading import page_render, reader_requests, reading_cells

SPEC = dict(image_sha='a' * 64, model='claude-haiku-5-5', system_sha='b' * 64, user_sha='c' * 64, form='markdown', max_tokens=16000,
            replicate=0, attempt=0, mode='batch')
USER = dict(work='openstax-finance-2e', pdf_page=179, image_size=(1688, 2184), work_card='A card.')


def key_of(**changes) -> str:
    return reader_requests.reading_key(reader_requests.reading_spec(**{**SPEC, **changes}))


def params(model='claude-haiku-5-5', form='markdown') -> dict:
    return reader_requests.message_params(model=model, form=form, system_text='the rules', user_text='the turn', png=b'\x89PNG')


def test_the_same_question_has_the_same_key():
    assert key_of() == key_of()


@pytest.mark.parametrize('change', [
    {'image_sha': 'd' * 64}, {'system_sha': 'd' * 64}, {'user_sha': 'd' * 64}, {'model': 'claude-sonnet-5-5'}, {'form': 'json'},
    {'max_tokens': 8000}, {'replicate': 1}, {'attempt': 1}, {'mode': 'standard'},
])
def test_anything_asked_differently_has_a_new_key(change):
    assert key_of(**change) != key_of()


def test_a_changed_prompt_or_card_changes_the_key_through_its_hash():
    other_card = reader_requests.user_turn(**{**USER, 'work_card': 'Another card.'})
    assert key_of(user_sha=reader_requests.sha256_text(other_card)) != key_of(user_sha=reader_requests.sha256_text(reader_requests.user_turn(**USER)))
    assert key_of(system_sha=reader_requests.sha256_text(reader_requests.system_prompt('json'))) != key_of(
        system_sha=reader_requests.sha256_text(reader_requests.system_prompt('markdown')))


def test_a_changed_schema_changes_the_key_of_form_json_only(monkeypatch):
    before = key_of(form='json'), key_of(form='markdown')
    monkeypatch.setattr(page_contract, 'json_schema', lambda: {'type': 'object', 'changed': True})
    assert key_of(form='json') != before[0]
    assert key_of(form='markdown') == before[1]


def test_the_custom_id_fits_the_api_format():
    assert re.fullmatch(r'[A-Za-z0-9_-]{1,64}', reader_requests.custom_id(key_of()))


@pytest.mark.parametrize('form', page_contract.FORMS)
def test_the_system_prompt_is_the_rules_and_then_the_format_of_the_form(form):
    prompt = reader_requests.system_prompt(form)
    rules = reader_requests.RULES_PROMPT.read_bytes().decode('utf-8')
    assert prompt.startswith(rules) and prompt[len(rules):].lstrip().startswith('OUTPUT FORMAT')
    assert '\r' not in prompt


def test_each_form_has_its_own_output_format():
    assert 'YAML front matter' in reader_requests.system_prompt('markdown')
    assert 'one JSON object' in reader_requests.system_prompt('json')
    with pytest.raises(ValueError, match='unknown form'):
        reader_requests.system_prompt('image')


def test_the_user_turn_gives_the_page_then_the_card_then_asks_to_read():
    turn = reader_requests.user_turn(**USER)
    assert turn.splitlines()[:3] == ['work: openstax-finance-2e', 'pdf_page: 179', 'image_size: 1688x2184']
    assert turn.index('image_size') < turn.index('A card.') < turn.index('Read this page')


def test_the_image_size_in_the_turn_is_the_form_the_contract_checks():
    size = re.search(r'image_size: (\S+)', reader_requests.user_turn(**USER)).group(1)
    assert page_contract.IMAGE_SIZE.match(size)


@pytest.mark.parametrize('model', sorted(reader_requests.MODEL_SETTINGS))
@pytest.mark.parametrize('form', page_contract.FORMS)
def test_no_sampling_parameter_is_ever_sent_and_the_system_prompt_is_cached(model, form):
    sent = params(model, form)
    assert not {'temperature', 'top_p', 'top_k'} & set(sent)  # API version 2026-10-21 rejects them
    assert sent['system'] == [{'type': 'text', 'text': 'the rules', 'cache_control': {'type': 'ephemeral'}}]
    assert sent['max_tokens'] == reader_requests.MAX_TOKENS and sent['model'] == model


def test_the_image_goes_first_and_refuses_a_silent_downscale():
    image, text = params()['messages'][0]['content']
    assert image['type'] == 'image' and text == {'type': 'text', 'text': 'the turn'}
    assert base64.standard_b64decode(image['source']['data']) == b'\x89PNG'
    # On the block, measured 2026-10-30: inside the source the API rejects it.
    assert image['transformations'] == {'oversized_image': 'error'} and 'transformations' not in image['source']


def test_thinking_is_set_the_way_each_model_accepts():
    assert reader_requests.MODEL_SETTINGS['claude-haiku-5-5']['thinking'] == {'type': 'disabled'}
    assert reader_requests.MODEL_SETTINGS['claude-sonnet-5-5']['thinking'] == {'type': 'between_tools'}
    assert 'thinking' not in reader_requests.MODEL_SETTINGS['claude-opus-5-5']  # cannot be switched off
    assert params('claude-sonnet-5-5')['thinking'] == {'type': 'between_tools'} and 'thinking' not in params('claude-opus-5-5')


@pytest.mark.parametrize('model, effort', [('claude-haiku-5-5', 'high'), ('claude-sonnet-5-5', 'high'), ('claude-opus-5-5', 'low')])
def test_form_json_merges_the_schema_with_the_effort_of_the_model(model, effort):
    assert params(model, 'json')['output_config'] == {'effort': effort, 'format': {'type': 'json_schema', 'schema': page_contract.json_schema()}}
    assert params(model, 'markdown')['output_config'] == {'effort': effort}


def test_building_a_json_request_leaves_the_model_settings_alone():
    before = copy.deepcopy(reader_requests.MODEL_SETTINGS)
    params(form='json')['output_config']['effort'] = 'changed'
    assert reader_requests.MODEL_SETTINGS == before


@pytest.mark.parametrize('form', page_contract.FORMS)
def test_the_token_constants_follow_the_prompts_they_stand_for(form):
    # A drift alarm, not a count: 1745 API tokens on the old prompt's characters give about 0.39 tokens a character.
    assert reader_requests.SYSTEM_PROMPT_TOKENS[form] == pytest.approx(len(reader_requests.system_prompt(form)) * 0.39, rel=0.25)


def test_an_answer_in_json_is_estimated_dearer_and_a_batch_cheaper():
    markdown = reader_requests.estimate_usd('claude-sonnet-5-5', 4758, 1800, 'markdown')
    assert reader_requests.estimate_usd('claude-sonnet-5-5', 4758, 1800, 'json') > markdown
    assert reader_requests.estimate_usd('claude-sonnet-5-5', 4758, 1800, 'markdown', batch=False) > markdown


def test_a_batch_estimate_counts_the_cache_as_the_pilot_measured_it():
    # 405 of 414 requests read the cached prompt, so nearly all of it is billed at 0.1 x.
    with_cache = reader_requests.estimate_usd('claude-haiku-5-5', 0, 0, 'markdown')
    without_output = (reader_requests.IMAGE_TOKEN_OVERHEAD + reader_requests.USER_TURN_TOKENS) * 0.05e-6
    prompt = reader_requests.SYSTEM_PROMPT_TOKENS['markdown']
    assert with_cache - without_output == pytest.approx(prompt * 0.05e-6 * (405 / 414 * 0.1 + 9 / 414 * 1.25))


def test_the_mini_pilot_is_estimated_within_its_budget():
    # Decision OC-1.a: at most 1 USD for the readings. At the size of a US Letter page, whose image is the largest of the list.
    total = sum(reader_requests.estimate_usd(cell.model, page_render.patches(1688, 2184), page['expected_output_tokens'], cell.form)
                for cell in reading_cells.CELLS.values() for page in reading_cells.pages_for(cell))
    assert 0.3 < total < 1.0


def test_page1_reads_as_it_always_did_and_page2_is_page1_plus_its_rules():
    # decision 207.a: a reader version beside page/1; page/1's bytes, and with them every key made before, stay the same
    rules_1 = (reader_requests.PROMPTS / 'reader_page1_rules.txt').read_text(encoding='utf-8')
    rules_2 = (reader_requests.PROMPTS / 'reader_page2_rules.txt').read_text(encoding='utf-8')
    markdown = (reader_requests.PROMPTS / 'reader_page1_markdown.txt').read_text(encoding='utf-8')
    assert reader_requests.system_prompt('markdown') == rules_1 + markdown
    assert reader_requests.system_prompt('markdown', 'page/2') == rules_2 + markdown
    assert rules_2.startswith(rules_1) and 'MORE BODY RULES' in rules_2[len(rules_1):]  # an addition, nothing of page/1 changed
    rules_3 = (reader_requests.PROMPTS / 'reader_page3_rules.txt').read_text(encoding='utf-8')
    assert reader_requests.system_prompt('markdown', 'page/3') == rules_3 + markdown
    anchor = 'Inside math a dollar sign is \\$.'  # F4.a: page/3 is page/1 with one sentence after it, nothing else
    assert rules_3 == rules_1.replace(anchor, anchor + ' A backslash the page prints as text, not as part of a formula, is '
                                      'written &#92; (rate&#92;term); inside math it is \\backslash.', 1)
    with pytest.raises(ValueError):
        reader_requests.system_prompt('json', 'page/2')
    with pytest.raises(ValueError):
        reader_requests.system_prompt('markdown', 'page/9')
