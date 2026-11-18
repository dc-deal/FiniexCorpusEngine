"""Typed access to `configs/app_config.json`: the one place that knows its shape."""

from pathlib import Path

from backend.configuration.config_file_loader import ConfigFileLoader
from backend.types.config_types.app_config_types import AppConfig, EmbeddingsConfig, PathsConfig


class AppConfigManager:
    """The app's configuration, validated once; an unknown key or section stops the program at its start."""

    def __init__(self):
        self._app_config = AppConfig(**ConfigFileLoader.get_config())

    def get_paths(self) -> PathsConfig:
        """Where the data and the local state live, as the file spells them."""
        return self._app_config.paths

    def get_embeddings(self) -> EmbeddingsConfig:
        """Where the vectors are fetched (decision 278.a)."""
        return self._app_config.embeddings

    def resolve(self, configured: str) -> Path:
        """A configured path as a place on disk: relative to the repository, or absolute as it stands."""
        path = Path(configured)
        return path if path.is_absolute() else ConfigFileLoader.ROOT / path
