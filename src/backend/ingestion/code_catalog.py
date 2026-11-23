"""The catalog of a code work's units (issue #12, the operator's idea of 23 Nov 2026): which indicators, functions and
strategies the corpus holds, asked for as a client asks for works.

The technique is LLM-based metadata extraction for metadata filtering (self-query retrieval): each unit gets a record a client
can filter by kind and category and find by name. What code can read stays code's; only what needs reading the code is asked of
a model.

- **By code:**
  - the unit's name, from its file name with the publisher's prefix split off;
  - its kind, from its folder (function, indicator, strategy);
  - its inputs as the file declares them (`inputs:` with their defaults);
  - the source its opening comment names (an article, a magazine, a chapter).
- **By a model** (Claude Haiku over the API, structured output, a few cents for a whole work): one category from a closed list,
  the other names the unit goes by, and one sentence on what it computes or trades. The sentence is derived, the model's own
  words, and the record says so; it is never quoted as the source's words.
- **Kept once:** every answer is stored under a key of everything asked (the file's hash, the instructions, the model, the
  schema), so a unit is never bought twice and a changed file is asked again.

    python -m backend.ingestion.code_catalog build --work KEY [--dry-run] [--limit N]
"""

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from backend.configuration import data_paths
from backend.search import code_pages

MODEL = 'claude-haiku-5-5'
CATALOG = data_paths.LICENSED_WORKING / 'code_catalog.json'  # derived and private: names what the licensed code holds
CATEGORIES = ('trend', 'momentum', 'mean reversion', 'breakout', 'volatility', 'volume', 'pattern', 'cycle', 'seasonality',
              'spread and arbitrage', 'risk and money management', 'statistics', 'utility')
INSTRUCTIONS = (
    'You catalog one unit of trading code (an indicator, a function or a strategy) for a search tool. Read the code and '
    'answer with the JSON the schema asks for:\n'
    f'- category: the one that fits best of: {", ".join(CATEGORIES)}. "utility" is for a helper that computes no market '
    'signal of its own.\n'
    '- aliases: the other names a trader would search this unit by (for example "KAMA" and "Kaufman Adaptive Moving '
    'Average"), at most five, none repeating the given name; an empty list if there are none.\n'
    '- summary: one plain sentence of at most 30 words on what it computes or how it trades, in your own words; name the '
    'method, never the code\'s variables.')
SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['category', 'aliases', 'summary'],
          'properties': {'category': {'type': 'string', 'enum': list(CATEGORIES)},
                         'aliases': {'type': 'array', 'items': {'type': 'string'}},
                         'summary': {'type': 'string'}}}
MAX_TOKENS = 400
MAX_CODE_CHARS = 12_000  # the longest file of the first work is about 8,200; a longer one is sent cut, and says so
INPUTS = re.compile(r'(?is)\binputs?\s*:\s*(.*?);')
INPUT = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)')
OPENING_COMMENT = re.compile(r'^\s*\{(.*?)\}', re.S)


def unit_name(label: str, prefix: str | None) -> str:
    """A unit's name: its file name without the publisher's prefix, the kind mark `(I)` or `(S)`, or the extension."""
    stem = Path(label).stem
    if prefix and stem.startswith(prefix):
        stem = stem[len(prefix):]
    stem = re.sub(r'\s*\((?:I|S|F)\)\s*$', '', stem).replace('_', ' ').strip()
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', stem) if ' ' not in stem else stem


def declared_inputs(code: str) -> list[dict]:
    """The inputs a unit declares (`inputs: Length(14), Price(Close);`), each with its default as written."""
    found = INPUTS.search(code)
    if not found:
        return []
    return [{'name': name, 'default': default.strip()} for name, default in INPUT.findall(found.group(1))]


def source_named(code: str) -> str | None:
    """What the file's opening comment says it comes from, as written, in one line; None without an opening comment."""
    found = OPENING_COMMENT.match(code)
    if not found:
        return None
    text = ' '.join(found.group(1).split())
    return text[:240] or None


def request_key(code: str) -> str:
    spec = {'model': MODEL, 'instructions': INSTRUCTIONS, 'schema': SCHEMA, 'max_tokens': MAX_TOKENS,
            'code': hashlib.sha256(code.encode('utf-8')).hexdigest()}
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode('utf-8')).hexdigest()


def ask(name: str, kind: str | None, code: str) -> tuple[dict, dict]:
    """One unit's category, aliases and sentence, and the call's usage; the answer is checked against the schema's list."""
    from backend.conversion.reading import reader_requests
    from backend.providers import anthropic_client

    shown = code if len(code) <= MAX_CODE_CHARS else code[:MAX_CODE_CHARS] + '\n{ … the rest of the file is cut here }'
    settings = json.loads(json.dumps(reader_requests.MODEL_SETTINGS[MODEL]))
    settings['output_config'] = {**settings.get('output_config', {}), 'format': {'type': 'json_schema', 'schema': SCHEMA}}
    message = anthropic_client.client().messages.create(
        **settings, model=MODEL, max_tokens=MAX_TOKENS, system=INSTRUCTIONS,
        messages=[{'role': 'user', 'content': f'Name: {name}\nKind: {kind or "unknown"}\n\nCode:\n{shown}'}])
    text = ''.join(block.text for block in message.content if getattr(block, 'type', '') == 'text')
    answer = json.loads(text)
    if answer.get('category') not in CATEGORIES:
        raise ValueError(f'{name}: a category outside the list: {answer.get("category")!r}')
    usage = {'input_tokens': message.usage.input_tokens, 'output_tokens': message.usage.output_tokens}
    return answer, usage


def load() -> dict:
    return json.loads(CATALOG.read_text(encoding='utf-8')) if CATALOG.exists() else {'about': __doc__.splitlines()[0], 'units': {}}


def save(catalog: dict) -> None:
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    partial = CATALOG.with_suffix('.json.part')
    partial.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    partial.replace(CATALOG)


def build(args) -> dict:
    from backend.providers import anthropic_client

    works = code_pages.licensed_code()
    if args.work not in works:
        sys.exit(f'no code work {args.work!r} in the local catalog; known: {sorted(works)}')
    folder, entry = works[args.work]
    pages = code_pages.code_pages(args.work, folder, prefix=entry.get('name_prefix'))
    catalog = load()
    todo = [page for page in pages if catalog['units'].get(f'{args.work}|{page.page}', {}).get('key') != request_key(page.text)]
    if args.limit:
        todo = todo[:args.limit]
    estimate = sum(anthropic_client.cost_usd(MODEL, (len(INSTRUCTIONS) + min(len(page.text), MAX_CODE_CHARS)) // 3 + 60, 90)
                   for page in todo)
    print(f'{args.work}: {len(pages)} units, {len(todo)} to ask {MODEL}, estimate {estimate:.4f} USD')
    if args.dry_run or not todo:
        return {'units': len(pages), 'asked': 0, 'estimate_usd': estimate}
    spent, asked, skipped = 0.0, 0, 0
    for page in todo:
        name, kind = unit_name(page.page, entry.get('name_prefix')), code_pages.unit_kind(page.page)
        answered = ask_with_retries(name, kind, page.text)
        if answered is None:  # a passing failure three times: the unit stays for the next run, nothing is stored
            skipped += 1
            continue
        answer, usage = answered
        spent += anthropic_client.cost_usd(MODEL, usage['input_tokens'], usage['output_tokens'])
        catalog['units'][f'{args.work}|{page.page}'] = {
            'work': args.work, 'page': page.page, 'name': name, 'unit': kind, 'category': answer['category'],
            'aliases': [alias for alias in answer['aliases'] if alias.strip() and alias.strip().lower() != name.lower()][:5],
            'summary': answer['summary'].strip(), 'summary_is': f'derived ({MODEL})', 'inputs': declared_inputs(page.text),
            'source_named': source_named(page.text), 'lines': {'first': page.line, 'last': page.line_end},
            'key': request_key(page.text), 'model': MODEL, 'usage': usage,
            'stored_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}
        asked += 1
        if asked % 25 == 0:
            save(catalog)
            print(f'{asked}/{len(todo)} asked, {spent:.4f} USD')
        time.sleep(0.05)
    save(catalog)
    print(f'{args.work}: {asked} units asked, {spent:.4f} USD; written to {CATALOG}'
          + (f'; {skipped} left for the next run after passing failures' if skipped else ''))
    return {'units': len(pages), 'asked': asked, 'spent_usd': spent, 'skipped': skipped}


def ask_with_retries(name: str, kind: str | None, code: str, tries: int = 3, pause: float = 5.0) -> tuple[dict, dict] | None:
    """`ask`, tried again after a passing failure (the connection, a timeout, a rate limit, a server error); None after the
    last try. A refusal of the request or an answer outside the schema is no passing failure and ends the run."""
    import anthropic

    passing = (anthropic.APIConnectionError, anthropic.APITimeoutError, anthropic.RateLimitError,
               anthropic.InternalServerError)
    for attempt in range(tries):
        try:
            return ask(name, kind, code)
        except passing as error:
            print(f'{name}: {type(error).__name__}, try {attempt + 1} of {tries}', flush=True)
            time.sleep(pause * (attempt + 1))
    return None


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    built = commands.add_parser('build')
    built.add_argument('--work', required=True)
    built.add_argument('--limit', type=int, default=0)
    built.add_argument('--dry-run', action='store_true')
    built.set_defaults(run=build)
    args = parser.parse_args(argv)
    args.run(args)
    return 0


if __name__ == '__main__':
    sys.exit(main())
