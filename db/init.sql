CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE users(
    id UUID PRIMARY KEY  DEFAULT gen_random_uuid(),
    goal_embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE reels(
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    tags TEXT[] NOT NULL,
    embedding vector(1536),
    search_vector tsvector,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON reels USING hnsw(embedding vector_cosine_ops) WITH(m=16, ef_construction=64);

CREATE INDEX on reels USING gin(search_vector);