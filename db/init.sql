CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE users(
    id UUID PRIMARY KEY  DEFAULT gen_random_uuid(),
    goal_embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);