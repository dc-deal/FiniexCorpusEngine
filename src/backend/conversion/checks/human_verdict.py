"""A person's verdict on a page's reading, kept for ever beside the judge's (decision 146.a): the person stays the final judge.

    python -m backend.conversion.checks.human_verdict give accept --work openstax-finance-2e --page 5 --block b12 \
        --reason judge_misread_name --tag name_list --note "a list of sponsors; the page prints Carlyse"
    python -m backend.conversion.checks.human_verdict give reject --work openstax-accounting --page 156 --reason reading_wrong --note "..."
    python -m backend.conversion.checks.human_verdict list [--work openstax-finance-2e]

`accept` says the reading is right and the judge's finding is not: the page serves its reading, and its route names the reason.
`reject` says the reading is wrong: the page serves its PDF's text layer. `note` is a remark that changes nothing. A reason comes
from a fixed list (`pipeline_db.HUMAN_REASONS`); `other` needs a note. A verdict is given on the reading that stands when it is
given and applies to that reading only: if the page is read again, the new reading starts unjudged, and the verdict stays in
the page's history. Nothing is overwritten; the pipeline database refuses an update or a delete.

`give` writes the export again, so the views and the search see the verdict; the chat's index follows with the next build.
"""

import argparse
import json
import re
import sys

from backend.conversion.store import pipeline_db, reading_export


BLOCK_ID = re.compile(r'b\d{2,3}')


def _row(base: reading_export.KnowledgeBase, work: str, pdf_page: int) -> dict | None:
    rows = json.loads((base.export / 'index.json').read_text(encoding='utf-8'))['pages']
    return next((row for row in rows if row['work'] == work and row['pdf_page'] == pdf_page), None)


def row_of(base: reading_export.KnowledgeBase, work: str, pdf_page: int) -> dict:
    found = _row(base, work, pdf_page)
    if found is None:
        raise SystemExit(f'{work} has no page {pdf_page} in the {base.name} export')
    return found


def record(base: reading_export.KnowledgeBase, work: str, pdf_page: int, verdict: str, reason: str, by: str,
           block: str | None = None, tag: str | None = None, note: str | None = None, reading_key: str | None = None,
           run_id: int | None = None, correction: str | None = None, judge_assessment: str | None = None,
           answers_judgement: str | None = None) -> dict:
    """Record one verdict on the reading that stands (or the one named), without writing the export. `answers_judgement` is
    the key of the judgement the person had before them (#17), as the page view shows it.

    Raises:
        ValueError: For a page the export does not hold, a reading that is not the page's, a block id that is none, or what
            `pipeline_db.give_verdict` refuses; the page view answers it as the person's input error (decision 213.b).
    """
    row = _row(base, work, pdf_page)
    if row is None:
        raise ValueError(f'{work} has no page {pdf_page} in the {base.name} export')
    key = reading_key or row['reading_key']
    known = {row['reading_key'], *(attempt['reading_key'] for attempt in row.get('attempts') or [])}
    if key not in known:
        raise ValueError(f'{key[:12]} is no reading of {work} p. {pdf_page}')
    lab = {attempt['reading_key'] for attempt in row.get('attempts') or [] if attempt.get('prototype')}
    if verdict == 'accept' and key in lab and key != row['reading_key']:
        # an accept pins the reading it names: on a Lab reading it would serve it past the promotion and its reason (#17)
        raise ValueError(f'{key[:12]} stands in the Lab: promote it to serve it (`promote`), an accept does not')
    if block is not None and not BLOCK_ID.fullmatch(block):
        raise ValueError(f'a block is named as b01, not {block!r}')
    if answers_judgement is not None:
        attempt = next((attempt for attempt in row.get('attempts') or [] if attempt['reading_key'] == key), {})
        if answers_judgement not in {judgement.get('judgement_key') for judgement in attempt.get('judgements') or []}:
            raise ValueError(f'{answers_judgement[:12]} is no judgement of reading {key[:12]}')
    verdict_id = pipeline_db.give_verdict(base.name, row['file'], pdf_page, key, verdict, reason, by, block=block, tag=tag,
                                          note=note, run_id=run_id, correction=correction, judge_assessment=judge_assessment,
                                          answers_judgement=answers_judgement)
    return {'verdict_id': verdict_id, 'reading_key': key, 'file': row['file'], 'route_before': row['route']}


def from_view(base: reading_export.KnowledgeBase, queue, work: str, pdf_page: int, verdict: str, reason: str,
              block: str | None = None, note: str | None = None, correction: str | None = None,
              judge_assessment: str | None = None, answers_judgement: str | None = None) -> dict:
    """A person's verdict from the page view (decision 213.b, the operator, 12 Nov): recorded at once as its own run, given by the
    maintainer like one from the command line, and the export requested in the background (`export_queue.ExportQueue`), so
    the person moves on while the views catch up. Raises ValueError for an input the database would refuse."""
    command = (f'backend.diagnostics: give {verdict} --work {work} --page {pdf_page} --reason {reason}'
               f"{' --block ' + block if block else ''}{' --correction' if correction else ''}"
               f"{' --judge-assessment ' + judge_assessment if judge_assessment else ''} (from the page view)")
    with pipeline_db.run([base.name], command) as recorded:
        made = record(base, work, pdf_page, verdict, reason, 'maintainer', block=block, note=note, run_id=recorded.run_id,
                      correction=correction, judge_assessment=judge_assessment, answers_judgement=answers_judgement)
    return {**made, 'export': queue.request({work})}


def give(base: reading_export.KnowledgeBase, work: str, pdf_page: int, verdict: str, reason: str, by: str, block: str | None = None,
         tag: str | None = None, note: str | None = None, reading_key: str | None = None, run_id: int | None = None,
         export: bool = True, correction: str | None = None, judge_assessment: str | None = None) -> dict:
    """Record one verdict on the reading that stands (or the one named), and write the export again."""
    try:
        made = record(base, work, pdf_page, verdict, reason, by, block=block, tag=tag, note=note, reading_key=reading_key,
                      run_id=run_id, correction=correction, judge_assessment=judge_assessment)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(f"{base.name} {work} p. {pdf_page}: {verdict} ({reason}{', ' + block if block else ''}) on reading "
          f"{made['reading_key'][:12]}, verdict {made['verdict_id']}; the route before: {made['route_before']}")
    if export:
        reading_export.export(base)
        print(f"the route now: {row_of(base, work, pdf_page)['route']}")
    return {'verdict_id': made['verdict_id'], 'reading_key': made['reading_key']}


def reset(base: reading_export.KnowledgeBase, work: str, pdf_page: int, reason: str, by: str, run_id: int | None = None,
          export: bool = True) -> dict:
    """A person's reset of one page (decision 191.a, the operator, 10 Nov): the page's verdicts move to the archive, the reading that
    stands is discarded and the page serves its text layer, and the page may be read and judged again, which a person starts
    (`replay --reread`). Nothing is deleted: the old reading and every verdict stay as the page's history."""
    row = row_of(base, work, pdf_page)
    try:
        reset_id = pipeline_db.give_reset(base.name, row['file'], pdf_page, row['reading_key'], reason, by, run_id=run_id)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(f"{base.name} {work} p. {pdf_page}: reset {reset_id} discards reading {row['reading_key'][:12]}, "
          f"{len(row.get('human') or [])} verdicts archived; the route before: {row['route']}")
    if export:
        reading_export.export(base)
        print(f"the route now: {row_of(base, work, pdf_page)['route']}; read it again with "
              f"`python -m backend.conversion.reading.replay reread --work {work} --page {pdf_page} --cap <USD>`")
    return {'reset_id': reset_id, 'reading_key': row['reading_key']}


def promote_record(base: reading_export.KnowledgeBase, work: str, pdf_page: int, reading_key: str, reason: str, by: str,
                   note: str | None = None, run_id: int | None = None) -> dict:
    """Record a person's promotion of a Lab reading to the page's reading (#17), without writing the export: a reading of
    that page that stands in the Lab (a test reading's or a prototype's) and is valid under today's validator.

    Raises:
        ValueError: For a page the export does not hold, a reading that is not one of the page's Lab readings or not valid,
            or what `pipeline_db.give_promotion` refuses; the page view answers it as the person's input error.
    """
    row = _row(base, work, pdf_page)
    if row is None:
        raise ValueError(f'{work} has no page {pdf_page} in the {base.name} export')
    attempt = next((attempt for attempt in row.get('attempts') or [] if attempt['reading_key'] == reading_key), None)
    if attempt is None or not attempt.get('prototype'):
        raise ValueError(f'{reading_key[:12]} is no Lab reading of {work} p. {pdf_page}')
    if attempt.get('class_now') != 'ok':
        raise ValueError(f"{reading_key[:12]} is {attempt.get('class_now')}: only a valid page/1 reading can be served")
    promotion_id = pipeline_db.give_promotion(base.name, row['file'], pdf_page, reading_key, reason, by, note=note, run_id=run_id)
    return {'promotion_id': promotion_id, 'reading_key': reading_key, 'file': row['file'], 'route_before': row['route']}


def promote_from_view(base: reading_export.KnowledgeBase, queue, work: str, pdf_page: int, reading_key: str, reason: str,
                      note: str | None = None) -> dict:
    """A person's promotion from the page view (#18), recorded at once as its own run, the export requested in the background,
    as a verdict from the view is. Raises ValueError for an input the core refuses."""
    command = f'backend.diagnostics: promote --work {work} --page {pdf_page} --reading {reading_key[:12]} --reason {reason} (from the page view)'
    with pipeline_db.run([base.name], command) as recorded:
        made = promote_record(base, work, pdf_page, reading_key, reason, 'maintainer', note=note, run_id=recorded.run_id)
    return {**made, 'export': queue.request({work})}


def promote(base: reading_export.KnowledgeBase, work: str, pdf_page: int, reading_key: str, reason: str, by: str,
            note: str | None = None, run_id: int | None = None, export: bool = True) -> dict:
    """Promote one Lab reading to the page's reading, and write the export again."""
    try:
        made = promote_record(base, work, pdf_page, reading_key, reason, by, note=note, run_id=run_id)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(f"{base.name} {work} p. {pdf_page}: promoted {reading_key[:12]} ({reason}), promotion {made['promotion_id']}; "
          f"the route before: {made['route_before']}")
    if export:
        reading_export.export(base)
        print(f"the route now: {row_of(base, work, pdf_page)['route']}")
    return made


def listing(base: reading_export.KnowledgeBase, work: str | None = None) -> list[dict]:
    rows = json.loads((base.export / 'index.json').read_text(encoding='utf-8'))['pages']
    found = [{'work': row['work'], 'pdf_page': row['pdf_page'], **verdict} for row in rows if work in (None, row['work'])
             for verdict in row.get('human') or []]
    for item in found:
        print(f"{item['work']} p. {item['pdf_page']} {item['block'] or 'page'}: {item['verdict']} ({item['reason']}"
              f"{', tag ' + item['tag'] if item['tag'] else ''}) on {item['reading_key'][:12]}"
              f"{'' if item['applies'] else ' (an earlier reading)'}, {item['given_at']}")
    print(f'{len(found)} verdicts by a person')
    return found


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    given = commands.add_parser('give', help='record a verdict on one page')
    given.add_argument('verdict', choices=pipeline_db.HUMAN_VERDICTS)
    given.add_argument('--work', required=True)
    given.add_argument('--page', type=int, required=True, help='the PDF page')
    given.add_argument('--reason', required=True, choices=sorted(pipeline_db.HUMAN_REASONS))
    given.add_argument('--block', help='the block the verdict is about, as b12; none for the page as a whole')
    given.add_argument('--tag', help='a word that names what the person saw, as name_list')
    given.add_argument('--note', help='free text; required with the reason other')
    given.add_argument('--by', default='maintainer', help='who gives it (default: maintainer)')
    given.add_argument('--reading', help='another reading of the page than the one that stands, by its key')
    given.add_argument('--correction', help="the block's text as it should read: a person's correction, shown beside the reading, "
                                             'never written into it (decision 188.a)')
    given.add_argument('--judge-assessment', choices=sorted(pipeline_db.JUDGE_ASSESSMENTS),
                       help="how the person rates the judge's finding on the block")
    given.add_argument('--no-export', action='store_true', help='record only; the export is written later')
    listed = commands.add_parser('list', help="every person's verdict in the export")
    listed.add_argument('--work')
    reset_parser = commands.add_parser('reset', help="archive a page's verdicts, discard its reading, and let it be read again")
    reset_parser.add_argument('--work', required=True)
    reset_parser.add_argument('--page', type=int, required=True, help='the PDF page')
    reset_parser.add_argument('--reason', required=True, help='why the page is reset: a reset always says why')
    reset_parser.add_argument('--by', default='maintainer', help='who resets it (default: maintainer)')
    reset_parser.add_argument('--no-export', action='store_true', help='record only; the export is written later')
    promoted = commands.add_parser('promote', help="make a Lab reading the page's reading (#17): a person's act, with a reason")
    promoted.add_argument('--work', required=True)
    promoted.add_argument('--page', type=int, required=True, help='the PDF page')
    promoted.add_argument('--reading', required=True, help='the Lab reading, by its key')
    promoted.add_argument('--reason', required=True, choices=sorted(pipeline_db.PROMOTE_REASONS))
    promoted.add_argument('--note', help='free text; required with the reason other')
    promoted.add_argument('--by', default='maintainer', help='who promotes it (default: maintainer); never a delegated session')
    promoted.add_argument('--no-export', action='store_true', help='record only; the export is written later')
    for command in (given, listed, reset_parser, promoted):
        command.add_argument('--knowledge-base', choices=sorted(reading_export.BASES), default='free')
    return parser


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    args = build_parser().parse_args()
    base = reading_export.BASES[args.knowledge_base]
    if args.command == 'list':
        listing(base, args.work)
        return
    if args.command == 'reset':
        with pipeline_db.run([base.name], pipeline_db.command_line('backend.conversion.checks.human_verdict')) as recorded:
            reset(base, args.work, args.page, args.reason, args.by, run_id=recorded.run_id, export=not args.no_export)
        return
    if args.command == 'promote':
        with pipeline_db.run([base.name], pipeline_db.command_line('backend.conversion.checks.human_verdict')) as recorded:
            promote(base, args.work, args.page, args.reading, args.reason, args.by, note=args.note, run_id=recorded.run_id,
                    export=not args.no_export)
        return
    with pipeline_db.run([base.name], pipeline_db.command_line('backend.conversion.checks.human_verdict')) as recorded:
        give(base, args.work, args.page, args.verdict, args.reason, args.by, block=args.block, tag=args.tag, note=args.note,
             reading_key=args.reading, run_id=recorded.run_id, export=not args.no_export, correction=args.correction,
             judge_assessment=args.judge_assessment)


if __name__ == '__main__':
    main()
