"""A file's stamp, its modification time and size, which every cache of this API is keyed by: what a file holds is read again
only when its stamp changed (line 1, 20 Nov: "cache what does not change between requests, keyed by what would change it").

Within one request a file's stamp is looked at once (`one_look`, set by the app's middleware for every request): the Sources
list asked the export's index for its stamp twice for every work a call, and through the container's mount of the Windows
folder a stat costs about 4 ms, so half a second of a 1.3 s call went on asking the same file the same question. Outside a request (a
background warm-up, a test calling a function itself) every call looks again, as before.

What it cannot see: a file rewritten within the same tick of the file system's clock to the same size, as `page_integrity`
says of its own stamps. Built here rather than taken from a library: a dictionary keyed by a path for the span of a request is
what `contextvars` is for; `functools.lru_cache` keys by arguments and cannot tell that a file changed.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

Stamp = tuple[int, int]  # (modified in nanoseconds, size in bytes)

# the stamps this request has looked at, by path; None outside a request
_looked: ContextVar[dict[Path, Stamp | None] | None] = ContextVar('stamps_looked', default=None)


def stamp(path: Path) -> Stamp | None:
    """The file's modification time and size, None where it does not exist; looked at once within a request."""
    looked = _looked.get()
    if looked is not None and path in looked:
        return looked[path]
    try:
        found = path.stat()
        said: Stamp | None = (found.st_mtime_ns, found.st_size)
    except OSError:
        said = None
    if looked is not None:
        looked[path] = said
    return said


@contextmanager
def one_look() -> Iterator[None]:
    """A request's span: each file's stamp looked at once within it."""
    token = _looked.set({})
    try:
        yield
    finally:
        _looked.reset(token)


class OneLook:
    """The ASGI middleware that gives every HTTP request its `one_look`; a plain ASGI one, so the route runs in the same context
    and a sync route's worker thread sees it (AnyIO copies the context into the thread)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        with one_look():
            await self.app(scope, receive, send)
