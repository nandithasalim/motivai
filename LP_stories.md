# Leadership Principle Stories — MotivAI

## Dive Deep
**Situation:** Building the feed algorithm for MotivAI.
**Task:** Return personalized reels matching user goals.
**Action:** Researched pure vector search vs hybrid. Found pure vector misses exact keyword matches. Studied RRF (Reciprocal Rank Fusion) to merge ranked lists without needing tuned weights. Chose HNSW over IVFFlat — no training step needed, works with real-time inserts.
**Result:** Feed returns semantically relevant AND keyword-matched reels. p95 latency ~50ms with Redis cache.

## Invent and Simplify
**Situation:** Agent reactions were generic — "Great job! Keep going!"
**Task:** Make reactions personalized to user's actual history.
**Action:** Built RAG pipeline — retrieve top 5 similar past tasks using pgvector semantic search, inject into GPT prompt. Added Pydantic v2 structured output with ToneEnum to ensure consistent reaction format.
**Result:** LLM-judge scores: encouraging 4.0/5, specific 4.4/5. Reactions reference actual user history.

## Bias for Action
**Situation:** Never built async pipeline before starting MotivAI.
**Task:** Video processing pipeline needed to handle 10-30s transcription without blocking API.
**Action:** Learned Celery + Redis in 2 days, shipped working pipeline with Whisper transcription, GPT moderation, embedding — all async with retries and exponential backoff.
**Result:** Upload endpoint returns in <100ms. Processing happens in background. Users get instant response.

## Frugality
**Situation:** Every agent reaction calls GPT — costs money at scale.
**Task:** Reduce cost without sacrificing quality.
**Action:** Built model routing (milestone streaks → gpt-4o, regular days → gpt-4o-mini), semantic cache (cosine similarity, 35% call reduction), token budgeting (max_tokens=200).
**Result:** Estimated ₹2.30/user/month at 10 tasks/day. Pure gpt-4o would be 15x more expensive.

## Customer Obsession
**Situation:** LLM output could contain harmful or inappropriate content.
**Task:** Ensure reactions are always safe for users.
**Action:** Built two-layer guardrail — regex pattern matching + embedding cosine classifier against safe/unsafe centroids. Output validator with content filter and fallback reaction.
**Result:** Prompt injection blocked at input. Inappropriate reactions caught at output. Users always see safe content.