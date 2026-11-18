"""Build the diagnostics UI and stamp the build with the sources it was made from.

    python -m backend.diagnostics.build

1. writes the API's OpenAPI schema to `src/frontend/diagnostics/openapi.json`,
2. turns it into TypeScript types (`npm run types`, openapi-typescript),
3. type-checks and builds the UI into `dist/` (`npm run build`, vue-tsc and Vite),
4. writes `dist/build_stamp.json` with one SHA-256 over every build input.

The build is committed so a reviewer needs no Node; Node runs only here, on the developer's machine.
A contract test computes the hash again in Python and fails when an input changed after the last build.
"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from backend.diagnostics.app import app

UI = Path(__file__).resolve().parents[2] / 'frontend' / 'diagnostics'
SCHEMA = UI / 'openapi.json'
STAMP = UI / 'dist' / 'build_stamp.json'
# What Vite and vue-tsc read to make the build. Tests and lint settings are not inputs, so changing
# them needs no rebuild.
INPUT_FILES = ('index.html', 'package.json', 'package-lock.json', 'openapi.json', 'vite.config.ts',
               'tsconfig.json', 'tsconfig.app.json', 'tsconfig.node.json')
INPUT_DIRS = ('src', 'public')


def build_inputs(ui: Path = UI) -> list[Path]:
    files = [ui / name for name in INPUT_FILES if (ui / name).is_file()]
    for folder in INPUT_DIRS:
        files += [path for path in (ui / folder).rglob('*') if path.is_file()]
    return sorted(files, key=lambda path: path.relative_to(ui).as_posix())


def sources_sha256(ui: Path = UI) -> str:
    """One hash over every build input: its path and the hash of its bytes.

    Line endings are normalised first. A clone with `core.autocrlf=true` checks text files out with CRLF,
    and without this the contract test would fail on such a clone although nothing changed.
    """
    digest = hashlib.sha256()
    for path in build_inputs(ui):
        content = hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        digest.update(f'{path.relative_to(ui).as_posix()}\0{content}\n'.encode())
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')


def npm(*args: str) -> None:
    executable = shutil.which('npm')
    if executable is None:
        sys.exit('npm not found: building the UI needs Node.js. Running it does not, the build is committed.')
    subprocess.run([executable, *args], cwd=UI, check=True)


def main() -> None:
    write_json(SCHEMA, app.openapi())
    npm('run', 'types')
    npm('run', 'build')
    write_json(STAMP, {'sources_sha256': sources_sha256(), 'inputs': len(build_inputs())})
    print(f'Built {STAMP.parent}, stamped over {len(build_inputs())} inputs.')


if __name__ == '__main__':
    main()
