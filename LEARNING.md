## Day 1 EOD
What I built today: Docker Compose: FastAPI + Postgres + pgvector extension. GET /health returns 200
What I learned today: abt docker compose format 
One decision I made and why: i chose pgvector over pinecone bcuz if i choose postgres i can use it fro vector search and store relational data

date :17 may 
## Day 2 EOD

What I built: POST /v1/onboard — takes 3 goals, calls OpenAI 
embeddings API, averages 3 vectors into one, stores in pgvector

What I learned: text-embedding-3-small outputs 1536 dimensions. 
Averaging vectors combines multiple goals into one query vector.

One decision I made: chose text-embedding-3-small over large 
because 5x cheaper, same dimensions, accuracy sufficient for feed

One thing that confused me: Docker caching old code — fixed with 
--no-cache flag
docker compose build --no-cache

## Day 3 EOD

What I built:
- reels table with HNSW index in init.sql
- seed_reels.py — seeds 12 reels with real OpenAI embeddings
- GET /v1/feed — returns top 10 reels by cosine similarity to user goals

What I learned:
- HNSW builds a layered graph, no training step needed
- IVFFlat groups into clusters, needs training step
- fetchone() returns a tuple — use [0] to get first column
- docker compose down -v wipes all data — only use when init.sql changes

One decision I made:
- chose HNSW over IVFFlat because reels are inserted in real time
- no training step = index works immediately on new inserts

## Day 4 EOD

What I built:
- Added search_vector column + GIN index to reels table
- Updated seed_reels.py to populate search_vector with tsvector
- GET /v1/feed now supports hybrid search with RRF
- query param optional — without it uses vector only

What I learned:
- tsvector: processed word index, stems words, removes stopwords
- tsquery: search query format, @@ operator matches tsvector
- GIN index: word lookup table, makes FTS fast
- RRF: merges two ranked lists using 1/(60+rank) formula
- Reels in both results get combined scores, rise to top

One decision I made:
- FTS only runs when query param provided
- Without query, pure vector search is faster and good enough
- Hybrid only needed when user actively searches

## Day 5 EOD

What I built:
- Redis cache for feed — cache-aside pattern, 5min TTL
added redis in requirment , and redis as new service in docker compose file .
it is checked if reel feed is present in cache for that user, if not then vector search done else retrieved from cache.
- POST /v1/tasks — creates task with embedding stored
- PATCH /v1/tasks/{id}/complete — marks task complete
- POST /v1/agent/context — semantic search on past completed tasks

What I learned:
- RAG: retrieve → augment → generate
- Redis cache-aside: check cache first, miss → DB → store in cache
- f-strings: f"feed:{user_id}" builds dynamic keys
- Foreign key constraint: user_id must exist in users table
- Monolith vs microservices — MotivAI is monolith for now

One decision I made:
- Used semantic search for agent context (not last 5)
- Reason: "30min run" query should find similar fitness tasks
- not unrelated tasks like "study Python"

client.embeddings.create()  →  converts text to vector
client.chat.completions.create()  →  generates text from prompt
client.audio.transcriptions.create()  →  converts audio to text

## Day 6 EOD

What I built:
- prompts/ library — agent_reaction.txt, reel_tagger.txt, onboard_summary.txt
- app/tasks.py — Celery task: Whisper → extract tags using GPT prompt → embed → store in DB
- Celery worker service in Docker Compose
- POST /v1/upload — async video processing pipeline : upload in temporary file path -> add title and return reel id -> call celery process_reel ->return reel id and file path 
- Shared named volume between api and worker for file passing : for temporary file path 

What I learned:
- Celery: task queue for background processing
- Why async: video processing takes 20-30s, can't block HTTP
- Dockerfile: FROM, WORKDIR, COPY, RUN, CMD explained
- Named volumes: shared storage between containers
- COPY app/ vs COPY prompts/ — relative paths in Dockerfile
- Whisper API: audio → text transcription
- client.chat.completions.create() for text generation

One decision I made:
- Save file to shared volume not pass as bytes to Redis
- Reason: video files are 10-100MB, Redis stores small data only
- File path (string) goes to Redis, file itself goes to shared volume

## Day 7 EOD

What structured output means:
Defining exact shape of API response using Pydantic models.
FastAPI validates automatically — wrong type = immediate error.

Why use Pydantic models for responses:
Catches missing fields early before they reach production.
Agent reads this data in Day 7 — wrong structure = agent crashes.

TaskContext model:
Defines shape of one past task — id, description, completed, created_at.

AgentContextResponse model:
Wraps list of TaskContext objects + user_id into one structured response.

json.dumps vs json.loads:
json.dumps: Python object → string (for storing/sending)
json.loads: string → Python object (for reading/receiving)

When MotivAI uses json.dumps:
Storing feed result in Redis — Redis only stores strings.

When MotivAI uses json.loads:
Reading feed result from Redis + reading GPT tag response.

## Day 8 EOD

### Why Render
Without Render:  app only works on your laptop
With Render:     app has a live URL anyone can access
                 https://motivai-ecjl.onrender.com
- Free tier available
- Supports Docker directly — no code changes needed
- Automatic redeploy when you push to GitHub
- Managed Postgres and Redis available

### What I deployed
3 services:
api     → FastAPI app (Web Service on Render)
db      → Postgres with pgvector (Render Postgres)
redis   → Redis cache + Celery broker (Upstash free tier)

Note: Celery worker not deployed yet .
Will add later.

### Steps I followed

1. Created Postgres on Render
   - New → PostgreSQL → motivai-db → Free plan
   - Copied External Database URL

2. Created Redis on Upstash (Render has no free Redis)
   - upstash.com → Create Database → motivai-redis
   - Region: ap-southeast-1 (closest to India)
   - Copied Redis URL (rediss://...)

3. Created Web Service on Render
   - New → Web Service → connected GitHub repo
   - Runtime: Docker
   - Added environment variables:
     OPENAI_API_KEY = my key
     DATABASE_URL   = Render Postgres URL
     REDIS_URL      = Upstash Redis URL

4. Ran init.sql on Render Postgres
   - Render Postgres starts empty — no tables
   - Had to run init.sql manually:
     psql <render-db-url> -f db/init.sql
   - This created: users, reels, tasks tables + HNSW + GIN indexes

5. Seeded reels on Render Postgres
   - seed_reels.py runs locally
   - Pointed it at Render DB temporarily
   - Seeded 52 reels with real OpenAI embeddings

6. Tested live URL
   - POST /v1/goals_embedding → returned user_id ✓
   - GET /v1/feed_return → returned 10 ranked reels ✓

### Key difference — local vs Render

Local Docker:
  DATABASE_URL = postgresql://postgres:postgres@db:5432/motivai
  "db" = Docker service name, works inside Docker network

Render:
  DATABASE_URL = postgresql://user:pass@host.render.com/dbname
  actual hostname, accessible from internet

### What's not deployed yet
- Celery worker (needs paid plan on Render)
- Will use Render Background Worker later
- For now upload pipeline only works locally

### Lesson learned
- init.sql doesn't run automatically on Render
  (unlike Docker which runs it on first startup)
- Must run it manually after creating Postgres
- Redis free tier removed from Render — use Upstash instead

## Day 9 EOD 

## Celery + Redis deep theory
Celery chains:
- split one big task into smaller linked tasks
- if step 2 fails → only step 2 retries
- .s() = task signature (reference without running)

Exponential backoff:
- countdown = 2 ** self.request.retries
- 1s, 2s, 4s, 8s between retries
- prevents hammering failing API

Dead letter queue:
- stores tasks that failed all retries
- lets you inspect failures and replay
- MotivAI: store in Redis list, inspect manually

Redis data structures:
- Strings:      simple cache, TTL
- Hashes:       store objects (user profile cache)
- Lists:        queues, notifications
- Sets:         unique items (seen reels per user)
- Sorted sets:  leaderboards (trending reels)

TTL: key expires automatically after N seconds
Eviction: allkeys-lru removes least recently used when memory full

## Day 10 EOD

## Object Storage + MinIO
Why object storage:
Videos are large binary files — Postgres stores structured data not binary.
/tmp/ is temporary — files deleted on container restart.
MinIO/S3 designed for large files, permanent storage, fast serving.

S3 vs MinIO:
S3 — Amazon's cloud object storage, pay per GB, managed by AWS.
MinIO — open source S3 clone, run yourself in Docker, free, same API.
Same Python code works for both — just change endpoint URL.

Presigned URL:
Temporary URL giving access to a private file for limited time.
Generated server-side — user gets URL valid for 1 hour then expires.
Production: private bucket + presigned URL = proper access control.
Local: public bucket used — presigned URL has hostname mismatch issue.

Multipart upload:
Splits large files into chunks, uploads in parallel — much faster.
MinIO Python client handles this automatically for files over 5MB.

Object key:
Path/name for file inside MinIO bucket.
We construct it: f"reels/{uuid.uuid4()}_{file.filename}"
Unique per upload — no files overwrite each other.

Named volume minio_data:
Stores all MinIO data — buckets, files, config.
Mounted at /data inside MinIO container.
Persists across docker compose down (not -v).

How MinIO fits in MotivAI upload flow:
Creator uploads video
↓
FastAPI reads file as bytes
↓
Uploads to MinIO (permanent) → object_key stored in DB
↓
Saves to /tmp/ (temporary) → for Celery/Whisper
↓
Celery processes: Whisper → GPT → embed → store
↓
os.remove() deletes /tmp/ file
↓
MinIO copy stays forever for playback

Redis — broker vs cache vs pub/sub:
Broker: passes messages between services — FastAPI → Redis → Celery
Cache: stores expensive results temporarily — feed result, TTL 5min
Pub/sub: broadcasts to multiple listeners — fire and forget

What I built today:
- MinIO service in Docker Compose with named volume
- Auto-create bucket on startup if not exists
- Upload reel to MinIO + /tmp/ simultaneously
- object_key column added to reels table
- GET /v1/reels/{id}/play returns URL for playback
- Postgres data persistence with named volume

Key decision:
- Two MinIO clients considered for presigned URL hostname fix
- Chose public bucket locally instead — simpler, avoids hostname mismatch
- Will use private bucket + proper presigned URLs on Render in week 8