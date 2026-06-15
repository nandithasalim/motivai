# MotivAI

TikTok-style motivational reels personalized by your goals. AI agent reacts when you complete tasks — grounded in your actual history, not generic praise.

## Live URL
https://motivai-ecjl.onrender.com

## Stack
FastAPI · pgvector · Redis · Celery · MinIO · LangGraph · OpenAI · Docker · Render

## Architecture
User onboards with 3 goals
↓
Goals embedded → pgvector (averaged for feed, per-goal for group matching)
↓
User swipes feed → hybrid search (vector + FTS + RRF) → Redis cache 5min TTL
↓
User uploads reel → MinIO storage → Celery pipeline → Whisper → GPT moderation → embed
↓
User completes task → Redis Stream event → LangGraph agent
↓
Agent: retrieve_context → generate_reaction (Pydantic v2) → store in group_posts
↓
Group members see daily task summaries + AI reactions in feed

## Performance
- Feed p95 latency: ~50ms (Redis cache hit)
- Agent reaction latency: ~4s (GPT call + retrieval)
- Cost per reaction: ~$0.0003 (gpt-4o-mini)
- Estimated cost: ~₹2.30/user/month at 10 tasks/day
- RAGAS answer relevancy: 0.834
- LLM-judge encouraging: 4.0/5, specific: 4.4/5

## AI Features
- **LangGraph agent** — 3-node graph: retrieve_context → generate_reaction → store_reaction
- **Pydantic v2 structured output** — AgentReaction model with ToneEnum, field validators
- **Semantic cache** — cosine similarity on task embeddings, ~35% GPT call reduction
- **Model routing** — milestone streaks (7/14/30 days) → gpt-4o, regular days → gpt-4o-mini
- **Two-layer guardrails** — regex + embedding cosine classifier blocks prompt injection
- **RAGAS evals** — 25-row golden dataset, GPT-as-judge baseline scores
- **Langfuse observability** — traces every LLM call with latency, cost, tokens

## Features
- Personalized reel feed — hybrid search (vector + FTS + RRF)
- Redis cache-aside — 5min TTL, prevents repeated DB queries
- Async video pipeline — Whisper → GPT moderation → GPT tagging → embed → store
- Object storage — MinIO for video files, presigned URLs for playback
- Redis Streams — task completion events, persistent, crash-safe
- Consumer groups — idempotency keys prevent duplicate agent reactions
- AI group matching — embed user goals on the fly, find similar groups via pgvector
- Group social feed — completed tasks + agent reactions per member

## Endpoints
POST /v1/goals_embedding      — onboard user with goals
GET  /v1/feed_return          — personalized reel feed (hybrid search + Redis cache)
POST /v1/upload_reel          — upload reel (async Celery pipeline)
GET  /v1/celery_status/{id}   — check upload processing status
GET  /v1/reels/{id}/play      — get presigned playback URL
POST /v1/tasks                — create task with embedding
GET  /v1/tasks/{user_id}      — get all tasks for user
PATCH /v1/tasks/{id}/complete — complete task + fire Redis Stream event
POST /v1/agent/past_tasks     — semantic search on past completed tasks
POST /v1/groups/create        — create group (description embedded for matching)
GET  /v1/groups/match         — AI match user goals to existing groups
POST /v1/groups/{id}/join     — join a group
GET  /v1/groups/{id}/members  — group details + members
GET  /v1/groups/{id}/feed     — group activity feed
GET  /v1/admin/dlq            — monitor failed stream events
GET  /metrics                 — Prometheus metrics endpoint

## Architecture Decisions

**pgvector over Pinecone:**
Keeps vectors + relational data in one DB. No second database to manage. HNSW index for sub-millisecond ANN search.

**Hybrid search (FTS + vector + RRF):**
Pure vector search misses exact keyword matches. RRF merges both ranked lists without needing tuned weights.

**Celery over FastAPI BackgroundTasks:**
Separate process = isolated crashes, proper retries, exponential backoff, Flower monitoring.

**Redis Streams over Pub/Sub:**
Streams persist events — agent worker crash doesn't lose task completion event. Consumer groups ensure exactly-once processing.

**Idempotency keys (Redis SET NX):**
At-least-once delivery means duplicate events. SET NX prevents double reactions atomically.

**RAG over fine-tuning:**
User history changes daily — RAG always up to date. Fine-tuning can't personalize per user. See docs/adr/ADR-001.md.

**Model routing:**
Milestone streaks (7/14/30 days) → gpt-4o for higher quality reaction. Regular days → gpt-4o-mini. ~89% cost reduction.

**Semantic cache:**
Similar task descriptions return cached reactions. Cosine distance threshold 0.15. ~35% LLM call reduction.

## Observability
- Langfuse traces every LLM call — latency, cost, tokens, model used
- Prometheus /metrics endpoint — feed latency histogram, agent latency histogram
- RAGAS eval pipeline — automated quality measurement on golden dataset

## Testing
- pytest suite — content filter, model routing, injection detection
- GitHub Actions CI — runs pytest on every push to main
- 25-row golden dataset for regression testing

## Running locally
```bash
docker compose up -d
python3 seed_reels.py
curl -X POST http://localhost:8000/v1/goals_embedding \
  -H "Content-Type: application/json" \
  -d '{"name": "Your Name", "goals": ["fitness", "coding", "reading"]}'
```