"""A proposed correction of one block (the operator's W2.a, 21 Nov 2026): asked once, kept, never for a page turned away."""

import json

import pytest

from backend.conversion.judge import correction_proposal, session_judge
from backend.conversion.reading import reading_cells
from backend.conversion.store import reading_store
from test_conversion_served_readings import page

READING = page('::: {#b01 .paragraph bbox="10 10 200 50"}\nThe rate rose to 4.5% in the second year and stayed there to the end.\n:::',
               '::: {#b02 .figure kind=chart bbox="10 60 200 90"}\nYear\n:::',
               '::: {#b03 .description of=b02 form=prose}\nBlue bars shrink steadily from left to right.\n:::')
FINDING = {'kind': 'wrong_value', 'severity': 'major', 'evidence': 'printed 4.6%, written 4.5%'}


class Message:
    """What the API answers, as far as `propose` reads it."""

    stop_reason = 'end_turn'

    def __init__(self, answer: dict):
        self.content = [type('Block', (), {'type': 'text', 'text': json.dumps(answer)})()]
        self.usage = type('Usage', (), {'to_dict': lambda self: {'input_tokens': 5000, 'output_tokens': 300}})()


@pytest.fixture
def a_reading(tmp_path, monkeypatch):
    store = reading_store.Store(tmp_path / 'vision')
    image = store.put_input(b'the page image', '.png')
    store.save_reading('r' * 64, {'file': 'book.pdf', 'pdf_page': 7, 'image_sha256': image, 'image_size': [1000, 1400],
                                  'form': 'markdown'}, READING)
    monkeypatch.setattr(correction_proposal, 'open_store', lambda mirror: store)
    monkeypatch.setattr(reading_cells, 'may_send', lambda file: True)
    monkeypatch.setattr(session_judge, 'filtered_pages', lambda mirror: set())
    return store


def asking(answer: dict, asked: list):
    def ask(params):
        asked.append(params)
        return Message(answer)
    return ask


def test_a_proposal_is_asked_once_kept_and_its_cost_in_the_ledger(a_reading):
    asked = []
    answer = {'agrees_with_judge': 'yes', 'image_shows': 'The page prints 4.6%.',
              'correction': 'The rate rose to 4.6% in the second year and stayed there to the end.'}
    found = correction_proposal.propose('free', 'r' * 64, 'b01', [FINDING], version='correction/1', asker=asking(answer, asked),
                                        spent=lambda: 0.0)
    assert (found['state'], found['correction'], found['flags']) == ('proposed', answer['correction'], [])
    again = correction_proposal.propose('free', 'r' * 64, 'b01', [FINDING], version='correction/1', asker=asking(answer, asked),
                                        spent=lambda: 0.0)
    assert len(asked) == 1 and again == found  # never bought twice
    (line,) = [line for line in a_reading.ledger() if line['kind'] == 'correction']
    assert line['cost_usd'] == found['cost_usd'] > 0 and line['provider'] == 'anthropic'


def test_the_model_sees_the_image_the_block_as_the_judge_saw_it_and_the_finding_as_a_pointer(a_reading):
    asked = []
    correction_proposal.propose('free', 'r' * 64, 'b03', [{'kind': 'other', 'severity': 'minor', 'evidence': 'not steady'}],
                                version='correction/1', spent=lambda: 0.0,
                                asker=asking({'agrees_with_judge': 'yes', 'image_shows': '', 'correction': 'Bars.'}, asked))
    (params,) = asked
    texts = [part['text'] for part in params['messages'][0]['content'] if part['type'] == 'text']
    assert 'POINTER, NOT A FACT' in params['system'][0]['text']
    assert any('[b03 description of=b02 form=prose DERIVED]' in text for text in texts)
    assert any('- other, minor: not steady' in text for text in texts)
    assert [part['type'] for part in params['messages'][0]['content']].count('image') == 1


def test_a_page_turned_away_or_a_file_held_back_is_never_sent(a_reading, monkeypatch):
    never = lambda params: pytest.fail('asked')  # noqa: E731
    monkeypatch.setattr(session_judge, 'filtered_pages', lambda mirror: {('book.pdf', 7)})
    with pytest.raises(correction_proposal.Refused, match='never sent again'):
        correction_proposal.propose('free', 'r' * 64, 'b01', [FINDING], version='correction/1', asker=never, spent=lambda: 0.0)
    monkeypatch.setattr(session_judge, 'filtered_pages', lambda mirror: set())
    monkeypatch.setattr(reading_cells, 'may_send', lambda file: False)
    with pytest.raises(correction_proposal.Refused, match='send: false'):
        correction_proposal.propose('free', 'r' * 64, 'b01', [FINDING], version='correction/1', asker=never, spent=lambda: 0.0)


def test_nothing_is_asked_without_an_active_version_or_over_the_spend_cap(a_reading):
    never = lambda params: pytest.fail('asked')  # noqa: E731
    with pytest.raises(correction_proposal.Refused, match='no active'):
        correction_proposal.propose('free', 'r' * 64, 'b01', [FINDING], asker=never, spent=lambda: 0.0)  # correction/1 is a prototype
    with pytest.raises(correction_proposal.Refused, match='spend guard'):
        correction_proposal.propose('free', 'r' * 64, 'b01', [FINDING], version='correction/1', asker=never, spent=lambda: 199.999)


def test_a_person_is_told_when_a_proposal_changes_nothing_much_or_finds_no_error():
    from backend.conversion.contract.page_contract import parse

    blocks = {block.id: block for block in parse(READING, 'markdown').blocks}
    assert correction_proposal.flags_of(blocks['b01'], blocks['b01'].body, 'no') == ['unchanged', 'the image shows no such error']
    assert correction_proposal.flags_of(blocks['b01'], 'A wholly other sentence about money.', 'yes') == ['large change']
    assert correction_proposal.flags_of(blocks['b03'], 'Red bars grow from the middle onward.', 'yes') == []  # a description is prose
    short = parse(page('::: {#b01 .index_entry bbox="1 1 2 2"}\nrates, 12, 14\n:::'), 'markdown').blocks[0]
    assert correction_proposal.flags_of(short, 'rates, 21, 41', 'yes') == []  # two values of a short entry are no large change


@pytest.mark.parametrize('proposal, scores', [
    ('The rate rose to 4.6% in the second year.', (1.0, 1.0)),
    ('The rate rose to 4.6% in the third year.', (1.0, 0.5)),  # one more word changed than the person did
    ('The rate rose to 4.5% in the second year.', (0.0, 0.0)),  # unchanged: the person's edit not made, nothing right
])
def test_a_proposal_is_scored_by_the_person_s_edit(proposal, scores):
    original, person = 'The rate rose to 4.5% in the second year.', 'The rate rose to 4.6% in the second year.'
    assert correction_proposal.edit_scores(original, person, proposal) == scores


def test_the_proposal_fills_the_whole_verdict_by_fixed_rules():
    # F1.a (21 Nov): the model gives what needs the image, fixed rules the rest; nothing is recorded by it
    from backend.conversion.contract.page_contract import parse

    blocks = {block.id: block for block in parse(READING, 'markdown').blocks}
    proposed = lambda agrees, correction: {'state': 'proposed', 'agrees_with_judge': agrees, 'correction': correction,  # noqa: E731
                                           'image_shows': 'what the image shows'}
    fields = ('verdict', 'reason', 'judge_assessment', 'correction')
    left = correction_proposal.prefill(proposed('no', blocks['b01'].body), blocks['b01'])
    assert [left[field] for field in fields] == ['accept', 'judge_false_alarm', 'false_alarm', None]
    quoted = correction_proposal.prefill(proposed('yes', 'Another sentence.'), blocks['b01'])
    assert [quoted[field] for field in fields] == ['reject', 'reading_wrong', 'right', 'Another sentence.']
    described = correction_proposal.prefill(proposed('partly', 'Bars.'), blocks['b03'])
    assert [described[field] for field in fields] == ['accept', 'finding_on_unquoted_block', 'right_for_a_wrong_reason', 'Bars.']
    assert described['block'] == 'b03' and described['note'] == 'what the image shows'
    assert correction_proposal.prefill({'state': 'no proposal'}, blocks['b01']) is None


def test_every_reason_the_prefill_names_is_one_a_person_may_give():
    from backend.conversion.store import pipeline_db

    assert {'judge_false_alarm', 'reading_wrong', 'finding_on_unquoted_block', 'other'} <= set(pipeline_db.HUMAN_REASONS)
    assert set(correction_proposal.ASSESSMENT_OF.values()) <= set(pipeline_db.JUDGE_ASSESSMENTS)
