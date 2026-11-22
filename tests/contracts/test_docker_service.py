"""The always-on service (docker-compose.yml): loopback only, started again with Docker, no data and no key in the image."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = yaml.safe_load((ROOT / 'docker-compose.yml').read_text(encoding='utf-8'))
SERVICES = COMPOSE['services']


def test_every_published_port_listens_on_this_machine_alone():
    # the view can show readings of licensed works, and the librarian answers anyone holding the token: never on the LAN
    for name, service in SERVICES.items():
        for port in service.get('ports', []):
            assert str(port).startswith('127.0.0.1:'), f'{name} publishes {port} beyond loopback'


def test_every_service_comes_back_with_docker_until_it_is_stopped_by_hand():
    assert {name: service.get('restart') for name, service in SERVICES.items()} == \
        {name: 'unless-stopped' for name in SERVICES}


OWN_IMAGE = 'finiex-corpus-engine'


def test_the_keys_come_from_the_mounted_env_never_from_the_image_and_a_clone_without_one_still_starts():
    own = {name: service for name, service in SERVICES.items() if service.get('image') == OWN_IMAGE}
    assert set(own) >= {'librarian', 'diagnostics'}
    for name, service in SERVICES.items():
        if name in own:
            assert service['env_file'] == [{'path': '.env', 'required': False}], name
        else:  # a foreign image (the database, its admin page) never gets the whole .env and its keys (issue #10)
            assert 'env_file' not in service, name
        assert not any('KEY' in str(item) or 'TOKEN' in str(item) for item in service.get('environment', [])), name
    # a variable missing from .env is interpolated empty, never a stop: `:?` would halt every service of a clone
    assert ':?' not in (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')


def test_the_image_is_built_from_the_requirements_alone():
    assert (ROOT / '.dockerignore').read_text(encoding='utf-8').split('\n')[1:3] == ['*', '!requirements.txt']
