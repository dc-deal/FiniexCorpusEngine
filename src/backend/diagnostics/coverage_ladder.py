"""How far each work is refined (the operator's U1.a, 20 Nov: "nowhere said how many pages are available at which refinement"):
one ladder of five levels, the same for a work and for the corpus, every figure counted here and none in the browser.

1. text served: the pages, for an HTML or EPUB work the sections, the librarian serves text for;
2. keyword search: of those, the ones in "search (BM25)";
3. semantic search: the chunks in the vector index and the PDF pages they cover, the private base's in its own (#8); a work
   the provenance list holds back is never embedded, and says so, and a machine without the private index says that, never
   0 of N;
4. read: the pages with a vision reading, and of them those whose reading passed;
5. checked: the pages whose reading the checks found fine, or a person or an automated review settled (`CHECKED`), every
   state counted beside them.

Levels 1 to 4 are the core's shelf (`shelf.load`, written at milestones), level 5 the export's states as every list counts
them (`counted_states`). Each level is drawn against the work's whole: its PDF pages, or for an HTML or EPUB work its
sections. A level that does not apply to a work's format says why, as a level not measured here does.
"""

from backend.diagnostics import work_editions
from backend.diagnostics.ladder_types import LEVELS, Ladder, LadderState, Level, Rung
from backend.diagnostics.readings import DECIDED, DECIDED_BY_REVIEW, KnowledgeBase, StateCount

__all__ = ['CHECKED', 'LEVELS', 'Ladder', 'Level', 'Rung', 'corpus_ladder', 'row_for', 'with_coverage', 'work_ladder']
# what each level means, for its hint and the overview's legend
MEANS: dict[str, str] = {
    'text served': 'the pages (an HTML or EPUB work: its sections) the librarian serves text for',
    'keyword search': 'of those, the ones search (BM25) finds by their words',
    'semantic search': ("what semantic (hybrid) searches: the chunks in its vector index, cut by the text's structure and then "
                        'by the recursive character splitter, and the PDF pages they cover'),
    'read': 'the pages a vision reader read, and of them those whose reading passed',
    'checked': 'the pages whose reading the checks found fine, or a person or an automated review settled',
}
# the states whose reading is checked and stands: what the judge passed, and what a person or a review settled
CHECKED = ('ok', DECIDED, DECIDED_BY_REVIEW)
NOT_VECTORISED = 'not vectorised yet (#8)'  # only where this machine holds no private index (`retrieval.licensed_index_built`)
HELD_NOT_EMBEDDED = 'held back: never embedded'  # a work the provenance list holds back, which #8 never embeds (line 1, 20 Nov)
NOT_SERVED_NOT_EMBEDDED = 'not served: never embedded'  # a file the librarian serves not at all, whose text #8 never sees
NOT_IN_INDEX = 'not in the vector index on this machine'
BY_HEADING = 'not read page by page: cut by its headings'
LEGACY_ONLY = 'legacy markdown'  # a work the shelf serves from the IDE's Markdown alone, its source file not held here
NOT_HELD = "served from the IDE's Markdown; the source file is not held here"  # line 1, 20 Nov
CHECKED_SAID = 'checked by the judge or a review'  # what level 5 counts, in its line (line 1, 20 Nov)
NO_SHELF = 'no shelf built on this machine: `python -m backend.search.shelf` builds it'


def figure(count: int, whole: int | None, unit: str) -> str:
    """'612 of 629 PDF pages', '1 of 1 section'."""
    said = unit if (whole if whole is not None else count) != 1 else unit.removesuffix('s')
    return f'{count:,} of {whole:,} {said}' if whole is not None else f'{count:,} {said}'


def checked_of(states: list[StateCount] | list[LadderState]) -> int:
    return sum(count.count for count in states if count.value in CHECKED)


def licensed_index_built() -> bool:
    """Whether this machine holds the private base's vector index (#8), as the core says it."""
    from backend.search import retrieval

    return retrieval.licensed_index_built()


def not_embedded(knowledge_base: str, held: str | None, not_served: str | None = None) -> str:
    """Why a work, a page or a section has no chunks to count: no private index here, held back, not served, or not in the
    index."""
    if knowledge_base == 'licensed' and not licensed_index_built():
        return NOT_VECTORISED
    return HELD_NOT_EMBEDDED if held else NOT_SERVED_NOT_EMBEDDED if not_served else NOT_IN_INDEX


def semantic_rung(row: dict, whole: int | None, unit: str, pdf: bool) -> Rung:
    semantic = row.get('semantic')
    if semantic is None:
        return Rung(level='semantic search', count=None, of=whole,
                    said=not_embedded(row['knowledge_base'], row.get('held'), row.get('not_served')))
    chunks = f"{semantic['chunks']:,} {'chunk' if semantic['chunks'] == 1 else 'chunks'}"
    if pdf:
        return Rung(level='semantic search', count=semantic['pages'], of=whole,
                    said=f"{chunks} over {figure(semantic['pages'], whole, unit)}")
    # an HTML or EPUB work's sections, and a legacy work's Markdown pages, are embedded whole: each has its chunks once the
    # index holds the work
    return Rung(level='semantic search', count=whole if semantic['chunks'] else 0, of=whole, said=f'{chunks} from its {unit}')


def issue_said(count: int, served: int | None) -> str:
    """The pages with judge findings, and what the core serves for them (line 1, 20 Nov, the operator asking what an issue
    line of a count and a served tally means): a reading whose findings lie only on blocks never quoted is served all the same
    (133.b), any other's page serves its fallback in its place."""
    pages = f"{count:,} {'page' if count == 1 else 'pages'} with judge findings"
    if not served:
        return f"{pages} · {'it serves' if count == 1 else 'each serves'} its fallback"
    if served == count:
        return f"{pages} · {'served' if count == 1 else f'all {count:,} served'}: the findings lie only on blocks never quoted (133.b)"
    return f'{pages} · {served:,} served (findings only on blocks never quoted) · {count - served:,} serve their fallback'


def with_means(ladder: Ladder) -> Ladder:
    """Each rung with what its level counts, in one place for every ladder."""
    for rung in ladder.rungs:
        rung.means = MEANS[rung.level]
    return ladder


def work_ladder(row: dict | None, states: list[StateCount] | None, built_at: str | None = None) -> Ladder | None:
    """A work's ladder from its shelf row and its read pages' states; None where the shelf has no row of it here."""
    if row is None:
        return None
    served = row.get('served') or {}
    pdf = row.get('format') == 'pdf'
    legacy_only = row.get('format') == LEGACY_ONLY
    unit = 'PDF pages' if pdf else 'Markdown pages' if legacy_only else 'sections'
    whole = row.get('pages') if pdf and row.get('pages') is not None else served.get('pages', 0)
    read_states = [LadderState(value=count.value, count=count.count, served=count.served,
                               said=issue_said(count.count, count.served) if count.value == 'issue' else None)
                   for count in states or [] if count.value != 'not_read']
    # a work that serves no text at all, a scan held back, its first level empty where it has a page (C1.b)
    rungs = [Rung(level='text served', count=served.get('pages', 0), of=whole, said=figure(served.get('pages', 0), whole, unit),
                  warn=not served.get('pages') and bool(whole)),
             Rung(level='keyword search', count=served.get('searchable', 0), of=whole,
                  said=figure(served.get('searchable', 0), whole, unit)),
             semantic_rung(row, whole, unit, pdf)]
    if pdf:
        read, passed = row.get('read') or 0, row.get('passed') or 0
        rungs.append(Rung(level='read', count=read, of=whole,
                          said=f'{figure(read, whole, unit)}, {passed:,} passed' if read else f'none of {whole:,} {unit} read yet'))
        checked = checked_of(read_states)
        issues = sum(count.count for count in read_states if count.value == 'issue')  # beside the checked ones (C1.b)
        rungs.append(Rung(level='checked', count=checked, of=whole, said=f'{figure(checked, whole, unit)} {CHECKED_SAID}',
                          issues=issues or None))
    else:
        why = NOT_HELD if legacy_only else BY_HEADING
        rungs += [Rung(level='read', count=None, of=whole, said=why), Rung(level='checked', count=None, of=whole, said=why)]
    rungs = kept_words(row, rungs)
    return with_means(Ladder(unit=unit, whole=whole, rungs=rungs, by_route=served.get('by_route') or {}, held=row.get('held'),
                             not_served=row.get('not_served'), unplaced=row.get('unplaced') or {}, states=read_states,
                             planned=row.get('planned'), passed=row.get('passed') if pdf else None, built_at=built_at))


KEPT_NOT_SEARCHED = 'kept: not searched'
KEPT_HELD_BACK = 'held back from the search'


def kept_words(row: dict, rungs: list[Rung]) -> list[Rung]:
    """A kept edition's levels in neutral words (the operator's E1.a, 20 Nov): it keeps all it has and opens by its own key,
    only the two searches skip it, so its first level says which edition is served, its second that it is not searched, its
    third its chunks held back from the search; never in the warning role, a decided case and no call to look (a kept file's
    outline, which served no text). Any other row's levels as they are."""
    served = work_editions.served_named(row, [])
    if served is None:
        return rungs
    said = {'text served': f'kept: the {served} is served; opens by its own key', 'keyword search': KEPT_NOT_SEARCHED}
    out = []
    for rung in rungs:
        update: dict = {'warn': False}
        if rung.level in said:
            update['said'] = said[rung.level]
        elif rung.level == 'semantic search' and rung.count is not None:
            update['said'] = f'{rung.said}, {KEPT_HELD_BACK}'
        out.append(rung.model_copy(update=update))
    return out


def corpus_ladder(shelves: dict[KnowledgeBase, dict], checked: dict[KnowledgeBase, int],
                  issues: dict[KnowledgeBase, int] | None = None) -> Ladder | None:
    """The corpus's ladder: each level summed over the knowledge bases whose shelf is built here, each base's part kept for
    its card. A base without a vector index is left out of level 3's sum and named there."""
    if not shelves:
        return None
    rows = {name: shelf.get('works') or [] for name, shelf in shelves.items()}

    def whole_of(row: dict) -> int:
        return row['pages'] if row.get('format') == 'pdf' and row.get('pages') is not None else (row.get('served') or {}).get('pages', 0)

    def summed(value) -> dict[KnowledgeBase, int]:
        return {name: sum(value(row) for row in found) for name, found in rows.items()}

    wholes = summed(whole_of)
    whole = sum(wholes.values())
    unit = 'pages and sections'

    # the levels a PDF alone reaches, read and checked, against the PDF pages alone: an HTML or EPUB work's sections are never
    # read page by page, so counted in the whole they would show a corpus read through as read in part
    pdf_pages = sum(row['pages'] for found in rows.values() for row in found if row.get('format') == 'pdf' and row.get('pages'))

    def rung(level: Level, parts: dict[KnowledgeBase, int], pages_filter: dict[str, list[str]] | None = None,
             of: int = whole, of_unit: str = unit) -> Rung:
        total = sum(parts.values())
        said = figure(total, of, of_unit) + (f' {CHECKED_SAID}' if level == 'checked' else '')
        return Rung(level=level, count=total, of=of, said=said, by_base=parts, pages_filter=pages_filter)

    vectorised = {name: found for name, found in rows.items() if any(row.get('semantic') is not None for row in found)}
    covered = {name: sum((row['semantic']['pages'] if row.get('format') == 'pdf' else whole_of(row) if row['semantic']['chunks'] else 0)
                         for row in found if row.get('semantic') is not None) for name, found in vectorised.items()}
    chunks = sum(row['semantic']['chunks'] for found in vectorised.values() for row in found if row.get('semantic') is not None)
    left = [name for name in rows if name not in vectorised]
    of = sum(wholes[name] for name in vectorised)
    said = (f"{chunks:,} chunks over {figure(sum(covered.values()), of, unit)}" + (f" of the {' and '.join(vectorised)} base" if left else '')
            if vectorised else NOT_VECTORISED)
    if vectorised and left:
        said += f"; the {' and '.join(left)} base {NOT_VECTORISED}"
    semantic = Rung(level='semantic search', count=sum(covered.values()) if vectorised else None, of=of if vectorised else whole,
                    said=said, by_base=covered)
    read = summed(lambda row: row.get('read') or 0)
    return with_means(Ladder(unit=unit, whole=whole, rungs=[
        rung('text served', summed(lambda row: (row.get('served') or {}).get('pages', 0))),
        rung('keyword search', summed(lambda row: (row.get('served') or {}).get('searchable', 0))),
        semantic,
        rung('read', read, pages_filter={}, of=pdf_pages, of_unit='PDF pages'),  # every page the Pages view lists has a reading
        rung('checked', {name: checked.get(name, 0) for name in rows}, pages_filter={'state': list(CHECKED)}, of=pdf_pages,
             of_unit='PDF pages').model_copy(update={'issues': sum((issues or {}).get(name, 0) for name in rows) or None})],
        planned=sum(row.get('planned') or 0 for found in rows.values() for row in found),
        passed=sum(row.get('passed') or 0 for found in rows.values() for row in found),
        built_at=max((shelf.get('built_at') or '' for shelf in shelves.values()), default=None) or None))


def row_for(shelf: dict | None, work_id: str, key: str | None = None) -> dict | None:
    """A work's row on its base's shelf: by the id the views link it by (the export's source id, a catalog entry's file stem),
    else by the search's work key, as an EPUB the librarian serves under a legacy work's key is named."""
    rows = (shelf or {}).get('works') or []
    return (next((row for row in rows if row.get('source_id') == work_id), None)
            or next((row for row in rows if key and row.get('work') == key), None))


def with_coverage(ladder: Ladder | None, coverage) -> Ladder | None:
    """A work page's ladder with its read level in the page list's own words (V1.b's line, `unread_pages.Coverage`): how many
    of the PDF's pages the export reads and what serves the rest, counted from the export the list stands on, so the page
    says one figure for its reads and never the shelf's beside it."""
    if ladder is None or coverage is None:
        return ladder
    rungs = [rung.model_copy(update={'count': coverage.read, 'of': coverage.pdf_pages, 'said': coverage.said}) if rung.level == 'read'
             else rung for rung in ladder.rungs]
    return ladder.model_copy(update={'rungs': rungs})
