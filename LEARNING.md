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

