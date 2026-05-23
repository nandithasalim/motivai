## Day 5 — System design zoom-out

Why Redis cache instead of hitting Postgres every time:
Hitting Postgres with 1M users is slow. Postgres can only 
handle a limited number of connections at once. Redis is 
in-memory so reads are 100x faster.

Cache-aside pattern:
Check Redis first. If data is there (cache hit) return it 
immediately. If not (cache miss) query Postgres, store 
result in Redis, return result.

TTL — why 5 minutes:
Cache forever means new reels never appear in feed. 
Cache for 1 second gives no benefit — almost every 
request still hits Postgres. 5 minutes is the balance.

What happens when cache expires:
After 5 minutes Redis deletes the cached feed. Next 
request for that user misses cache, hits Postgres, 
gets fresh results, stores in Redis again.

At 1M users, how much does Redis help:
If 90% of requests hit cache, only 10% hit Postgres.
1000 simultaneous users → only 100 hit Postgres instead 
of 1000. Postgres stays healthy.

## Day 5 — AI vocab

RAG — Retrieval Augmented Generation:
Retrieve relevant data from DB → Augment the prompt with 
that data → Generate response grounded in real facts.
MotivAI uses RAG to give agent real user history before 
generating reactions.

Grounding:
Providing real facts to LLM so it doesn't hallucinate.
In MotivAI — agent reads user's actual past tasks before 
reacting. Response is grounded in real data not made up.

Context window:
Maximum amount of text LLM can read in one call.
GPT-4o: 128k tokens. If you stuff too much retrieved 
data into prompt you exceed the limit or confuse the model.