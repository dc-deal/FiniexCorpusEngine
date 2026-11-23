import anthropic
import httpx
import pytest

from backend.ingestion import code_catalog

CODE = ('{ Fast Average\n  From an invented article, Invented Magazine, May 2011 }\n'
        'inputs: Length(14), Price(Close), Band(Average(Range, 10));\nPlot1(Average(Price, Length));\n')


def test_a_units_name_is_its_file_name_without_the_prefix_the_kind_mark_or_the_extension():
    assert code_catalog.unit_name('Indicators/XYZ Fast Average (I).txt', 'XYZ') == 'Fast Average'
    assert code_catalog.unit_name('Functions/XYZFastAverage.txt', 'XYZ') == 'Fast Average'
    assert code_catalog.unit_name('Functions/XYZ_Fast_Average.txt', 'XYZ') == 'Fast Average'


def test_code_reads_the_declared_inputs_with_their_defaults_and_the_source_the_opening_comment_names():
    assert code_catalog.declared_inputs(CODE) == [{'name': 'Length', 'default': '14'}, {'name': 'Price', 'default': 'Close'},
                                                  {'name': 'Band', 'default': 'Average(Range, 10)'}]
    assert code_catalog.source_named(CODE) == 'Fast Average From an invented article, Invented Magazine, May 2011'
    assert code_catalog.declared_inputs('Plot1(Close);') == [] and code_catalog.source_named('Plot1(Close);') is None


def test_an_answer_is_kept_under_a_key_of_everything_asked_so_a_changed_file_is_asked_again():
    assert code_catalog.request_key(CODE) == code_catalog.request_key(CODE)
    assert code_catalog.request_key(CODE) != code_catalog.request_key(CODE + ' ')


def test_a_passing_failure_is_tried_again_and_after_the_last_try_the_unit_waits(monkeypatch):
    request = httpx.Request('POST', 'https://api.anthropic.com/v1/messages')
    calls = []

    def flaky(name, kind, code):
        calls.append(name)
        if len(calls) < 2:
            raise anthropic.APIConnectionError(request=request)
        return {'category': 'trend', 'aliases': [], 'summary': 'x'}, {'input_tokens': 1, 'output_tokens': 1}

    monkeypatch.setattr(code_catalog, 'ask', flaky)
    assert code_catalog.ask_with_retries('Fast', 'indicator', CODE, pause=0)[0]['category'] == 'trend' and len(calls) == 2

    def down(name, kind, code):
        raise anthropic.APIConnectionError(request=request)

    monkeypatch.setattr(code_catalog, 'ask', down)
    assert code_catalog.ask_with_retries('Fast', 'indicator', CODE, pause=0) is None


def test_the_categories_are_a_closed_list_the_schema_enforces():
    assert code_catalog.SCHEMA['properties']['category']['enum'] == list(code_catalog.CATEGORIES)
    assert 'utility' in code_catalog.CATEGORIES and len(set(code_catalog.CATEGORIES)) == len(code_catalog.CATEGORIES)
    with pytest.raises(KeyError):
        code_catalog.SCHEMA['properties']['category']['default']
