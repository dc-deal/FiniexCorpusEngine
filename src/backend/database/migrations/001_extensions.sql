-- The extensions the index needs (issue #10): pgvector for the chunks' vectors. The tables follow in their own migration
-- with part B, so this one is the runner's first and smallest step.
CREATE EXTENSION IF NOT EXISTS vector;
