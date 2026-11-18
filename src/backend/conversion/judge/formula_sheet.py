"""Every formula of a reading rendered as an image, so the judge can set it beside the page.

A model reads LaTeX source well, but a person and a model both compare two pictures better: `\\frac{a}{b+c}` against the printed
fraction. KaTeX gives MathML, and a headless browser renders MathML natively, so no fonts or CSS are downloaded (measured
2026-10-30 with Edge). Checked first: rendering KaTeX's HTML output needs its stylesheet and 60 font files, and matplotlib's mathtext
has no `aligned` or `array`. Microsoft Edge ships with Windows; on a machine without a browser `sheets` returns nothing, and the
caller records that the judge saw no sheet. A browser is used only if it really writes a screenshot: on 2026-11-04 an Edge
update left msedge.exe returning at once with exit code 0 and no image, so each candidate is tried once on a tiny page.

    sheets(parsed) -> list of PNG bytes   # empty: no formula on the page, or no browser
"""

import functools
import html
import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops

from backend.conversion.checks import katex_check
from backend.conversion.contract.page_contract import ParsedPage

BROWSERS = (r'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', r'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
            r'C:/Program Files/Google/Chrome/Application/chrome.exe', r'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe')
BROWSER_NAMES = ('msedge', 'chrome', 'google-chrome', 'chromium', 'chromium-browser')
WIDTH = 1100
ROW_HEIGHT = 130
MARGIN = 60
MAX_HEIGHT = 2400  # inside the API's limits: 2,576 px on the long edge and 4,760 patches of 28 px
TIMEOUT_SECONDS = 120
PAGE = ('<!doctype html><meta charset="utf-8"><style>body{{margin:12px;font:20px "Cambria Math",serif;background:#fff}}'
        'table{{border-collapse:collapse}}td{{padding:10px 18px;border-bottom:1px solid #ccc}}'
        'td.id{{font:16px monospace;color:#444}}math{{font-size:26px}}</style><table>{rows}</table>')


@functools.cache
def find_browser() -> str | None:
    """The first installed browser that writes a headless screenshot."""
    candidates = [path for path in BROWSERS if Path(path).exists()] + [found for found in map(shutil.which, BROWSER_NAMES) if found]
    for browser in dict.fromkeys(candidates):
        try:
            _screenshot('<p>probe</p>', browser, 100)
            return browser
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def rows_for(parsed: ParsedPage) -> list[tuple[str, str, bool]]:
    """(block id, LaTeX, display) for every formula and inline math of the page, table cells included, in reading order."""
    rows = []
    for block in parsed.blocks:
        if block.cls == 'formula':
            if block.body.strip():
                rows.append((block.id, block.body.strip(), True))
            continue
        rows.extend((block.id, latex, False) for latex in (block.inline or {}).get('math', []))
        for row in block.rows or []:
            for cell in row:
                rows.extend((block.id, latex, False) for latex in (cell.inline or {}).get('math', []))
    return rows


def _screenshot(page_html: str, browser: str, height: int) -> Image.Image:
    with tempfile.TemporaryDirectory() as folder:
        source, out = Path(folder) / 'sheet.html', Path(folder) / 'sheet.png'
        source.write_text(page_html, encoding='utf-8')
        subprocess.run([browser, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', '--no-default-browser-check',
                        f'--user-data-dir={folder}/profile', '--force-device-scale-factor=1', f'--window-size={WIDTH},{height}',
                        f'--screenshot={out}', source.as_uri()], capture_output=True, timeout=TIMEOUT_SECONDS, check=True)
        return Image.open(out).convert('L').copy()


def _render(rows: list[str], browser: str) -> list[bytes]:
    """One sheet, or more when the rows turn out taller than the window: a sheet never cuts a formula off."""
    height = min(MAX_HEIGHT, MARGIN + ROW_HEIGHT * len(rows))
    image = _screenshot(PAGE.format(rows=''.join(rows)), browser, height)
    box = ImageChops.difference(image, Image.new('L', image.size, 255)).getbbox()
    if box and box[3] >= height - 2 and len(rows) > 1:
        return _render(rows[:len(rows) // 2], browser) + _render(rows[len(rows) // 2:], browser)
    out = io.BytesIO()
    (image.crop((0, 0, image.width, min(height, box[3] + 12))) if box else image).save(out, format='PNG')
    return [out.getvalue()]


def sheets(parsed: ParsedPage) -> list[bytes]:
    rows = rows_for(parsed)
    browser = find_browser()
    if not rows or browser is None:
        return []
    verdicts = katex_check.check_many([(latex, display) for _, latex, display in rows])
    cells = [f'<tr><td class="id">{block_id}</td><td>' + (verdict.mathml if verdict.ok else
             f'does not render: {html.escape(latex)}') + '</td></tr>' for (block_id, latex, _), verdict in zip(rows, verdicts)]
    per_sheet = (MAX_HEIGHT - MARGIN) // ROW_HEIGHT
    return [png for start in range(0, len(cells), per_sheet) for png in _render(cells[start:start + per_sheet], browser)]
