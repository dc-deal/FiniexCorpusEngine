"""Start the diagnostics UI: `python -m backend.diagnostics`, then open http://127.0.0.1:8001.

`--public-only` serves the free knowledge base alone and never reads the licensed one: for a recorded review.
`--no-chat` switches the chat off, so nothing this process does can spend money: the browser check starts it this way.
`--allow-verdicts` opens the one write route: a person's verdict from the page view (213.b). Off by default (223.a), so a
clone stays read-only.
"""

import argparse

import uvicorn

from backend.diagnostics import chat
from backend.diagnostics.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description='Serve the diagnostics UI and its API.')
    parser.add_argument('--port', type=int, default=8001)
    parser.add_argument('--host', default='127.0.0.1',
                        help='the address to listen on (default 127.0.0.1); 0.0.0.0 only inside a container, whose port is published on '
                             '127.0.0.1 alone (docker-compose.yml)')
    parser.add_argument('--public-only', action='store_true',
                        help='serve the free knowledge base alone; the licensed one is never read')
    parser.add_argument('--no-chat', action='store_true', help='switch the chat off: no model is ever called')
    parser.add_argument('--allow-verdicts', action='store_true',
                        help="take a person's verdict from the page view, recorded in the pipeline database and exported in "
                             'the background; without it the app is read-only')
    args = parser.parse_args()
    scope = ' (the free knowledge base only)' if args.public_only else ''
    writes = '; verdicts from the page view are taken' if args.allow_verdicts else ''
    print(f'Diagnostics UI on http://127.0.0.1:{args.port}{scope}{writes}', flush=True)
    # Loopback only: the UI can show readings of the licensed works, which never leave this machine; in a container it listens
    # on its own interface and Docker publishes the port on 127.0.0.1 alone. The search index is built while the server comes
    # up, so the first search does not wait for it.
    uvicorn.run(create_app(public_only=args.public_only, warm_search=True, chat_agent=None if args.no_chat else chat.default_agent,
                           allow_verdicts=args.allow_verdicts),
                host=args.host, port=args.port)


if __name__ == '__main__':
    main()
