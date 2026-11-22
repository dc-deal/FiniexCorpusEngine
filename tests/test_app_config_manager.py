"""The app's configuration: every default visible in the file, every unknown key refused."""

import json

import pytest
from pydantic import ValidationError

from backend.configuration.app_config_manager import AppConfigManager
from backend.configuration.config_file_loader import ConfigFileLoader
from backend.types.config_types.app_config_types import (AppConfig, CorrectionConfig, DatabaseConfig, EmbeddingsConfig,
                                                         PathsConfig)

RAW = json.loads(ConfigFileLoader.CONFIG_FILE.read_text(encoding='utf-8'))


@pytest.mark.parametrize('section, model', [('paths', PathsConfig), ('embeddings', EmbeddingsConfig),
                                            ('correction', CorrectionConfig), ('database', DatabaseConfig)])
def test_every_typed_default_stands_in_the_file_with_the_same_value(section, model):
    for field, info in model.model_fields.items():
        assert RAW[section].get(field) == info.default, f'{section}.{field}: the file and the model disagree'


def test_the_file_loads_as_the_model_and_the_manager_hands_out_its_paths():
    AppConfig(**RAW)  # the tracked file alone is valid
    # the manager hands out what the loader read: the tracked file with a machine's local file laid over it (285.a)
    assert AppConfig(**ConfigFileLoader.get_config()).paths == AppConfigManager().get_paths()


def test_an_unknown_key_is_refused_and_an_explanation_is_not():
    with pytest.raises(ValidationError):
        PathsConfig(**{**RAW['paths'], 'dta': '_data'})
    with pytest.raises(ValidationError):
        AppConfig(**{**RAW, 'pathz': {}})
    assert PathsConfig(**{'_comment': 'why', 'data': '_data'}).data == '_data'


def test_a_relative_path_lies_in_the_repository_and_an_absolute_one_stays(tmp_path):
    manager = AppConfigManager()
    assert manager.resolve('_data') == ConfigFileLoader.ROOT / '_data'
    assert manager.resolve(str(tmp_path)) == tmp_path


def test_a_local_file_lays_this_machine_s_settings_over_the_tracked_ones_key_by_key():
    from backend.configuration.config_file_loader import deep_merge
    tracked = {'paths': {'data': '_data', 'logs': 'logs'}, 'ui': {'title': 'T'}}
    merged = deep_merge(tracked, {'paths': {'data': 'D:/elsewhere/_data'}})
    assert merged == {'paths': {'data': 'D:/elsewhere/_data', 'logs': 'logs'}, 'ui': {'title': 'T'}}
    assert tracked['paths']['data'] == '_data'  # the tracked configuration is never changed in place


def test_the_local_file_is_read_through_the_loader_and_checked_like_the_tracked_one(tmp_path, monkeypatch):
    local = tmp_path / 'app_config.local.json'
    local.write_text(json.dumps({'paths': {'logs': 'D:/logs'}}), encoding='utf-8')
    monkeypatch.setattr(ConfigFileLoader, 'LOCAL_FILE', local)
    monkeypatch.setattr(ConfigFileLoader, '_config', None)
    assert AppConfigManager().get_paths().logs == 'D:/logs'
    local.write_text(json.dumps({'paths': {'lgos': 'D:/logs'}}), encoding='utf-8')
    monkeypatch.setattr(ConfigFileLoader, '_config', None)
    with pytest.raises(ValidationError):
        AppConfigManager()
