"""Suite-wide fixtures.

The offline guarantee is enforced here rather than stated: every test not marked `live` runs
with outgoing connections refused. In Sprint 1 a "free" run turned out to make paid calls from a
background task that no test mentioned; a guard that fails loudly is the only reliable answer.
"""

import socket

import pytest

from backend.configuration import data_paths



LOOPBACK = {'127.0.0.1', '::1', 'localhost'}


@pytest.fixture(autouse=True)
def _refuse_network(request, monkeypatch):
    """Refuse every connection that leaves the machine.

    Connections to the machine itself are let through: on Windows, asyncio (which the MCP
    client runs on) builds its event loop's wake-up channel from a socket pair over 127.0.0.1.
    Nothing outside, OpenRouter included, can be reached that way.
    """
    if request.node.get_closest_marker('live'):
        return
    connect, create_connection = socket.socket.connect, socket.create_connection

    def refuse():
        raise RuntimeError('network access in an offline test - mark it @pytest.mark.live')

    def guarded_connect(self, address, *args, **kwargs):
        if isinstance(address, tuple) and address and address[0] in LOOPBACK:
            return connect(self, address, *args, **kwargs)
        refuse()

    def guarded_create_connection(address, *args, **kwargs):
        if address and address[0] in LOOPBACK:
            return create_connection(address, *args, **kwargs)
        refuse()

    monkeypatch.setattr(socket.socket, 'connect', guarded_connect)
    monkeypatch.setattr(socket, 'create_connection', guarded_create_connection)


# What each data marker needs, all of it in the local data folder `_data/` (264.a, 282), and what to do without it.
NEEDS = {
    'corpus': (data_paths.FREE_RAW / '_manifest.json', 'run python -m backend.ingestion.acquire first'),
    'readings': (data_paths.FREE_READINGS / 'index.json', 'the page readings are in the local data folder'),
    'results': (data_paths.RESULTS, 'the measurements are in the local data folder'),
}


@pytest.fixture(autouse=True)
def _skip_without_data(request):
    """A test marked with what it reads skips where a clone has none of it, as a public clone has no `_data/`."""
    for marker, (needed, hint) in NEEDS.items():
        if request.node.get_closest_marker(marker) and not needed.exists():
            pytest.skip(f'{needed.relative_to(data_paths.ROOT).as_posix()} is missing - {hint}')


_DATABASE = {}


def database_reachable() -> bool:
    """Whether the index database answers (issue #10), asked once per run; a clone without Docker or .env says no."""
    if 'up' not in _DATABASE:
        import psycopg

        from backend.database.database_url import DatabaseNotConfigured, database_url
        try:
            with psycopg.connect(database_url(), connect_timeout=2):
                _DATABASE['up'] = True
        except (DatabaseNotConfigured, psycopg.Error):
            _DATABASE['up'] = False
    return _DATABASE['up']


@pytest.fixture
def scratch_database():
    """An empty database of its own on the running server, dropped after: the real index is never touched. Its URL is
    handed to the test; only tests marked `database` use it."""
    import uuid
    from urllib.parse import urlsplit, urlunsplit

    import psycopg

    from backend.database.database_url import database_url

    url = database_url()
    name = f'corpus_test_{uuid.uuid4().hex[:12]}'
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE {name}')
    yield urlunsplit(urlsplit(url)._replace(path=f'/{name}'))
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)')


@pytest.fixture(autouse=True)
def _skip_without_database(request):
    """A test marked `database` skips where the index database is not running, as the data markers skip without data."""
    if request.node.get_closest_marker('database') and not database_reachable():
        pytest.skip('the index database is not running - docker compose up -d postgres, with CORPUS_DB_PASSWORD in .env')
