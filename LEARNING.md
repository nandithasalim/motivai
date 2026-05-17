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