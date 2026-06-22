# MotivAI System Design — Scaling to 1M Users

## Current Architecture (MVP)
User → FastAPI → Redis Cache → pgvector (feed)

User → FastAPI → Celery → Whisper → GPT → MinIO (upload)

User → FastAPI → Redis Stream → LangGraph Agent → GPT → Postgres (task)

**Current capacity:** ~100 concurrent users, single server

---

## Bottlenecks at Scale

### 1. Database (pgvector)
**Problem:** Single Postgres instance, vector search slows at 10M+ reels
**Solution:**
- Read replicas for feed queries
- Partition reels table by category (fitness, coding, reading)
- pgvector HNSW index already handles 1M vectors efficiently
- At 10M+ → migrate to dedicated vector DB (Pinecone/Weaviate)

### 2. Feed Generation
**Problem:** Every feed request hits DB even with Redis cache
**Solution:**
- Pre-compute feeds for active users nightly (Celery Beat)
- CDN cache for popular reels metadata
- Cache hit rate target: >80% (currently ~60% with 5min TTL)

### 3. LangGraph Agent
**Problem:** GPT call takes 4s — 1000 concurrent completions = 4000s wait
**Solution:**
- Already async via Redis Streams — agent decoupled from API
- Scale agent workers horizontally (3-5 Celery workers)
- Semantic cache reduces GPT calls by ~35%
- Model routing saves 89% cost on regular days

### 4. Video Processing (Celery)
**Problem:** Whisper transcription takes 10-30s per reel
**Solution:**
- Celery autoscale based on queue depth
- Dedicated GPU worker for Whisper at scale
- Batch processing during off-peak hours

### 5. Object Storage
**Problem:** MinIO single node, no CDN
**Solution:**
- Swap to AWS S3 (one env var change — STORAGE_PROVIDER=s3)
- CloudFront CDN in front of S3
- Reels served from edge — p95 latency <100ms globally

---

## Scaled Architecture (1M Users)
Users → CloudFront CDN → Load Balancer

↓

FastAPI (3-5 instances)

/          |          

Redis          Postgres      S3 + CloudFront

(ElastiCache)   (RDS + read    (reels storage)

replicas)



Celery Workers (autoscale)

/        

Whisper        Agent Workers (3-5)

(GPU)          Redis Streams consumer group

---

## Cost at 1M Users
Current (100 users):

GPT reactions:    $0.0003 × 10 tasks/day × 100 users = $0.30/day

Embeddings:       $0.00002 × 10 × 100 = $0.02/day

Total:            ~$10/month
At 1M users (with optimizations):

Model routing:    90% gpt-4o-mini, 10% gpt-4o

Semantic cache:   35% reduction in GPT calls

Cost per user:    ~₹2.30/month

Total:            ~₹23,00,000/month ($27,000)

Revenue needed:   ₹3-5/user/month subscription covers costs

---

## Database Scaling

### pgvector at Scale
Current:  52 reels, 1536-dim HNSW index

1M reels: HNSW still performs well (~10ms p95)

10M reels: partition by category

fitness_reels table

coding_reels table

→ each partition has own HNSW index

→ query only relevant partition

### Redis at Scale
Current:  single Redis instance

At scale: Redis Cluster (6 nodes)

feed cache → node 1-2

streams    → node 3-4

semantic   → node 5-6

---

## API Scaling

### Stateless FastAPI
Current:  1 instance

At scale: 3-5 instances behind load balancer

All state in Redis/Postgres — not in memory

Any instance handles any request

Scale horizontally with zero code changes

### Rate Limiting
Redis counter per user:

SET rate:user123 0 EX 60

INCR rate:user123

If > 100 → return 429 Too Many Requests

---

## Reliability
Current:

Redis Streams: at-least-once delivery
Idempotency keys: exactly-once processing
Celery retries: exponential backoff
DLQ: failed events stored for replay

At scale additions:

Circuit breaker: if OpenAI down → serve cached reactions
Multi-region: ap-south-1 (Mumbai) primary, us-east-1 backup
SLO: 99.9% uptime, p95 feed latency <200ms


---

## What I Would Build Next

Celery Beat — nightly group posts (midnight auto-share)
Grafana dashboard — p95 latency, cost per user, cache hit rate
A/B testing framework — test prompt versions on % of users
Push notifications — when group member completes task
React Native app — iOS + Android