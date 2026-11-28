"""Reading groups (the operator's 52.a, 28 Nov 2026): a run kept together, with its name, a short description and a document
the view shows. The groups and their members are two append-only tables of each knowledge base's pipeline database
(`pipeline_db.create_group`, `add_to_group`); a reading in no group belongs to the root, and the view draws no group row for
a page that has only the root. The export names each reading's groups and lists the groups (`reading_export`).

A group's document holds, first, what matters most (`.claude` rule "an experiment's group document"): the comparison table,
the performance table, the course of each test, the models with their settings and most important parameters. A free
group's document is tracked under `docs/experiments/`; a licensed group's stays in the knowledge base's working folder.

    python -m backend.conversion.store.reading_groups create --knowledge-base free --id night-2026-11-26 --name "…" \\
        --description "…" --document docs/experiments/night-2026-11-26.md
    python -m backend.conversion.store.reading_groups add --knowledge-base free --id night-2026-11-26 --run night_2026-11-26
    python -m backend.conversion.store.reading_groups list --knowledge-base free
"""

import argparse
import sys

from backend.conversion.reading import reading_cells, vision_batches
from backend.conversion.store import pipeline_db
from backend.conversion.store.reading_store import open_store

KNOWLEDGE_BASES = ('free', 'licensed')


def readings_of_run(store, run: str) -> list[str]:
    """The keys of every reading a run stored, by the run's name in the record (a local run's import names its folder)."""
    cells = list(reading_cells.known_cells())
    return [record['reading_key'] for record in vision_batches.readings_of(cells, store) if record.get('run') == run]


def readings_of_cell(store, cell: str) -> list[str]:
    if cell not in reading_cells.known_cells():
        raise ValueError(f'no cell {cell!r}')
    return [record['reading_key'] for record in vision_batches.readings_of([cell], store)]


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('create', help='a new group')
    create.add_argument('--knowledge-base', choices=KNOWLEDGE_BASES, required=True)
    create.add_argument('--id', required=True)
    create.add_argument('--name', required=True)
    create.add_argument('--description', required=True)
    create.add_argument('--document', help="the group document's path from the repository's root")
    create.add_argument('--by', default='line 1', help='who made it: a person, or the line that ran it')
    add = commands.add_parser('add', help="readings into a group, by their run's name or their cell")
    add.add_argument('--knowledge-base', choices=KNOWLEDGE_BASES, required=True)
    add.add_argument('--id', required=True)
    which = add.add_mutually_exclusive_group(required=True)
    which.add_argument('--run')
    which.add_argument('--cell')
    listing = commands.add_parser('list', help='every group with its member count')
    listing.add_argument('--knowledge-base', choices=KNOWLEDGE_BASES, required=True)
    args = parser.parse_args(argv)
    if args.command == 'create':
        row = pipeline_db.create_group(args.knowledge_base, args.id, args.name, args.description, args.by, args.document)
        print(f"group {row['group_id']} made at {row['created_at']}")
    elif args.command == 'add':
        store = open_store(args.knowledge_base)
        keys = readings_of_run(store, args.run) if args.run else readings_of_cell(store, args.cell)
        if not keys:
            print('no reading found: nothing added')
            return 1
        added = pipeline_db.add_to_group(args.knowledge_base, args.id, keys)
        print(f'{added} of {len(keys)} readings added to {args.id}')
    else:
        for group in pipeline_db.reading_groups(args.knowledge_base):
            print(f"{group['group_id']}  {group['readings']:>4} readings  {group['created_at'][:16]}  {group['name']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
