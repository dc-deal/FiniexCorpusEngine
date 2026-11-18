"""Sections → chunks: the size cap, the stable ids, and the citation fixed on every chunk.

The splitter is LangChain's `RecursiveCharacterTextSplitter` (lesson 3), applied inside each
section, so a chunk never spans two sections and always knows which one it belongs to.
`add_start_index` gives each piece's offset in the section, which is what maps a chunk of a
multi-page section back to the page it starts on.
"""

import functools
import hashlib
import json

import tiktoken
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.ingestion.sections import Section

# The course's starting point (lesson 3). Tuned against the evaluation in later phases.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

@functools.cache
def _encoding():
    """OpenAI's cl100k_base encoding, which text-embedding-3 uses, so a count here is what the API
    bills. Loaded on first use, not at import: on a cold cache tiktoken downloads its vocabulary
    (once, then cached), and a download at import time would run before any offline guard does."""
    return tiktoken.get_encoding('cl100k_base')


def splitting_config() -> dict:
    """Everything that changes the chunks. Part of a source's fingerprint, so changing any value
    re-indexes every source on the next build."""
    return {'splitter': 'RecursiveCharacterTextSplitter', 'chunk_size': CHUNK_SIZE,
            'chunk_overlap': CHUNK_OVERLAP}


def config_hash() -> str:
    return hashlib.sha256(json.dumps(splitting_config(), sort_keys=True).encode()).hexdigest()[:12]


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text))


def source_metadata(source: dict) -> dict:
    """The catalog fields every chunk of a source carries, for citation and filtering."""
    return {
        'source_id': source['id'],
        'source_title': source['title'],
        'authors': source['authors'],
        'shelf': source['shelf'],
        'format': source['format'],
        'licence': source['licence'],
        'licence_url': source['licence_url'],
    }


def chunk_sections(sections: list[Section], source: dict) -> list[Document]:
    """Split every section and attach the full citation to each piece.

    Args:
        sections: The sections of one source, from the PDF or HTML loader.
        source: The catalog entry of that source.

    Returns:
        LangChain documents with a stable `chunk_id` in their metadata:
        `<source id>:<section ordinal>:<chunk ordinal>`. None values are left out, because Chroma
        accepts only strings, numbers and booleans as metadata.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, add_start_index=True)
    base = source_metadata(source)
    chunks = []
    for section in sections:
        pieces = splitter.create_documents([section.text])
        for number, piece in enumerate(pieces):
            start = piece.metadata['start_index']
            pdf_page, printed_page = section.page_at(start)
            pdf_page_end, printed_page_end = section.page_at(start + max(len(piece.page_content) - 1, 0))
            route, reading_key = section.routes.get(pdf_page, (None, None))
            route_end, reading_key_end = section.routes.get(pdf_page_end, (None, None))
            metadata = {
                **base,
                'chunk_id': f'{section.id}:{number:03d}',
                'section_id': section.id,
                'chapter': section.chapter,
                'section': section.title,
                'heading_path': ' > '.join(section.heading_path),
                'pdf_page': pdf_page,
                'printed_page': printed_page,
                # A chunk that runs over a page boundary names the page it ends on too (decision 65.a)
                'pdf_page_end': pdf_page_end if pdf_page_end != pdf_page else None,
                'printed_page_end': printed_page_end if pdf_page_end != pdf_page else None,
                # How the text of its pages was made: a verified reading (with its key) or a text layer, and why (phase 5)
                'route': route,
                'reading_key': reading_key,
                'route_end': route_end if pdf_page_end != pdf_page else None,
                'reading_key_end': reading_key_end if pdf_page_end != pdf_page else None,
                'url': section.url,
                'anchor': section.anchor,
                'tokens': count_tokens(piece.page_content),
            }
            chunks.append(Document(page_content=piece.page_content,
                                   metadata={k: v for k, v in metadata.items() if v is not None}))
    return chunks
