"""The build stamp: one hash over the UI's build inputs, the same on every machine."""

from backend.diagnostics import build


def a_ui(root):
    (root / 'src').mkdir(parents=True)
    (root / 'src' / 'main.ts').write_bytes(b"import App from './App.vue'\nmount(App)\n")
    (root / 'index.html').write_bytes(b'<div id="app"></div>\n')
    return root


def test_crlf_line_endings_give_the_same_hash(tmp_path):
    ui = a_ui(tmp_path)
    before = build.sources_sha256(ui)
    main = ui / 'src' / 'main.ts'
    main.write_bytes(main.read_bytes().replace(b'\n', b'\r\n'))
    assert build.sources_sha256(ui) == before


def test_a_changed_input_changes_the_hash(tmp_path):
    ui = a_ui(tmp_path)
    before = build.sources_sha256(ui)
    (ui / 'src' / 'main.ts').write_bytes(b"import App from './App.vue'\nmount(App, 1)\n")
    assert build.sources_sha256(ui) != before


def test_a_moved_input_changes_the_hash(tmp_path):
    ui = a_ui(tmp_path)
    before = build.sources_sha256(ui)
    (ui / 'src' / 'main.ts').rename(ui / 'src' / 'start.ts')
    assert build.sources_sha256(ui) != before


def test_tests_and_lint_settings_are_not_inputs(tmp_path):
    ui = a_ui(tmp_path)
    before = build.sources_sha256(ui)
    (ui / 'tests').mkdir()
    (ui / 'tests' / 'app.test.ts').write_bytes(b'it()\n')
    (ui / 'eslint.config.js').write_bytes(b'export default []\n')
    assert build.sources_sha256(ui) == before
