"""Every third-party package the code imports is declared in requirements.txt.

A missing entry does not fail here, where the package happens to be installed. It fails on the
reviewer's machine, after `pip install -r requirements.txt`.
"""

import ast
import re
import subprocess
import sys
from importlib.metadata import packages_distributions
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# The project's own packages: every folder in src/. Derived rather than listed, so a new one
# cannot be mistaken for a missing third-party package.
LOCAL = {p.name for p in (ROOT / 'src').iterdir() if p.is_dir()} | {'conftest'}
# Code that runs in the RAGAS report's own environment (decision 136.a): checked against requirements-eval.txt instead
EVALUATION_ENV = {'src/backend/evaluation/ragas_report.py'}
MODULE_DISTRIBUTIONS = {'dotenv': 'python-dotenv'}  # import names that differ from their distribution's, where not installed


def imported_modules(evaluation_env: bool = False) -> dict[str, str]:
    """Top-level module name → first file importing it, over the project's Python files: the app's, or with `evaluation_env`
    the files of the RAGAS report's environment."""
    found = {}
    # Only what git would commit is the project's code: the virtual environment, the local data folders and a frontend's
    # node_modules (KaTeX ships Python helper scripts there, found 2026-11-04) are all left out for that one reason.
    listed = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '--', '*.py'], cwd=ROOT,
                            capture_output=True, text=True, check=True).stdout.splitlines()
    files = [ROOT / name for name in listed if (ROOT / name).exists() and (name in EVALUATION_ENV) == evaluation_env]
    for path in files:
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                found.setdefault(name.split('.')[0], str(path.relative_to(ROOT)))
    return found


def declared(requirements: str = 'requirements.txt') -> set[str]:
    names = set()
    for line in (ROOT / requirements).read_text(encoding='utf-8').splitlines():
        line = line.split('#')[0].strip()
        if line:
            names.add(re.split(r'[=<>!~\[ ]', line)[0].lower().replace('_', '-'))
    return names


def undeclared(evaluation_env: bool, requirements: str) -> dict[str, str]:
    distributions = packages_distributions()
    missing = {}
    for module, where in imported_modules(evaluation_env).items():
        if module in sys.stdlib_module_names or module in LOCAL or module.startswith('test_'):
            continue
        dists = {d.lower().replace('_', '-') for d in distributions.get(module, [MODULE_DISTRIBUTIONS.get(module, module)])}
        if not dists & declared(requirements):
            missing[module] = where
    return missing


def test_every_third_party_import_is_declared():
    assert undeclared(False, 'requirements.txt') == {}, 'imported but not in requirements.txt'


def test_the_ragas_report_imports_only_what_its_own_environment_declares():
    assert undeclared(True, 'requirements-eval.txt') == {}, 'imported but not in requirements-eval.txt'
