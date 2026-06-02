# MotivAI

TikTok-style motivational reels personalized by your goals.

## Live URL
https://motivai-ecjl.onrender.com

## Stack
FastAPI · pgvector · Redis · Celery · MinIO · OpenAI · Docker · Render

## Features
- Personalized reel feed — hybrid search (vector + FTS + RRF)
- Redis cache-aside — 5min TTL, prevents repeated DB queries
- Async video pipeline — Whisper transcription → GPT moderation → GPT tagging → embed → store
- Object storage — MinIO for video files, presigned URLs for playback
- Redis Streams — task completion events, persistent, crash-safe
- Consumer groups — idempotency keys prevent duplicate agent reactions
- AI group matching — embed user goals, find similar groups via pgvector
- Group social feed — daily task summaries + agent reactions

## Endpoints
POST /v1/goals_embedding      — onboard user with 3 goals
GET  /v1/feed_return          — personalized reel feed (hybrid search)
POST /v1/upload_reel          — upload reel (async Celery pipeline)
GET  /v1/celery_status/{id}   — check upload processing status
GET  /v1/reels/{id}/play      — get playback URL
POST /v1/tasks                — create task with embedding
GET  /v1/tasks/{user_id}      — get all tasks for user
PATCH /v1/tasks/{id}/complete — complete task + fire Redis Stream event
POST /v1/agent/past_tasks     — semantic search on past completed tasks
POST /v1/groups/create        — create group with name + description
GET  /v1/groups/match         — AI match user goals to existing groups
POST /v1/groups/{id}/join     — join a group
GET  /v1/groups/{id}/members  — get group members
GET  /v1/groups/{id}/feed     — group activity feed
GET  /v1/admin/dlq            — monitor failed stream events

## Architecture Decisions

**pgvector over Pinecone:**
Keeps vectors + relational data in one DB. No second database to manage.

**Hybrid search (FTS + vector + RRF):**
Pure vector search misses exact keyword matches. RRF merges both ranked lists without needing weights.

**Celery over FastAPI BackgroundTasks:**
Separate process = isolated crashes, proper retries, Flower monitoring.

**Redis Streams over Pub/Sub:**
Streams persist events — agent worker crash doesn't lose task completion event.

**Idempotency keys:**
At-least-once delivery means duplicate events. SET NX prevents double reactions.

**MinIO over storing in Postgres:**
Videos are binary files — Postgres not designed for this. MinIO handles large files efficiently.

