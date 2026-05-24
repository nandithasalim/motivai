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

