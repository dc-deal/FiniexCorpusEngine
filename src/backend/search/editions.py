"""A work's editions (the operator's E1.a, E2.a, E3.a, 20 Nov 2026): one work, its editions a level under it, exactly one
edition served and every other kept.

A kept edition keeps all it has: its readings, its chunks in the private index, its pages in the view and in `open_page` by
its own key. Only the two searches skip it: the keyword index leaves its pages out and the semantic search drops its chunks
after the query, so a switch embeds nothing again. What is served changes only by a command on the operator's word, never by
itself: a file that looks like another edition of a work (the same main title, an author in common) is flagged as a possible
edition and changes nothing until it is linked.

The list lives beside the stand-ins' (`data_paths.LICENSED_WORKING / 'editions.json'`), never in the repository: it tells
what the private collection holds (251.a). A family is named by the key of the edition it was founded with; an edition is
named by its work key, which for these works is its file's stem and its catalog id.

    python -m backend.search.editions                              # every family, what it serves, the possible editions
    python -m backend.search.editions link KEY KEY ... --serves KEY --why TEXT
    python -m backend.search.editions serve KEY --why TEXT         # the operator's choice; then a shelf milestone and a restart

Only the private knowledge base has editions so far ("we only have this one case", the operator, 20 Nov).
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from backend.configuration import data_paths

EDITIONS = data_paths.LICENSED_WORKING / 'editions.json'
ABOUT = ("A work's editions (E1.a): one edition served, the others kept. Written by python -m backend.search.editions; "
         'edit it only through that command.')
_STOPWORDS = {'a', 'an', 'the', 'of', 'and', 'for', 'to', 'in', 'on', 'with'}


def load(path: Path | None = None) -> dict[str, dict]:
    """Family key -> {'editions': [keys], 'serves': key, 'chosen': ISO date, 'why': text}; empty without a list."""
    path = path or EDITIONS
    return json.loads(path.read_text(encoding='utf-8'))['works'] if path.exists() else {}


def kept(families: dict[str, dict] | None = None) -> dict[str, str]:
    """A kept edition's key -> the key of the edition its work serves."""
    families = load() if families is None else families
    return {key: family['serves'] for family in families.values() for key in family['editions'] if key != family['serves']}


def family_of(key: str, families: dict[str, dict]) -> str | None:
    """The family an edition belongs to, by the family's key; None for a work with one edition."""
    return next((name for name, family in families.items() if key in family['editions']), None)


def label(entry: dict | None) -> str:
    """An edition as a person names it, from its catalog entry: "2nd edition, 2005", or the year alone."""
    entry = entry or {}
    edition, year = entry.get('edition'), entry.get('year')
    words = f'{edition} edition' if edition else None
    return ', '.join(str(part) for part in (words, year) if part) or 'edition unknown'


def write(families: dict[str, dict], path: Path | None = None) -> Path:
    """The list as JSON, refused where git would track it: it names private works."""
    from backend.conversion.store import reading_store

    path = path or EDITIONS
    if refused := reading_store.refusal(path.parent.resolve()):
        raise ValueError(f'the editions list is never written there: {refused}')
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps({'about': ABOUT, 'works': families}, indent=1, ensure_ascii=False) + '\n'
    path.write_bytes(text.encode('utf-8'))
    return path


def link(families: dict[str, dict], keys: list[str], serves: str, why: str, today: str) -> dict[str, dict]:
    """A new family of these editions, `serves` the one served. An edition already in a family, or a family of one, is refused."""
    if len(set(keys)) < 2:
        raise ValueError('a family needs two editions or more')
    if serves not in keys:
        raise ValueError(f'{serves!r} is not among the editions linked')
    if taken := [key for key in keys if family_of(key, families)]:
        raise ValueError(f'already in a family: {taken}')
    return {**families, keys[0]: {'editions': list(dict.fromkeys(keys)), 'serves': serves, 'chosen': today, 'why': why}}


def serve(families: dict[str, dict], key: str, why: str, today: str) -> dict[str, dict]:
    """The operator's choice (E2.a): `key` becomes the edition its work serves."""
    name = family_of(key, families)
    if name is None:
        raise ValueError(f'{key!r} is in no family; link it first')
    return {**families, name: {**families[name], 'serves': key, 'chosen': today, 'why': why}}


def main_title(title: str | None) -> str:
    """A title without its subtitle, punctuation and small words: what two editions of one work share."""
    words = re.findall(r'[a-z0-9]+', (title or '').lower().split(':')[0])
    return ' '.join(word for word in words if word not in _STOPWORDS)


def surnames(authors) -> set[str]:
    names = authors if isinstance(authors, list) else str(authors or '').split(',')
    return {name.split()[-1].lower() for name in names if name.split()}


def possible_editions(entries: list[dict], families: dict[str, dict]) -> dict[str, list[str]]:
    """Catalog id -> the ids that look like other editions of the same work (the same main title, an author in common) and
    are not linked with it yet. A part of a series shares its main title with its siblings and with the book they teach by
    design (a lecture deck beside its book), so it is left alone; a family links such a part by hand."""
    found: dict[str, list[str]] = {}
    for one in entries:
        for two in entries:
            if one['id'] >= two['id'] or not main_title(one.get('title')) or main_title(one.get('title')) != main_title(two.get('title')):
                continue
            if one.get('series') or two.get('series'):
                continue
            if not surnames(one.get('authors')) & surnames(two.get('authors')):
                continue
            if family_of(one['id'], families) and family_of(one['id'], families) == family_of(two['id'], families):
                continue
            found.setdefault(one['id'], []).append(two['id'])
            found.setdefault(two['id'], []).append(one['id'])
    return found


def catalog() -> list[dict]:
    """The local licensed catalog's entries; empty on a machine without it."""
    path = data_paths.LICENSED_CATALOG
    return json.loads(path.read_text(encoding='utf-8'))['sources'] if path.exists() else []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command')
    linking = commands.add_parser('link', help='make a family of these editions')
    linking.add_argument('keys', nargs='+')
    linking.add_argument('--serves', required=True)
    linking.add_argument('--why', required=True)
    serving = commands.add_parser('serve', help='the edition its work serves from now on')
    serving.add_argument('key')
    serving.add_argument('--why', required=True)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8')

    families, today = load(), date.today().isoformat()
    try:
        if args.command == 'link':
            families = link(families, args.keys, args.serves, args.why, today)
        elif args.command == 'serve':
            families = serve(families, args.key, args.why, today)
    except ValueError as refused:
        print(refused, file=sys.stderr)
        return 2
    if args.command:
        write(families)
        print('written; next: python -m backend.search.shelf --milestone NAME, then docker compose restart diagnostics librarian')
    entries = {entry['id']: entry for entry in catalog()}
    for name, family in sorted(families.items()):
        print(f'{name}: serves {family["serves"]} ({label(entries.get(family["serves"]))}), chosen {family["chosen"]}: {family["why"]}')
        for key in family['editions']:
            if key != family['serves']:
                print(f'  kept: {key} ({label(entries.get(key))})')
    unlinked = possible_editions(list(entries.values()), families)
    print(f'possible editions not linked: {len(unlinked)}')
    for key, others in sorted(unlinked.items()):
        print(f'  {key}: {", ".join(others)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
