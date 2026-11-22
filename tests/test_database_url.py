"""The index database's URL (issue #10): a container's whole URL wins, else the configuration with the password from the
environment; without either nothing is guessed, and the error names the variable, never a value."""
import pytest

from backend.constants.database_constants import PASSWORD_ENV, URL_ENV
from backend.database import database_url as module


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch):
    monkeypatch.setattr('dotenv.load_dotenv', lambda *args, **kwargs: False)  # the machine's .env never enters a test
    from backend.constants.database_constants import HOST_ENV, PORT_ENV

    for name in (URL_ENV, PASSWORD_ENV, HOST_ENV, PORT_ENV):
        monkeypatch.delenv(name, raising=False)


def test_a_whole_url_from_the_environment_wins(monkeypatch):
    monkeypatch.setenv(URL_ENV, 'postgresql://someone:secret@postgres:5432/somewhere')
    monkeypatch.setenv(PASSWORD_ENV, 'other')
    assert module.database_url() == 'postgresql://someone:secret@postgres:5432/somewhere'


def test_the_configured_place_with_the_password_quoted(monkeypatch):
    monkeypatch.setenv(PASSWORD_ENV, 'a/b@c:d')
    assert module.database_url() == 'postgresql://corpusengine:a%2Fb%40c%3Ad@127.0.0.1:5434/corpusengine'


def test_a_container_names_its_own_host_and_port(monkeypatch):
    from backend.constants.database_constants import HOST_ENV, PORT_ENV

    monkeypatch.setenv(PASSWORD_ENV, 'pw')
    monkeypatch.setenv(HOST_ENV, 'postgres')
    monkeypatch.setenv(PORT_ENV, '5432')
    assert module.database_url() == 'postgresql://corpusengine:pw@postgres:5432/corpusengine'


def test_without_a_password_nothing_is_guessed():
    with pytest.raises(module.DatabaseNotConfigured, match=PASSWORD_ENV):
        module.database_url()
