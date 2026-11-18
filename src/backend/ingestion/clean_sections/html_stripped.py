r"""An HTML source's sections as readable, stripped HTML, made on demand for the diagnostics view (the operator's 5.a, 9 Nov).

Beside the indexed text of a section the view shows its original: headings, paragraphs, lists, tables, code, quotes and
formulas as the loader reads them, nothing that runs or loads. It is made here from `corpus/raw` each time it is asked for and
never stored (no cache file, nothing under `corpus/`): the SRE book is CC BY-NC-ND, so no converted copy of it enters the
repository (decision 91.a), and the raw file stays the one copy of record.

It walks a document the way `html_sections.parse_sections` does (the same profile, noise, formulas and section boundaries, the
same blocks read), without changing that module: its `LOADER_VERSION` and code hash stand for the chat's index. A test holds the
two together: the text of every stripped section, read the way the loader reads text, is the section's indexed text.

The sections a profile drops (Wikipedia's references and link lists, Gutenberg's contents) come back apart, at their place in
the outline, so the view can show them greyed; their text stays out of every index and search answer.

Display safety stays with the view's own sanitiser; this is the first filter, an allow-list:
- kept: headings with their id; p, ul/ol/li, dl/dt/dd, table/thead/tbody/tr/th/td (colspan, rowspan), pre/code, blockquote,
  em/strong/i/b, sub/sup, br, and a link whose href is http(s) or an in-document #anchor;
- every other element becomes a plain `<span>` with its text and allowed children, or a plain `<div>` where a browser breaks
  the line (`html_sections.EDGES`: the loader reads a space at those edges only), and the ones that could run or load
  something (script, style, link, meta, base, iframe, noscript, form, object, embed, svg, canvas, video, audio) leave their
  text only, in a plain span;
- every other attribute goes, on* handlers, style and class among them;
- an image becomes an empty `<span data-image="its alt text">`, so nothing loads from outside and the text stays the loader's;
- a formula is the loader's text, its LaTeX in \( \) or \[ \], in `<span data-tex="…" data-display="inline|block">` with
  the bare LaTeX in data-tex, so the view can typeset it; Wikipedia's picture of the same formula (its fallback image, alt
  text the same LaTeX) goes, or it would show twice (the operator, 10 Nov).
"""

import html
import re
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup, CData, NavigableString, Tag

from backend.ingestion.clean_sections.html_sections import (BLOCKS, EDGES, HEADINGS, PROFILES, Profile, anchor_of, delimited,
                                                             latex_of, prepared, text_of)

KEPT = {'p', 'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'pre', 'code', 'blockquote',
        'em', 'strong', 'i', 'b', 'sub', 'sup', 'br', 'a', 'h1', 'h2', 'h3', 'h4'}
TEXT_ONLY = {'script', 'style', 'link', 'meta', 'base', 'iframe', 'noscript', 'form', 'object', 'embed', 'svg', 'canvas', 'video',
             'audio'}
VOID = {'br'}
SAFE_HREF = re.compile(r'^(?:https?://|#)', re.I)
BASE: ContextVar[str | None] = ContextVar('base', default=None)  # the document's address, while it is stripped
# A block's wrapper, so runs of items read as the list, table or definitions they came from
WRAPPERS = {'li': None, 'tr': 'table', 'dt': 'dl', 'dd': 'dl'}


@dataclass
class StrippedSection:
    source_id: str
    ordinal: int              # as `load_html_sections` numbers it, across the source's files
    heading_path: list[str]
    anchor: str | None
    file: str
    html: str


@dataclass
class DroppedSection:
    source_id: str
    heading: str
    heading_id: str
    after_ordinal: int | None  # the indexed section it follows in the outline; None before the first
    file: str
    html: str


TEX = 'stripped-tex'  # a formula's place in the soup while it is stripped; never in the output


def mark_math(soup: BeautifulSoup) -> None:
    """`html_sections.replace_math`, with the formula kept as a marked element instead of bare text: the same delimited LaTeX
    as its text, so it reads as the loader reads it, and the bare LaTeX beside it for typesetting."""
    for math in soup.find_all('math'):
        latex = latex_of(math)
        if not latex:
            math.replace_with(' ')
            continue
        block = math.get('display') == 'block'
        marked = soup.new_tag(TEX)
        marked['latex'], marked['display'] = latex, 'block' if block else 'inline'
        marked.string = delimited(latex, block)
        math.replace_with(marked)


def _attributes(tag: Tag) -> str:
    kept = []
    if tag.name in HEADINGS and tag.get('id'):
        kept.append(('id', tag['id']))
    href = str(tag.get('href') or '').strip()
    if tag.name == 'a' and href and not href.startswith('#') and BASE.get():
        href = urljoin(BASE.get(), href)  # Wikipedia links relative to the article: made absolute, so they lead somewhere
    if tag.name == 'a' and SAFE_HREF.match(href):
        kept.append(('href', href))
    if tag.name in ('td', 'th'):
        kept += [(name, tag[name]) for name in ('colspan', 'rowspan') if str(tag.get(name) or '').isdigit()]
    return ''.join(f' {name}="{html.escape(str(value), quote=True)}"' for name, value in kept)


def _children(node: Tag) -> str:
    """An element's children as stripped HTML, in order."""
    return ''.join(stripped(child) for child in node.children)


def stripped(node) -> str:
    """One element or text as allowed HTML: kept tags with their allowed attributes, others unwrapped, text escaped."""
    if isinstance(node, NavigableString):  # the strings the loader reads: no comment, doctype or declaration
        return html.escape(str(node)) if type(node) in (NavigableString, CData) else ''
    if not isinstance(node, Tag):
        return ''
    if node.name == TEX:
        latex, display = str(node.get('latex') or ''), 'block' if node.get('display') == 'block' else 'inline'
        return f'<span data-tex="{html.escape(latex, quote=True)}" data-display="{display}">{html.escape(node.get_text())}</span>'
    if node.name == 'img' and any(name.startswith('mwe-math-fallback-image') for name in node.get('class') or []):
        return ''  # Wikipedia's picture of a formula whose LaTeX stands beside it
    if node.name == 'img':
        return f'<span data-image="{html.escape(str(node.get("alt") or ""), quote=True)}"></span>'
    if node.name in TEXT_ONLY:
        text = node.get_text()
        return f'<span>{html.escape(text)}</span>' if text else ''
    inner = _children(node)
    if node.name not in KEPT:  # a plain div where a browser breaks the line, and the loader reads a space; else a plain span
        wrapper = 'div' if node.name in EDGES else 'span'
        return f'<{wrapper}>{inner}</{wrapper}>' if inner else ''
    if node.name in VOID:
        return f'<{node.name}>'
    return f'<{node.name}{_attributes(node)}>{inner}</{node.name}>'


def _wrapper(block: Tag) -> str | None:
    """The list, table or definition list a block stands in, by the tag of its own parent."""
    if block.name == 'li':
        parent = block.find_parent(['ul', 'ol'])
        return parent.name if parent is not None else 'ul'
    return WRAPPERS.get(block.name)


def _render(blocks: list[Tag]) -> str:
    """Blocks in order, a run of items in one list, rows in one table, terms in one definition list."""
    out, run, kind = [], [], None

    def close():
        if run:
            body = ''.join(run)
            out.append(f'<{kind}><tbody>{body}</tbody></{kind}>' if kind == 'table' else f'<{kind}>{body}</{kind}>')
            run.clear()

    for block in blocks:
        wrapper = _wrapper(block)
        if wrapper != kind:
            close()
            kind = wrapper
        if wrapper is None and block.name not in KEPT:  # a figure's caption reads as a paragraph, as the loader reads it
            out.append(f'<p>{_children(block)}</p>')
        elif wrapper is None:
            out.append(stripped(block))
        else:
            run.append(stripped(block))
    close()
    return ''.join(out)


def _dropped_roots(root: Tag, heading_ids: set[str]) -> list[tuple[Tag, list[Tag]]]:
    """What `html_sections.drop_sections` would remove, without removing it: per dropped heading the elements that go with it
    (its <section>, or the heading and its following siblings up to the next heading of its level), in document order."""
    found, inside = [], set()
    for heading in root.find_all(HEADINGS):
        if id(heading) in inside or heading.get('id') not in heading_ids:
            continue
        container = heading.find_parent('section')
        if container is not None and container.find(HEADINGS) is heading:
            elements = [container]
        else:
            elements = [heading]
            for sibling in heading.find_next_siblings():
                if sibling.name == heading.name or (isinstance(sibling, Tag) and sibling.find(heading.name)):
                    break
                elements.append(sibling)
        for element in elements:
            inside.add(id(element))
            inside.update(id(tag) for tag in element.find_all(True))
        found.append((heading, elements))
    return found


def _region(elements: list[Tag]) -> str:
    """A dropped section's elements as stripped HTML: its headings and its outer blocks, read in order as the loader would."""
    tags = [tag for part in elements for tag in ([part] if part.name in HEADINGS + BLOCKS else []) + part.find_all(HEADINGS + BLOCKS)]
    out, blocks = [], []
    for tag in tags:
        if tag.name in HEADINGS:
            out.append(_render(blocks))
            blocks = []
            out.append(f'<{tag.name}{_attributes(tag)}>{html.escape(text_of(tag))}</{tag.name}>')
        elif tag.find_parent(BLOCKS) is None and text_of(tag):
            blocks.append(tag)
    out.append(_render(blocks))
    return ''.join(out)


def strip_document(html_text: str, profile: Profile, source_id: str, document_title: str, file: str,
                   first_ordinal: int = 0, base_url: str | None = None) -> tuple[list[StrippedSection], list[DroppedSection]]:
    """One HTML document's sections as stripped HTML, cut exactly where `parse_sections` cuts, and the sections it drops.
    A relative link is made absolute against `base_url`; an in-document #anchor stays as it is."""
    token = BASE.set(base_url)
    try:
        return _strip(html_text, profile, source_id, document_title, file, first_ordinal)
    finally:
        BASE.reset(token)


def _strip(html_text: str, profile: Profile, source_id: str, document_title: str, file: str,
           first_ordinal: int) -> tuple[list[StrippedSection], list[DroppedSection]]:
    soup = BeautifulSoup(prepared(html_text), 'html.parser')
    for selector in profile.noise:
        for element in soup.select(selector):
            element.decompose()
    mark_math(soup)
    root = soup.select_one(profile.content) if profile.content else (soup.body or soup)
    if root is None:
        raise ValueError(f'{source_id}: content element {profile.content!r} not found')
    dropped_roots = _dropped_roots(root, profile.drop_headings)
    gone = {id(element) for _, elements in dropped_roots for element in elements}
    gone |= {id(tag) for _, elements in dropped_roots for element in elements for tag in element.find_all(True)}

    title = document_title
    sections: list[StrippedSection] = []
    dropped: list[DroppedSection] = []
    stack: list[tuple[int, str]] = []
    heading_html, anchor, blocks = '', None, []
    first_heading = True
    dropped_at = {id(heading): elements for heading, elements in dropped_roots}

    def flush():
        # the loader keeps a section only where a block gave it text; the same blocks decide here
        if any(text_of(block) for block in blocks):
            sections.append(StrippedSection(source_id, first_ordinal + len(sections), [title] + [text for _, text in stack], anchor,
                                            file, heading_html + _render([block for block in blocks if text_of(block)])))

    for element in root.find_all(HEADINGS + BLOCKS):
        if id(element) in dropped_at:  # a dropped heading: its region comes back apart, at its place
            # the indexed section it follows: the last one made, or the one still open before it (it is made later)
            count = first_ordinal + len(sections) + (1 if any(text_of(block) for block in blocks) else 0)
            dropped.append(DroppedSection(source_id, text_of(element), element.get('id'), count - 1 if count else None, file,
                                          _region(dropped_at[id(element)])))
            continue
        if id(element) in gone:
            continue
        if element.name in HEADINGS:
            if first_heading and profile.first_heading_is_title:
                title = text_of(element) or title
                first_heading = False
                continue
            first_heading = False
            flush()
            level = int(element.name[1])
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, text_of(element)))
            anchor, blocks = anchor_of(element), []
            heading_html = f'<{element.name}{_attributes(element)}>{html.escape(text_of(element))}</{element.name}>'
            continue
        if element.find_parent(BLOCKS) is not None:
            continue
        blocks.append(element)
    flush()
    return sections, dropped


def strip_source(source: dict, manifest: dict, root: Path) -> tuple[list[StrippedSection], list[DroppedSection]]:
    """Every section of one HTML source as stripped HTML, numbered as `load_html_sections` numbers them, and its dropped
    sections; made from the raw files each time, never stored."""
    profile = PROFILES[source['html_profile']]
    sections: list[StrippedSection] = []
    dropped: list[DroppedSection] = []
    for entry in source['files']:
        text = (root / entry['path']).read_text(encoding='utf-8')
        # the loader's title rule: a Wikipedia article is titled by its file, every other document by its source
        title = Path(entry['path']).stem.replace('_', ' ') if source['html_profile'] == 'wikipedia' else source['title']
        base = (f"https://en.wikipedia.org/wiki/{Path(entry['path']).stem}" if source['html_profile'] == 'wikipedia'
                else entry.get('url'))
        made, gone = strip_document(text, profile, source['id'], title, entry['path'], first_ordinal=len(sections), base_url=base)
        sections += made
        dropped += gone
    return sections, dropped
