"""The index database's connection URL (issue #10): the configured host, port, database and user with the password from
.env; a container names its own host and port (`postgres:5432`) through the environment, and a whole URL wins where set."""

import os
from urllib.parse import quote

from backend.configuration.app_config_manager import AppConfigManager
from backend.configuration.config_file_loader import ConfigFileLoader
from backend.constants.database_constants import HOST_ENV, PASSWORD_ENV, PORT_ENV, URL_ENV


class DatabaseNotConfigured(RuntimeError):
    """No URL and no password: the database cannot be reached, and nothing is guessed."""


def database_url() -> str:
    """`CORPUS_DATABASE_URL` where it is set; else the configured place, its host and port overridden by `CORPUS_DB_HOST`
    and `CORPUS_DB_PORT` where a container sets them, with the password from the environment or .env. The password is
    never logged, and an error names the variable, never its value."""
    from dotenv import load_dotenv

    load_dotenv(ConfigFileLoader.ROOT / '.env', override=False)
    if url := os.environ.get(URL_ENV):
        return url
    password = os.environ.get(PASSWORD_ENV)
    if not password:
        raise DatabaseNotConfigured(f'set {URL_ENV}, or {PASSWORD_ENV} in .env (see .env.example)')
    database = AppConfigManager().get_database()
    host = os.environ.get(HOST_ENV) or database.host
    port = os.environ.get(PORT_ENV) or database.port
    return (f'postgresql://{quote(database.user, safe="")}:{quote(password, safe="")}@{host}:{port}/'
            f'{quote(database.name, safe="")}')
