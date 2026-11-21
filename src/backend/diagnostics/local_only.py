"""The guard of the routes here that write or spend: a person's verdict (213.b) and a call to the librarian (L1.a), which can
spend a fraction of a cent, and a model call with the router on.

Each answers only a request addressed to this machine by name (127.0.0.1 or localhost, against a page elsewhere reaching it
through DNS rebinding), and, where a browser says where the request comes from (`Origin`), only one from this machine's own
pages: a page elsewhere can neither reach the route nor make a browser send to it. Both sit behind the app's own
TrustedHostMiddleware as a second wall. Taken from the chat's route, which went with the chat (L1.a), and the verdict's.
"""

from urllib.parse import urlsplit

from fastapi import HTTPException, Request

LOCAL_HOSTS = ('127.0.0.1', 'localhost', '::1')


def local_host_only(request: Request) -> None:
    """Refuses a request not addressed to this machine by name."""
    host = request.headers.get('host', '')
    name = host[1:host.index(']')] if host.startswith('[') and ']' in host else host.split(':')[0]
    if name not in LOCAL_HOSTS:
        raise HTTPException(403, 'This route answers only requests addressed to this machine (127.0.0.1 or localhost).')


def local_origin_only(request: Request) -> None:
    """Refuses a request a browser sent from a page elsewhere: where it names its origin, that origin must be this machine's
    own. A request with no origin (a command line on this machine) passes, as the host check has passed."""
    origin = request.headers.get('origin')
    if origin is None:
        return
    host = urlsplit(origin).hostname or ''
    if host not in LOCAL_HOSTS:
        raise HTTPException(403, "This route is taken only from this machine's own pages.")


def guarded(request: Request) -> None:
    """Addressed to this machine, and sent from its own pages."""
    local_host_only(request)
    local_origin_only(request)
