"""Which reading of a free page may be served, the route that made each page's text, and a reading as text one can quote.

One place for the rules the search server, the chat's index and the export all follow, so a page never counts as verified in
one of them and as text layer in another. The rows are those of `corpus/readings/index.json` (written by `reading_export`):
tracked, so a clone serves the same pages.

A reading may be served when it is valid under today's validator, not an issue the judge found and its work not stopped; otherwise
the page's own text layer is served and the route says why.
"""

import json
import re
from pathlib import Path

from backend.configuration import data_paths
from backend.constants.reading_constants import DIRECT_DEVIATION, DIRECT_ROUTE_KIND

EXPORT = data_paths.FREE_READINGS
READING_ROUTE = 'vision reading'
TEXT_LAYER_WHY = {  # why a page's text came from its PDF's text layer and not from its reading
    'blocked': 'text layer: the provider blocked the reading',
    'malformed': 'text layer: the reading stayed malformed after its one format retry',
    'no_page': 'text layer: the reading found no page',
    'refused': 'text layer: the reader declined the page',
    'issue': 'text layer: the judge found the reading bad, a person looks at it',
    # decision 196.a (the operator, 12 Nov): say why a work stops and what releases it, not only that a person looks
    'stopped': ('text layer: the work is stopped, too many of its sampled pages were bad; its pages keep their earlier text '
                'until a person releases the work'),
    'unread': 'text layer: the page has no reading',
    'rejected': 'text layer: a person rejected the reading',
    'unchecked': 'text layer: the reading has not been checked yet',
    'reset': 'text layer: a person reset the page; a new reading is due',
}
# Never quoted: page furniture, navigation (a contents or an index names a topic, it explains nothing), and what the reader
# wrote itself rather than read (a figure's description, a block it could not class).
NOT_QUOTED = {'page_header', 'page_footer', 'page_number', 'watermark', 'decoration', 'margin_tab', 'toc_entry', 'index_entry',
              'description', 'other'}
NO_NUMBER = {'', 'none', 'null'}


def quoted_untouched(row: dict) -> bool:
    """Whether every finding of the judge on this reading lies on a block that is never quoted (a figure's description, page
    furniture, a contents or index entry): then the text a quote is taken from is what the judge passed (decision 133.b, the operator,
    2026-11-09). A finding on the page as a whole, or one whose block's class the export does not name, touches the quotes."""
    findings = (((row.get('check') or {}).get('verdict')) or {}).get('findings') or []
    return bool(findings) and all(finding.get('block_class') in NOT_QUOTED for finding in findings)


def human_standing(row: dict | None) -> dict | None:
    """A person's latest accept or reject on the reading that stands, or None (decision 146.a). A note changes nothing, and a
    verdict on an earlier reading of the page does not carry over to this one."""
    found = [verdict for verdict in (row or {}).get('human') or [] if verdict.get('applies') and verdict['verdict'] in ('accept', 'reject')]
    return found[-1] if found else None


def text_layer_why(row: dict | None) -> str | None:
    """None when the page's reading may be served, else why its text layer is served instead. A person's verdict on the reading
    stands over the judge's: a model never overrules a person (decision 146.a)."""
    if row is None or not row.get('text_file'):
        return 'blocked' if row and row.get('error_type') == 'invalid_request_error' else 'unread'
    if row.get('reset'):
        return 'reset'  # a person discarded this reading (decision 191.a)
    person = human_standing(row)
    if person is not None and person['verdict'] == 'reject':
        return 'rejected'
    if person is not None and row['class_now'] == 'ok':
        return None  # accepted by a person, over the judge's finding
    if not row.get('check') and row['class_now'] == 'ok':
        return 'unchecked'  # no check reached this reading: never served as if it had passed (found 9 Nov)
    state = (row.get('check') or {}).get('state')
    if state in ('issue', 'bin') and row['class_now'] == 'ok' and quoted_untouched(row):
        return None  # the judge's issue lies on blocks never quoted: the quotable text stands (133.b)
    if state in ('issue', 'bin', 'stopped') and row['class_now'] == 'ok':  # 'bin' in an export written before decision 97.a
        return 'issue' if state == 'bin' else state
    if row['class_now'] != 'ok':
        return row['class_now'] if row['class_now'] in TEXT_LAYER_WHY else 'malformed'
    return None


def route_of(row: dict | None) -> str:
    """The route a free PDF page's text comes by, from its row in corpus/readings/index.json: the same string a hit carries."""
    why = text_layer_why(row)
    person = human_standing(row)
    if why is None and person is not None:  # accepted by a person (146.a), and the route names the reason, or the note it is said in
        reason = person['note'] if person.get('reason') == 'other' and person.get('note') else person['reason_text']
        return (f"{READING_ROUTE} ({row['model']}, {row['contract']}, validator {row['validator']}): "
                f"a person accepted the reading: {reason}")
    if why is None and (row.get('check') or {}).get('state') in ('issue', 'bin'):  # served by 133.b, and the route says so
        return (f"{READING_ROUTE} ({row['model']}, {row['contract']}, validator {row['validator']}): "
                "the judge's findings lie on blocks never quoted")
    if why is None and (((row.get('check') or {}).get('verdict')) or {}).get('void'):  # the judge's finding was void (146.a)
        return (f"{READING_ROUTE} ({row['model']}, {row['contract']}, validator {row['validator']}): "
                "the judge's findings contradict their own evidence")
    if why is None and row.get('deviation') == DIRECT_DEVIATION:  # read in a Claude Code session (280.a)
        return (f"{READING_ROUTE}, {DIRECT_ROUTE_KIND} ({row['model']}, {row['contract']}, validator {row['validator']}): "
                f"{row['deviation']}")
    if why is None and row.get('deviation'):  # a reading off the default says why, in the route it is served by (63.a)
        return f"{READING_ROUTE}, second reader ({row['model']}, {row['contract']}, validator {row['validator']}): {row['deviation']}"
    if why is None:
        return f"{READING_ROUTE} ({row['model']}, {row['contract']}, validator {row['validator']})"
    return TEXT_LAYER_WHY[why]


ROUTE_LEVELS = {  # how good a page's route is, for a person reading the routes (the operator, 10 Nov: "is this route a faulty one?")
    'checked': 'the checked reading of the page image',
    'noted': 'the checked reading, with a note: a void or unquoted finding, a second reader, or a person accepted it',
    'fallback': "the PDF's own text layer, because the reading could not be served: formulas and tables may be garbled there",
}


def route_level(row: dict | None) -> str:
    """checked, noted or fallback: whether the page serves its checked reading as is, its reading with a note on why it
    stands, or its text layer in the reading's place. Every route quotes word for word; a fallback may garble structure."""
    if text_layer_why(row) is not None:
        return 'fallback'
    return 'checked' if route_of(row) == f"{READING_ROUTE} ({row['model']}, {row['contract']}, validator {row['validator']})" else 'noted'


def export_rows(file_name: str | None = None) -> list[dict]:
    """The rows of corpus/readings/index.json, all or one PDF's; empty where nothing was exported."""
    path = EXPORT / 'index.json'
    rows = json.loads(path.read_text(encoding='utf-8'))['pages'] if path.exists() else []
    return [row for row in rows if file_name is None or row['file'] == file_name]


def printed_of(parsed) -> str | None:
    label = str(parsed.front.get('printed_label', '')).strip()
    return None if label.lower() in NO_NUMBER else label


def inline_text(inline: dict | None, fallback: str = '') -> str:
    """A text block as it reads: its words, inline formulas as \\( … \\), inline code as printed."""
    if not inline or not inline.get('segments'):
        return ' '.join(fallback.split())
    return ' '.join(''.join(_part(kind, value) for kind, value in inline['segments']).split())


NUMBER = re.compile(r'[−-]?\d+')


def _part(kind: str, value: str) -> str:
    """A segment as it reads in a quote: a footnote marker set apart as "[2]" and a numeric superscript as "^2", so neither
    runs into the number before it (decision 205.a: "1947–2020" and its note 2 had read "1947–20202"); an ordinal's "nd"
    and a subscript stay as printed."""
    if kind == 'math':
        return f'\\({value}\\)'
    if kind == 'fn':
        return f'[{value.strip()}]'
    if kind == 'sup' and NUMBER.fullmatch(value.strip()):
        return f'^{value.strip()}'
    return value


def block_text(block) -> str:
    if block.cls == 'formula':
        label = block.attrs.get('label')
        return f'\\[ {block.body.strip()} \\]' + (f' ({label})' if label else '')
    if block.cls == 'code':
        return (block.code or block.body).rstrip()
    if block.cls == 'table':
        return '\n'.join(' | '.join(inline_text(cell.inline, cell.text) for cell in row) for row in block.rows or [])
    if block.cls == 'figure':  # its labels one per line and its groups apart, as the reader wrote them (decision 156.a, the operator,
        # 10 Nov): joined into one run, eleven T-accounts read "… Bal. 5,500 Common Stock 70,000 …"
        return '\n'.join(' '.join(line.split()) for line in block.body.strip().splitlines())
    text = inline_text(block.inline, block.body)
    term = block.attrs.get('term')
    if block.cls == 'glossary_entry' and term and not text.lower().startswith(term.lower()):
        # the term the entry defines stands in its attribute, as the contract asks; without it the index held 934 definitions
        # of the free corpus without the words they define (decision 190.a, the operator, 10 Nov, finance p. 136)
        text = f'{term}: {text}'
    marker = block.attrs.get('marker')
    if block.cls in ('list_item', 'footnote') and marker:
        text = f'{marker} {text}'
    if block.cls == 'heading' and block.attrs.get('number') and not text.startswith(block.attrs['number']):
        text = f"{block.attrs['number']} {text}"
    return text


def quotable_text(parsed) -> str:
    """A page reading as text one can quote: the author's words, formulas, tables and code, in reading order."""
    return '\n\n'.join(text for text in (block_text(block) for block in parsed.blocks
                                         if block.cls not in NOT_QUOTED and block.body.strip()) if text.strip())


def headings_of(parsed) -> list[str]:
    """The page's headings as they read, its number in front; a box's title (`in=`) is no heading of the document."""
    return [text for text in (block_text(block) for block in parsed.blocks if block.cls == 'heading' and not block.attrs.get('in'))
            if text.strip()]


def continues_previous(parsed) -> bool:
    """Whether the page's first quotable block goes on from the page before (the reader's cont=prev or cont=both)."""
    first = next((block for block in parsed.blocks if block.cls not in NOT_QUOTED and block.body.strip()), None)
    return first is not None and first.attrs.get('cont') in ('prev', 'both')


def served_pages(file_name: str, rows: list[dict] | None = None, export: Path = EXPORT) -> dict:
    """PDF page -> what the chat's index uses of a free PDF's page: quotable text, whether it continues the page before, the
    printed number, the route, the reading key and its headings. Pages served from the text layer carry only their route.

    By default from the tracked free export; `rows` and `export` name another one: the rows an export is writing, or the
    licensed export, whose outline is cut from the same pages (decision 84.a)."""
    from backend.conversion.contract.page_contract import parse

    pages = {}
    for row in export_rows(file_name) if rows is None else [row for row in rows if row['file'] == file_name]:
        why = text_layer_why(row)
        if why is not None:
            pages[row['pdf_page']] = {'text': None, 'continues': None, 'printed': None, 'route': TEXT_LAYER_WHY[why], 'reading_key': None,
                                      'headings': None}
            continue
        parsed = parse((export / row['text_file']).read_text(encoding='utf-8'), row['form'])
        pages[row['pdf_page']] = {'text': quotable_text(parsed), 'continues': continues_previous(parsed), 'printed': printed_of(parsed),
                                  'route': route_of(row), 'reading_key': row['reading_key'], 'headings': headings_of(parsed)}
    return pages


def readings_fingerprint(file_name: str) -> str:
    """What a PDF's chunks depend on from its readings: each page's route and text hash. Part of the source's fingerprint, so a
    corrected or newly chosen reading re-indexes its source, and nothing else."""
    import hashlib

    rows = sorted((row['pdf_page'], route_of(row), row.get('text_sha256')) for row in export_rows(file_name))
    return hashlib.sha256(json.dumps(rows).encode('utf-8')).hexdigest()


def is_free_pdf(path: Path) -> bool:
    return bool(export_rows(path.name))
