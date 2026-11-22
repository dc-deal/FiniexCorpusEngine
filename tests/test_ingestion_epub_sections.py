"""The EPUB route (decision 123.a): the spine in reading order, cut at headings, images kept where they stand."""

import zipfile

from backend.ingestion.clean_sections import epub_sections
from backend.ingestion.clean_sections.epub_sections import IMAGE_MARK, load_epub_sections

CONTAINER = ('<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
             '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')


def package(nav: bool = True) -> str:
    navigation = ('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>' if nav else
                  '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
    return ('<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata '
            'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>An Invented Book</dc:title></metadata><manifest>'
            f'{navigation}<item id="c1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="c2" href="text/ch%202.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="note" href="text/note.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="img" href="images/eq.png" media-type="image/png"/></manifest>'
            '<spine><itemref idref="c1"/><itemref idref="note" linear="no"/><itemref idref="c2"/></spine></package>')


NAV = ('<html xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol>'
       '<li><a href="text/ch1.xhtml">Chapter One</a></li><li><a href="text/ch%202.xhtml#start">Chapter Two</a></li>'
       '</ol></nav></body></html>')
NCX = ('<?xml version="1.0"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap>'
       '<navPoint id="p1"><navLabel><text>Chapter One</text></navLabel><content src="text/ch1.xhtml"/></navPoint>'
       '<navPoint id="p2"><navLabel><text>Chapter Two</text></navLabel><content src="text/ch%202.xhtml#start"/></navPoint>'
       '</navMap></ncx>')
CHAPTER_ONE = ('<html><body><h1>Chapter One</h1><p>The return is <img src="../images/eq.png" alt="eq1"/> per year.</p>'
               '<div class="tx">A paragraph set as a div.</div><div class="figure"><img src="../images/eq.png" alt=""/></div>'
               '<h2 id="sub">A Subsection</h2><p>Its text.</p></body></html>')
CHAPTER_TWO = '<html><body><p id="start">A chapter without a heading of its own.</p></body></html>'
NOTE = '<html><body><p>A note outside the reading order.</p></body></html>'


def an_epub(tmp_path, nav: bool = True):
    path = tmp_path / 'invented_book.epub'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('mimetype', 'application/epub+zip')
        archive.writestr('META-INF/container.xml', CONTAINER)
        archive.writestr('OEBPS/content.opf', package(nav))
        archive.writestr('OEBPS/nav.xhtml' if nav else 'OEBPS/toc.ncx', NAV if nav else NCX)
        archive.writestr('OEBPS/text/ch1.xhtml', CHAPTER_ONE)
        archive.writestr('OEBPS/text/ch 2.xhtml', CHAPTER_TWO)
        archive.writestr('OEBPS/text/note.xhtml', NOTE)
        archive.writestr('OEBPS/images/eq.png', b'\x89PNG')
    return path


def test_the_spine_is_read_in_order_cut_at_headings_and_named_by_the_navigation(tmp_path):
    sections = load_epub_sections(an_epub(tmp_path), 'invented')
    assert [item.section.heading_path for item in sections] == [['Chapter One'], ['Chapter One', 'A Subsection'], ['Chapter Two']]
    assert [item.section.ordinal for item in sections] == [0, 1, 2]
    assert sections[1].section.url == 'invented_book.epub/OEBPS/text/ch1.xhtml#sub'
    assert sections[2].section.text == 'A chapter without a heading of its own.'  # its label from the navigation, its file's space unquoted
    assert all('outside the reading order' not in item.section.text for item in sections)  # linear="no" is left out


def test_a_paragraph_set_as_a_div_is_read(tmp_path):
    assert 'A paragraph set as a div.' in load_epub_sections(an_epub(tmp_path), 'invented')[0].section.text


def test_an_image_keeps_its_place_as_a_mark_and_is_listed_with_its_file(tmp_path):
    # 18 Nov: in several books the formulas are images; a route of text alone would lose them without a word
    first = load_epub_sections(an_epub(tmp_path), 'invented')[0]
    assert first.section.text.count(IMAGE_MARK) == 2 and f'The return is {IMAGE_MARK} per year.' in first.section.text
    assert [(image.href, image.alt, image.inline) for image in first.images] == [
        ('OEBPS/images/eq.png', 'eq1', True), ('OEBPS/images/eq.png', '', False)]


def test_the_search_server_serves_an_epub_by_section_and_never_ranks_by_its_image_marks(tmp_path, monkeypatch):
    from backend.search import search_server

    pages = search_server.epub_pages('invented', an_epub(tmp_path), [])
    assert [(page.page, page.route, page.section) for page in pages] == [
        ('s1', 'epub, parsed by section', 'Chapter One'), ('s2', 'epub, parsed by section', 'Chapter One > A Subsection'),
        ('s3', 'epub, parsed by section', 'Chapter Two')]
    assert IMAGE_MARK in pages[0].text and 'image' not in pages[0].words


def test_an_epub_serves_its_legacy_work_and_a_stand_in_serves_only_when_the_list_names_its_work(tmp_path, monkeypatch):
    # the operator, 22 Nov: a stand-in EPUB of a listed work serves it; one the list does not name stays beside it
    from backend.search import search_server

    for name in ('book_of_a.epub', 'new_book.epub', 'old_book__replacement.epub', 'other_book__replacement.epub',
                 'book_of_b.pdf'):
        (tmp_path / name).write_bytes(b'')
    monkeypatch.setattr(search_server, 'LICENSED_ARCHIVE', tmp_path)
    monkeypatch.setattr(search_server, 'stand_in_rule', lambda: ('__replacement', ['old']))
    found = search_server.licensed_epubs({'a': 'book_of_a', 'b': 'book_of_b', 'old': 'old_book', 'other': 'other_book'})
    assert {key: path.name for key, path in found.items()} == {
        'a': 'book_of_a.epub', 'new_book': 'new_book.epub', 'old': 'old_book__replacement.epub'}


def test_an_epub_2_book_is_named_by_its_ncx(tmp_path):
    sections = load_epub_sections(an_epub(tmp_path, nav=False), 'invented')
    assert [item.section.heading_path[0] for item in sections] == ['Chapter One', 'Chapter One', 'Chapter Two']


def test_the_route_is_versioned():
    assert epub_sections.LOADER_VERSION >= 1
