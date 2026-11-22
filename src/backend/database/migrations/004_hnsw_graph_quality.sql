-- The semantic search's HNSW indexes built again with a wider construction search (issue #10, part C2). A question sits
-- far from every chunk (cosine distance 0.4 to 0.8), where a walk through a graph built with pgvector's default
-- ef_construction of 64 lost its way: on 104 real questions, recall@10 against an exact search was 0.978 for the free
-- base, below Chroma's 0.995, and one question found none of its exact ten. Built with 200, measured in a scratch
-- database on the same questions at ef_search 400: free 0.996, licensed 0.999 (Chroma 0.995 and 0.996), 6.5 and 12.2 ms
-- a query, about 140 s to build both. m = 24 gained 0.002 for the free base at half again the build time and a larger
-- index. The graph is held in memory while it is built, so it is built at once rather than spilled to disk.
SET LOCAL maintenance_work_mem = '1GB';

DROP INDEX chunks_free_hnsw;
DROP INDEX chunks_licensed_hnsw;
CREATE INDEX chunks_free_hnsw ON chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 200)
    WHERE knowledge_base = 'free';
CREATE INDEX chunks_licensed_hnsw ON chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 200)
    WHERE knowledge_base = 'licensed';
