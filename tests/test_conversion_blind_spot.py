from backend.conversion.measurement import blind_spot
from backend.conversion.reading import second_reader


def row(file='a.pdf', page=1, state='ok', judged=True, level='checked', category='content', deviation=None):
    return {'file': file, 'pdf_page': page, 'work': 'w', 'reading_key': f'k{page}', 'text_file': f'w/p{page:04d}.md',
            'check': {'state': state, 'judged': judged}, 'route_level': level, 'category': category, 'deviation': deviation}


def test_only_pages_the_default_reader_read_and_the_judge_passed_are_sampled():
    rows = [row(page=1), row(page=2, judged=False), row(page=3, state='issue'), row(page=4, level='fallback'),
            row(page=5, category='contents'), row(page=6, deviation='a second reader'), row(page=7)]
    assert [page['pdf_page'] for page in blind_spot.candidates(rows)] == [1, 7]


def test_its_key_is_never_the_second_readers_for_the_same_page():
    # the purpose is part of the question, so a measurement's reading can never stand for a page through another cell
    same = {'image_sha': 'i', 'system_sha': 's', 'user_sha': 'u'}
    ours = blind_spot.reading_spec(**same)
    theirs = second_reader.reading_spec(model=blind_spot.MODEL, **same)
    assert ours != theirs and ours['purpose'] == blind_spot.PURPOSE


def test_two_readings_are_compared_by_their_verbatim_words_only():
    served = '::: {#b01 .paragraph}\nThe rate was 5.25 percent in 2007.\n:::\n'
    other = '::: {#b01 .paragraph}\nThe rate was 5.75 percent in 2007.\n:::\n'
    ratio, spans = blind_spot.differences(blind_spot.verbatim_words(served), blind_spot.verbatim_words(other))
    assert ratio < 1.0 and spans == [{'op': 'replace', 'served': '5.25', 'other': '5.75'}]
    assert blind_spot.differences(['a', 'b'], ['a', 'b']) == (1.0, [])


def test_a_tables_markup_is_no_word():
    served = '::: {#b01 .table}\n<table><tr><td>Cash</td><td>1,500</td></tr></table>\n:::\n'
    other = '::: {#b01 .table}\n<table><thead></thead><tr><td>Cash<br></td><td>1,500</td></tr></table>\n:::\n'
    assert blind_spot.verbatim_words(served) == blind_spot.verbatim_words(other) == ['cash', '1,500']
