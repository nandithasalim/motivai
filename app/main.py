from fastapi import FastAPI , HTTPException
from openai import OpenAI
from dotenv import load_dotenv
import numpy as np
import redis
import json
from sqlalchemy import create_engine, text
import os
from pydantic import BaseModel
load_dotenv()

redis_client = redis.from_url(os.getenv("REDIS_URL"))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
app = FastAPI()
engine = create_engine(os.getenv("DATABASE_URL"))

class OnboardRequest(BaseModel):
    goals: list[str]

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/v1/onboard")
async def onboard(request: OnboardRequest):
    if len(request.goals) != 3:
        raise HTTPException(status_code=400, detail="Exactly 3 goals required.")
    
    embeddings = []
    for goal in request.goals:
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=goal
        )
        embedding = response.data[0].embedding
        embeddings.append(embedding)
    
    averaged = np.mean(embeddings, axis=0).tolist()
    
    with engine.connect() as conn:
        result = conn.execute(
            text("INSERT INTO users (goal_embedding) VALUES (:embedding) RETURNING id"),
            {"embedding": str(averaged)}
        )
        conn.commit()
        user_id = result.fetchone()[0]
    return {"user_id": str(user_id)}

@app.get("/v1/feed")
async def get_feed(user_id: str, query: str = ""):
    with engine.connect() as conn:
        
        # get user's goal embedding
        user = conn.execute(
            text("SELECT goal_embedding FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        goal_embedding = user[0]

        cache_key = f"feed:{user_id}"  #redis reads only strings
        cached= redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
        
        # vector search — find reels closest to user goals
        vector_results = conn.execute(
            text("""
                SELECT id, title, summary, tags,
                ROW_NUMBER() OVER (ORDER BY embedding <=> :embedding) as rank
                FROM reels
                ORDER BY embedding <=> :embedding
                LIMIT 10
            """),
            {"embedding": str(goal_embedding)}
        ).fetchall()
        
        # FTS search — find reels matching exact keywords
        fts_results = []
        if query:
            fts_results = conn.execute(
                text("""
                    SELECT id, title, summary, tags,
                    ROW_NUMBER() OVER (
                        ORDER BY ts_rank(search_vector, 
                        to_tsquery('english', :query)) DESC
                    ) as rank
                    FROM reels
                    WHERE search_vector @@ to_tsquery('english', :query)
                    ORDER BY ts_rank(search_vector, 
                             to_tsquery('english', :query)) DESC
                    LIMIT 10
                """),
                {"query": query}
            ).fetchall()
        
        # RRF merge — combine both ranked lists
        rrf_scores = {}
        
        # add vector search scores
        for row in vector_results:
            reel_id = str(row[0])
            rank = row[4]
            rrf_score = 1 / (60 + rank)
            rrf_scores[reel_id] = {
                "score": rrf_score,
                "data": {
                    "id": reel_id,
                    "title": row[1],
                    "summary": row[2],
                    "tags": row[3]
                }
            }
        
        # add FTS scores — add to existing or create new
        for row in fts_results:
            reel_id = str(row[0])
            rank = row[4]
            rrf_score = 1 / (60 + rank)
            if reel_id in rrf_scores:
                # reel appeared in both — add scores together
                rrf_scores[reel_id]["score"] += rrf_score
            else:
                # reel only in FTS results
                rrf_scores[reel_id] = {
                    "score": rrf_score,
                    "data": {
                        "id": reel_id,
                        "title": row[1],
                        "summary": row[2],
                        "tags": row[3]
                    }
                }
        
        # sort by RRF score, return top 10
        sorted_ids = sorted(
            rrf_scores.keys(),
            key=lambda x: rrf_scores[x]["score"],
            reverse=True
        )[:10]
        
        final_result=[rrf_scores[id]["data"] for id in sorted_ids]
        redis_client.setex(cache_key, 300, json.dumps(final_result))
        return final_result