"""Apply the index database's pending migrations, or show their status (issue #10, part A); the only writer of its schema.

    python -m backend.database.migrate            # apply what is pending, each file in its own transaction
    python -m backend.database.migrate --status   # applied, pending, drifted; changes nothing but the ledger's creation
"""

import argparse
import sys

from backend.database.database_url import DatabaseNotConfigured, database_url
from backend.database.migration_runner import MigrationError, MigrationFileError, MigrationRunner


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--status', action='store_true', help='show applied, pending and drifted migrations; apply nothing')
    args = parser.parse_args(argv)
    try:
        runner = MigrationRunner(database_url())
        if args.status:
            status = runner.status()
            print(f'applied {len(status.applied)}: {[f"{m.version}_{m.name}" for m in status.applied]}')
            print(f'pending {len(status.pending)}: {[f"{m.version}_{m.name}" for m in status.pending]}')
            print(f'drifted {len(status.drifted)}: {[f"{m.version}_{m.name}" for m in status.drifted]}')
            return 1 if status.drifted else 0
        runs = runner.apply()
        for run in runs:
            print(f'applied {run.version}_{run.name} in {run.duration_ms:.0f} ms')
        if not runs:
            print('nothing pending')
        return 0
    except (DatabaseNotConfigured, MigrationError, MigrationFileError) as error:
        print(f'migrate: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
