-- The index's generation (issue #10, part C): one row, raised by every write of pages, so a running librarian notices a
-- change with one cheap query per call and loads the index again. And a work's count of ranked pages, as the librarian's
-- `works` tool reports it, kept with the work instead of counted again.
CREATE TABLE index_state (
    id         BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    generation BIGINT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL
);
INSERT INTO index_state (id, generation, changed_at) VALUES (TRUE, 0, now());

ALTER TABLE works ADD COLUMN pages INTEGER NOT NULL DEFAULT 0;
