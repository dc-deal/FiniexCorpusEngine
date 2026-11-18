"""LaTeX checked by KaTeX inside an embedded V8 (mini-racer): no Node, no browser, no TeX installation.

KaTeX rejects what a reader can get wrong: a missing or extra brace, an unknown command, `\\left` without
`\\right`, a `$` inside math, the form feed a lost JSON escape leaves behind. latex2mathml, the other candidate
(a docling-core dependency), converted all of these but the `\\left` case without complaint (measured 2026-10-29).
KaTeX's own limit: a TAB where `\\text` was still renders, so `page_contract` scans bodies for control characters.

The check runs in a child process, because mini-racer 0.14.1 on Windows keeps the interpreter alive at shutdown
(measured 2026-10-29). The child writes its answer and leaves hard.

    check_many([(latex, display), ...]) -> [Rendered, ...]
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

KATEX_JS = Path(__file__).resolve().parents[1] / 'vendor' / 'katex.min.js'
TIMEOUT_SECONDS = 300
CHECK_FUNCTION = """
function check(tex, display) {
  try {
    var html = katex.renderToString(tex, {throwOnError: true, displayMode: display, strict: 'error', output: 'mathml'});
    return JSON.stringify({ok: true, mathml: html});
  } catch (e) {
    return JSON.stringify({ok: false, error: String(e.message || e).slice(0, 200)});
  }
}
"""


class KatexUnavailable(RuntimeError):
    """The child process failed: the check did not run, which says nothing about the formulas."""


@dataclass(frozen=True)
class Rendered:
    ok: bool
    error: str | None = None
    mathml: str | None = None


def check_many(items: list[tuple[str, bool]]) -> list[Rendered]:
    """KaTeX's verdict on each (latex, display) pair, in strict mode, with its MathML when it renders."""
    if not items:
        return []
    completed = subprocess.run([sys.executable, str(Path(__file__).resolve())], input=json.dumps(items), text=True,
                               encoding='utf-8', capture_output=True, timeout=TIMEOUT_SECONDS)
    if completed.returncode != 0:
        raise KatexUnavailable(completed.stderr[-400:])
    return [Rendered(ok=row['ok'], error=row.get('error'), mathml=row.get('mathml')) for row in json.loads(completed.stdout)]


def _child() -> None:
    from py_mini_racer import MiniRacer  # only the child process loads V8

    sys.stdin.reconfigure(encoding='utf-8')
    context = MiniRacer()
    context.eval('var self = this; var window = this;')
    context.eval(KATEX_JS.read_text(encoding='utf-8'))
    context.eval(CHECK_FUNCTION)
    rows = [json.loads(context.call('check', latex, display)) for latex, display in json.loads(sys.stdin.read())]
    sys.stdout.write(json.dumps(rows))
    sys.stdout.flush()
    os._exit(0)


if __name__ == '__main__':
    _child()
