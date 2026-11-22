-- The index (issue #10, part B): works, their pages, the pages' BM25 postings and the chunks' vectors. Derived data
-- only: every row is rebuilt from the readings and the stored vectors by `python -m backend.search.database.index_import`.

CREATE TABLE works (
    key            TEXT PRIMARY KEY,
    knowledge_base TEXT NOT NULL CHECK (knowledge_base IN ('free', 'licensed')),
    title          TEXT NOT NULL,
    licence        TEXT NOT NULL,
    route          TEXT NOT NULL,
    subject        TEXT,
    view_id        TEXT,
    edition        TEXT,
    year           INTEGER,
    kept_for       TEXT
);

-- A page as the librarian serves it: an open page, a hit, a citation. `ordinal` is its place in the librarian's order of
-- ranked pages, so a tie in score breaks as the in-memory ranking breaks it; `length` counts the words the ranking sees.
CREATE TABLE pages (
    id             BIGINT PRIMARY KEY,
    work           TEXT NOT NULL REFERENCES works (key) ON DELETE CASCADE,
    knowledge_base TEXT NOT NULL CHECK (knowledge_base IN ('free', 'licensed')),
    label          TEXT NOT NULL,
    line           INTEGER NOT NULL,
    line_end       INTEGER,
    path           TEXT NOT NULL,
    pdf            TEXT,
    printed        TEXT,
    section        TEXT,
    route          TEXT NOT NULL,
    reading_key    TEXT,
    searchable     BOOLEAN NOT NULL,
    text           TEXT NOT NULL,
    index_text     TEXT,
    length         INTEGER NOT NULL,
    ordinal        INTEGER NOT NULL,
    UNIQUE (work, label)
);
CREATE INDEX pages_ranked ON pages (ordinal) WHERE searchable;

-- One row per term and ranked page, with the term's count on it: BM25 is computed from these at query time, so a page's
-- change touches its own rows alone (the IDE's port, its tokenizer, K1, B and idf unchanged, decision 56.b).
CREATE TABLE postings (
    term    TEXT NOT NULL,
    page_id BIGINT NOT NULL REFERENCES pages (id) ON DELETE CASCADE,
    tf      INTEGER NOT NULL,
    PRIMARY KEY (term, page_id) INCLUDE (tf)
);
CREATE INDEX postings_page ON postings (page_id);

-- A chunk of the semantic search with its stored vector and the model that made it; the two knowledge bases are searched
-- apart and fused by rank (39.a), so each has an HNSW index of its own.
CREATE TABLE chunks (
    id             TEXT PRIMARY KEY,
    knowledge_base TEXT NOT NULL CHECK (knowledge_base IN ('free', 'licensed')),
    work           TEXT NOT NULL,
    text           TEXT NOT NULL,
    metadata       JSONB NOT NULL,
    model          TEXT NOT NULL,
    embedding      vector(1536) NOT NULL
);
CREATE INDEX chunks_work ON chunks (work);
CREATE INDEX chunks_free_hnsw ON chunks USING hnsw (embedding vector_cosine_ops) WHERE knowledge_base = 'free';
CREATE INDEX chunks_licensed_hnsw ON chunks USING hnsw (embedding vector_cosine_ops) WHERE knowledge_base = 'licensed';
