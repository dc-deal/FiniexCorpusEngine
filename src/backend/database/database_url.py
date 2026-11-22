"""The index database's connection URL (issue #10): a container is handed the whole URL by Compose (its host is the
service `postgres`); a process on this machine builds it from the configuration and the password in .env."""

import os
from urllib.parse import quote

from backend.configuration.app_config_manager import AppConfigManager
from backend.configuration.config_file_loader import ConfigFileLoader
from backend.constants.database_constants import PASSWORD_ENV, URL_ENV


class DatabaseNotConfigured(RuntimeError):
    """No URL and no password: the database cannot be reached, and nothing is guessed."""


def database_url() -> str:
    """`CORPUS_DATABASE_URL` where it is set, else the configured host, port, database and user with the password from
    the environment or .env; the password is never logged, and an error names the variable, never its value."""
    from dotenv import load_dotenv

    load_dotenv(ConfigFileLoader.ROOT / '.env', override=False)
    if url := os.environ.get(URL_ENV):
        return url
    password = os.environ.get(PASSWORD_ENV)
    if not password:
        raise DatabaseNotConfigured(f'set {URL_ENV}, or {PASSWORD_ENV} in .env (see .env.example)')
    database = AppConfigManager().get_database()
    return (f'postgresql://{quote(database.user, safe="")}:{quote(password, safe="")}@{database.host}:{database.port}/'
            f'{quote(database.name, safe="")}')
