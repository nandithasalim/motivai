from fastapi import FastAPI , HTTPException
from openai import OpenAI
from dotenv import load_dotenv
import numpy as np
import redis
import json
from sqlalchemy import create_engine, text
import os
from pydantic import BaseModel
from fastapi import UploadFile, File
import shutil
import uuid
from reels_celery import process_reel
from celery.result import AsyncResult
load_dotenv()
from minio import Minio
from minio.error import S3Error
import io
from datetime import timedelta
from datetime import datetime

# add MinIO client below your other clients
minio_client = Minio(
    os.getenv("MINIO_ENDPOINT"),
    access_key=os.getenv("MINIO_ACCESS_KEY"),
    secret_key=os.getenv("MINIO_SECRET_KEY"),
    secure=False  # no HTTPS locally
)
# auto-create bucket if not exists
bucket_name = os.getenv("MINIO_BUCKET")
if not minio_client.bucket_exists(bucket_name):
    minio_client.make_bucket(bucket_name)

redis_client = redis.from_url(os.getenv("REDIS_URL"))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
app = FastAPI()
engine = create_engine(os.getenv("DATABASE_URL"))

class OnboardRequest(BaseModel):
    goals: list[str]
@app.post("/v1/goals_embedding")
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

@app.get("/v1/feed_return")
async def get_feed(user_id: str, query: str = ""):
    #checks if feed is in redis cache, if yes return, if no compute and store in redis before returning
    cache_key = f"feed:{user_id}"  #redis reads only strings
    cached= redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    
    with engine.connect() as conn:
        # get user's goal embedding
        user = conn.execute(
            text("SELECT goal_embedding FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        goal_embedding = user[0]
        
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
        if final_result:
            redis_client.setex(cache_key, 300, json.dumps(final_result)) # store in redis for 5 mins
        return final_result
    

@app.post("/v1/upload_reel")
async def upload_reel(title: str, file: UploadFile = File(...)):
    # 1. read file content
    file_content = await file.read()  # read file as bytes
    file_size = len(file_content)
    object_key = f"reels/{uuid.uuid4()}_{file.filename}"
    
    # 2. upload to MinIO
    minio_client.put_object(
        os.getenv("MINIO_BUCKET"),
        object_key,
        io.BytesIO(file_content), # MinIO expects stream for file uploads, so we wrap bytes in BytesIO
        length=file_size,
        content_type=file.content_type
    )
    # 3. save to /tmp/ for Celery processing
    file_path = f"/tmp/{uuid.uuid4()}_{file.filename}"
    with open(file_path, "wb") as buffer:  # wb as we are writing non text data (binary mode)
        buffer.write(file_content)
    
    # 4. create reel record in DB with object key
    with engine.connect() as conn:
        reel_id = conn.execute(
            text("INSERT INTO reels (title, object_key) VALUES (:title, :object_key) RETURNING id"),
            {"title": title, "object_key": object_key}
        ).fetchone()[0]
        conn.commit()
    
    # 5. send to Celery
    task = process_reel.delay(str(reel_id), file_path)
    
    return {"task_id": task.id, "reel_id": str(reel_id), "object_key": object_key} # task.id is celery id 


@app.get("/v1/celery_status/{task_id}")
async def get_upload_status(task_id: str):
    task = AsyncResult(task_id, app=process_reel.app)  #to check status of celery task
    return {"status": task.status}   


@app.get("/v1/reels/{reel_id}/play")
async def get_reel_url(reel_id: str):
    with engine.connect() as conn:
        reel = conn.execute(
            text("SELECT object_key FROM reels WHERE id = :reel_id"),
            {"reel_id": reel_id}
        ).fetchone()
        
        if not reel:
            raise HTTPException(status_code=404, detail="Reel not found")
        
        object_key = reel[0]
        
        if not object_key:
            raise HTTPException(status_code=404, detail="No file uploaded for this reel")
    
    # generate using internal client (minio:9000)
    url = minio_client.presigned_get_object(
        os.getenv("MINIO_BUCKET"),
        object_key,
        expires=timedelta(hours=1)
    )
    
    # replace internal hostname with localhost for browser access
    url = url.replace("http://minio:9000", "http://localhost:9000")

    
    return {"url": url, "expires_in": "1 hour"}

class TaskRequest(BaseModel):
    user_id: str
    description: str
    
@app.post("/v1/tasks")
async def create_task(request: TaskRequest):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=request.description
    )
    embedding = response.data[0].embedding
    with engine.connect() as conn:
        id=conn.execute(text(
            """INSERT INTO tasks(user_id,description,embedding) VALUES (:user_id,:description,:embedding) RETURNING id"""),
            {"user_id":request.user_id,"description":request.description,"embedding": str(embedding)}
        ).fetchone()[0]
        conn.commit()
    return {"task_id":id}

class AgentContextRequest(BaseModel):
    user_id: str
    task_id: str
class TaskContext(BaseModel):
    id: str
    description: str
    completed: bool
    created_at: str

class AgentContextResponse(BaseModel):
    user_id: str
    past_tasks: list[TaskContext]

@app.post("/v1/agent/past_tasks")
async def get_agent_context(request: AgentContextRequest):
    
    with engine.connect() as conn:
        # get embedding of current task
        task = conn.execute(
            text("SELECT embedding FROM tasks WHERE id = :task_id"),
            {"task_id": request.task_id}
        ).fetchone()

        current_embedding = task[0] 
        # find top 5 similar past completed tasks
        results = conn.execute(
            text("""
                SELECT id, description, completed, created_at
                FROM tasks
                WHERE user_id = :user_id 
                AND completed = TRUE
                AND embedding IS NOT NULL
                ORDER BY embedding <=> :embedding
                LIMIT 5
            """),
            {
                "user_id": request.user_id,
                "embedding": str(current_embedding)
            }
        ).fetchall()
        
        tasks=[
            TaskContext(
                id =str(row[0]),
                description= row[1],
                completed= row[2],
                created_at= str(row[3])
            )
            for row in results
        ]
        return AgentContextResponse(user_id=request.user_id, past_tasks=tasks)
    

@app.patch("/v1/tasks/{task_id}/complete")
async def complete_task(task_id: str, user_id: str):
    with engine.connect() as conn:
        # get task description
        task = conn.execute(
            text("SELECT description FROM tasks WHERE id = :task_id"),
            {"task_id": task_id}
        ).fetchone()
        
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # mark complete in DB
        conn.execute(
            text("UPDATE tasks SET completed = TRUE WHERE id = :task_id"),
            {"task_id": task_id}
        )
        conn.commit()
    
    # fire Redis Stream event
    redis_client.xadd("task_completed", {
        "user_id": user_id,
        "task_id": task_id,
        "description": task[0],
        "timestamp": str(datetime.now())
    })
    
    return {"status": "completed"}


