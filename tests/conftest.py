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
