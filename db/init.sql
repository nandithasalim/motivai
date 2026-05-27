CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE users(
    id UUID PRIMARY KEY  DEFAULT gen_random_uuid(),
    goal_embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE reels(
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    summary TEXT ,
    tags TEXT[] ,
    object_key TEXT,
    flagged BOOLEAN DEFAULT FALSE,
    embedding vector(1536),
    search_vector tsvector,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON reels USING hnsw(embedding vector_cosine_ops) WITH(m=16, ef_construction=64);

CREATE INDEX on reels USING gin(search_vector);

CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    description TEXT NOT NULL,
    embedding vector(1536),
    completed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
)