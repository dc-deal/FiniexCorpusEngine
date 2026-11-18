"""Where the data lives (264.a): `_data/` keeps the repository's layout, so a stored path names one file either way."""

from backend.configuration import data_paths


def test_a_stored_data_path_is_found_under_data_and_any_other_in_the_repository():
    assert data_paths.locate('corpus/raw/x.pdf') == data_paths.DATA / 'corpus' / 'raw' / 'x.pdf'
    assert data_paths.locate('corpus/readings/w/p0001.md') == data_paths.FREE_READINGS / 'w' / 'p0001.md'
    assert data_paths.locate('evaluation/results/r.json') == data_paths.RESULTS / 'r.json'
    assert data_paths.locate('corpus/catalog.json') == data_paths.ROOT / 'corpus' / 'catalog.json'
    assert data_paths.locate('docs/roadmap.md') == data_paths.ROOT / 'docs' / 'roadmap.md'
    assert data_paths.locate('corpus/rawer/x.pdf') == data_paths.ROOT / 'corpus' / 'rawer' / 'x.pdf'  # a prefix is no folder


def test_stored_names_a_file_as_the_catalog_and_the_exports_do_and_undoes_locate():
    for spelled in ('corpus/raw/w/A.html', 'corpus/readings/w/p0001.md', 'evaluation/results/r.json', 'corpus/catalog.json'):
        assert data_paths.stored(data_paths.locate(spelled)) == spelled
    own = data_paths.DATA / 'README.md'  # the data folder's own files stay apart: named from the root, or where it lies (285.a)
    assert data_paths.stored(own) == (own.relative_to(data_paths.ROOT).as_posix() if own.is_relative_to(data_paths.ROOT)
                                      else own.as_posix())


def test_a_root_of_its_own_names_the_files_outside_the_data_from_there(tmp_path):
    assert data_paths.stored(tmp_path / 'archive' / 'b.pdf', tmp_path) == 'archive/b.pdf'
    assert data_paths.stored(data_paths.FREE_RAW / 'x.pdf', tmp_path) == 'corpus/raw/x.pdf'


def test_the_configured_folders_come_from_the_app_config():
    from backend.configuration.app_config_manager import AppConfigManager
    paths = AppConfigManager().get_paths()
    assert data_paths.DATA == data_paths.ROOT / paths.data and data_paths.INDEX == data_paths.ROOT / paths.index
    assert data_paths.LICENSED_ARCHIVE == data_paths.ROOT / paths.originals / 'licensed'
    assert data_paths.FREE_WORKING == data_paths.ROOT / paths.working / 'free' and data_paths.LOGS == data_paths.ROOT / paths.logs


def test_the_licensed_catalog_lies_in_the_local_working_folder():
    # N1.a (18 Nov): licensed titles and authors, local only; `_work/` is git-ignored as a whole (251.a)
    assert data_paths.LICENSED_CATALOG == data_paths.LICENSED_WORKING / 'catalog.json'
    assert data_paths.LICENSED_WORKING.parent == data_paths.WORKING
