CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE users(
    id UUID PRIMARY KEY  DEFAULT gen_random_uuid(),
    goals TEXT[] ,
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
);

CREATE TABLE groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON groups USING hnsw(embedding vector_cosine_ops)
WITH (m=16, ef_construction=64);

CREATE TABLE group_members (
    group_id UUID REFERENCES groups(id),
    user_id UUID REFERENCES users(id),
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (group_id, user_id)
);

CREATE TABLE group_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID REFERENCES groups(id),
    user_id UUID REFERENCES users(id),
    completed_tasks TEXT[],    
    uncompleted_tasks TEXT[],   
    agent_reaction TEXT,       
    post_date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);