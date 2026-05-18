from fastapi import FastAPI , HTTPException
from openai import OpenAI
from dotenv import load_dotenv
import numpy as np
from sqlalchemy import create_engine, text
import os
from pydantic import BaseModel
load_dotenv()


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
async def get_feed(user_id: str):
    with engine.connect() as conn:
        # 1. get user's goal embedding
        user = conn.execute(
            text("SELECT goal_embedding FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        goal_embedding = user[0]
        
        # 2. query reels by cosine similarity
        result = conn.execute(
            text("SELECT id, title, summary, tags FROM reels ORDER BY embedding <=> :goal_embedding LIMIT 10"),
            {"goal_embedding": str(goal_embedding)}
        )
        
        # 3. return as list of dicts
        reels = result.fetchall()
        return [
            {
                "id": str(row[0]),
                "title": row[1],
                "summary": row[2],
                "tags": row[3]
            }
            for row in reels
        ]