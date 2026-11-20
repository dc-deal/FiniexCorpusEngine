"""Where the data and the local state live: the one place the code asks, its folders from `configs/app_config.json`.

The repository holds code, docs and tests. Everything else lies in folders the `paths` section of the app's
configuration names (relative to the repository, or absolute), read once when this module is first imported:

- `data`: the local data folder, never in any repository (282), in the repository's layout: the free sources
  (`corpus/raw/`), their checked page readings (`corpus/readings/`) and every measurement (`evaluation/results/`). A path the catalog or an export
  stores (`corpus/raw/x.pdf`) names the same file either way, and `locate` turns it into a place on disk. A clone
  without it gets the free sources with `python -m backend.ingestion.acquire`; what needs readings or measurements
  says so (a test skips, a view shows the free knowledge base empty).
- `originals`: the original books no repository holds: the licensed archive, only on its owner's machine, and the
  downloads of free candidates not yet taken in.
- `working`: what the pipeline makes and keeps on this machine, per knowledge base: the readings store, the pipeline
  database, renders, replays, the licensed export.
- `index` and `logs`: the search index, rebuilt by the build, and the logs.
"""

from pathlib import Path

from backend.configuration.app_config_manager import AppConfigManager
from backend.configuration.config_file_loader import ConfigFileLoader
from backend.constants.data_constants import DATA_FOLDERS

_MANAGER = AppConfigManager()
_PATHS = _MANAGER.get_paths()

ROOT = ConfigFileLoader.ROOT
DATA = _MANAGER.resolve(_PATHS.data)
FREE_RAW = DATA / 'corpus' / 'raw'
FREE_READINGS = DATA / 'corpus' / 'readings'
RESULTS = DATA / 'evaluation' / 'results'
ORIGINALS = _MANAGER.resolve(_PATHS.originals)
LICENSED_ARCHIVE = ORIGINALS / 'licensed'  # the licensed PDFs and EPUBs with their `_manifest.json`
WORKING = _MANAGER.resolve(_PATHS.working)
FREE_WORKING = WORKING / 'free'
LICENSED_WORKING = WORKING / 'licensed'
# The licensed works' catalog (title, authors, publisher, year, format, shelf, licence), the free catalog's fields, written
# from each file's own title and copyright pages (the operator's N1.a, 18 Nov). Local and git-ignored like everything under
# `_work/`: a licensed title never stands in a tracked file (251.a). A view not run with --public-only shows it.
LICENSED_CATALOG = LICENSED_WORKING / 'catalog.json'
SHELF_HISTORY = WORKING / 'shelf_history.json'  # the corpus's milestones, each base's figures apart (X1.a, 19 Nov)
LICENSED_INDEX = LICENSED_WORKING / 'index'  # the private base's vector index (#8): local only, never in any repository
# How the exports spell a file in the role folders (the tracked configuration's names), and where each lies on this machine:
# the same place in the main tree, the main tree's folders in line 2's worktree (285.a, found 20 Nov by line 2)
_ROLE_FOLDERS = {'_sources/': ORIGINALS, '_work/': WORKING}
INDEX = _MANAGER.resolve(_PATHS.index)
LOGS = _MANAGER.resolve(_PATHS.logs)


def locate(stored: str | Path) -> Path:
    """The file a stored, repository-relative path names: under the data for the data folders, else in the repository.

    >>> locate('corpus/raw/x.pdf') == DATA / 'corpus' / 'raw' / 'x.pdf'
    True
    >>> locate('corpus/catalog.json') == ROOT / 'corpus' / 'catalog.json'
    True
    """
    relative = Path(stored).as_posix()
    if _in_data_folder(relative):
        return DATA / relative
    for prefix, folder in _ROLE_FOLDERS.items():  # line 2's worktree names the main tree's folders (285.a)
        if relative.startswith(prefix):
            return folder / relative[len(prefix):]
    return ROOT / relative


def stored(path: Path, root: Path | None = None) -> str:
    """How the catalog and the exports spell a file: the inverse of `locate`, so a hit still says `corpus/raw/x.pdf`.

    >>> stored(DATA / 'corpus' / 'readings' / 'w' / 'p0001.md')
    'corpus/readings/w/p0001.md'
    >>> stored(ROOT / 'src' / 'a.py')
    'src/a.py'
    """
    if path.is_relative_to(DATA) and _in_data_folder(path.relative_to(DATA).as_posix()):
        return path.relative_to(DATA).as_posix()
    if root is None:
        for prefix, folder in _ROLE_FOLDERS.items():  # spelled as the main tree spells them, wherever they lie (285.a)
            if path.is_relative_to(folder):
                return prefix + path.relative_to(folder).as_posix()
    root = root or ROOT  # a caller with a root of its own (a test's folder) names its files from there
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()


def _in_data_folder(relative: str) -> bool:
    return any(relative == folder or relative.startswith(folder + '/') for folder in DATA_FOLDERS)
