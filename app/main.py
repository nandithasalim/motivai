# all imports first
import os
import json
import uuid
import time
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Response
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from openai import OpenAI
from sqlalchemy import create_engine, text
from pydantic import BaseModel
from celery.result import AsyncResult
from middleware import GuardrailMiddleware
from metrics import requests_total, feed_latency
from guardrails import check_injection
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from reels_celery import process_reel
from storage import get_file_url, ensure_bucket_exists
import redis
import numpy as np
from zoneinfo import ZoneInfo
# then load_dotenv
load_dotenv()



# then app setup
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all for now
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GuardrailMiddleware)
# add MinIO client below your other clients


redis_client = redis.from_url(os.getenv("REDIS_URL"))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

engine = create_engine(
    os.getenv("DATABASE_URL")
)

@app.on_event("startup")
async def startup():
    ensure_bucket_exists()

class OnboardRequest(BaseModel):
    name: str
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
    text("INSERT INTO users (name, goal_embedding, goals) VALUES (:name, :embedding, :goals) RETURNING id"),
    {
        "name": request.name,
        "embedding": str(averaged),
        "goals": request.goals
    }
)
        conn.commit()
        user_id = result.fetchone()[0]
    return {"user_id": str(user_id)}

def reject_if_injection(*texts):
    for t in texts:
        if t and check_injection(t):
            raise HTTPException(status_code=400, detail="Invalid input detected")
        
@app.get("/v1/feed_return")
def get_feed(user_id: str, query: str = ""):
    requests_total.labels(endpoint="feed").inc()
    start = time.time()
    #checks if feed is in redis cache, if yes return, if no compute and store in redis before returning
    cache_key = f"feed:{user_id}:{query.strip().lower()}"  #redis reads only strings
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
        feed_latency.observe(time.time() - start)
        return final_result  
    

@app.post("/v1/upload_reel")
def upload_reel(title: str, file: UploadFile = File(...)):
    reject_if_injection(title)
    # 1. read file content
    file_content = file.file.read()  # read file as bytes (sync: this endpoint runs in a thread) # read file as bytes
    object_key = f"reels/{uuid.uuid4()}_{file.filename}"
    
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
def get_upload_status(task_id: str):
    task = AsyncResult(task_id, app=process_reel.app)  #to check status of celery task
    return {"status": task.status}   


@app.get("/v1/reels/{reel_id}/play")
def get_reel_url(reel_id: str):
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
    
    url = get_file_url(object_key)
    return {"url": url, "expires_in": "1 hour"}

class TaskRequest(BaseModel):
    user_id: str
    description: str
    
@app.post("/v1/tasks")
def create_task(request: TaskRequest):
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
def get_agent_context(request: AgentContextRequest):
    
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
def complete_task(task_id: str, user_id: str, completed: bool = True):
    with engine.connect() as conn:
        updated = conn.execute(
            text("""
                UPDATE tasks SET completed = :completed
                WHERE id = :task_id AND user_id = :user_id
                RETURNING id
            """),
            {"completed": completed, "task_id": task_id, "user_id": user_id}
        ).fetchone()
        if not updated:
            raise HTTPException(status_code=404, detail="Task not found")
        conn.commit()
    return {"status": "completed" if completed else "pending"}


@app.get("/v1/tasks/{user_id}")
def get_tasks(user_id: str):
    with engine.connect() as conn:
        tasks = conn.execute(
            text("SELECT id, description, completed, created_at FROM tasks WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchall()
        return [
    {
        "id": str(row[0]),
        "description": row[1],
        "completed": row[2],
        "created_at": str(row[3])
    }
    for row in tasks
    ]

class GroupCreateRequest(BaseModel):
    user_id: str
    name: str
    description: str

@app.post("/v1/groups/create")
def create_group(request: GroupCreateRequest):
    response= client.embeddings.create(
        model="text-embedding-3-small",
        input=request.description
    )
    embedding = response.data[0].embedding
    with engine.connect() as conn:
        group_id = conn.execute(
            text("INSERT INTO groups (name, description, embedding) VALUES (:name, :description, :embedding) RETURNING id"),
            {"name": request.name, "description": request.description, "embedding": str(embedding)}
        ).fetchone()[0]
        # add creator as member
        conn.execute(
            text("INSERT INTO group_members (group_id, user_id) VALUES (:group_id, :user_id)"),
            {"group_id": group_id, "user_id": request.user_id}
        )
        conn.commit()
    return {"group_id": str(group_id)}

@app.get("/v1/groups/match")
def match_groups(user_id: str):
    seen_ids = set()
    groups = []
    with engine.connect() as conn:
        goals = conn.execute(
            text("SELECT goals FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]

        # one API call for all goals
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=goals
        )
        embeddings = [item.embedding for item in response.data]

        # loop through each goal embedding
        for embedding in embeddings:
            results = conn.execute(
                text("""
                    SELECT id, name, description
                    FROM groups
                    WHERE embedding <=> :embedding < 0.8
                    ORDER BY embedding <=> :embedding
                    LIMIT 3
                """),
                {"embedding": str(embedding)}
            ).fetchall()

            for row in results:
                group_id = str(row[0])
                if group_id not in seen_ids:
                    seen_ids.add(group_id)
                    groups.append({
                        "id": group_id,
                        "name": row[1],
                        "description": row[2]
                    })
    return {"matched_groups": groups}


@app.post("/v1/groups/{group_id}/join")
def join_group(group_id: str, user_id: str):
    with engine.connect() as conn:
        conn.execute(
        text("INSERT INTO group_members (group_id, user_id) VALUES (:group_id, :user_id)"),
       {"group_id": str(group_id), "user_id": user_id}
    )
        conn.commit()    
    return {"status": "joined"}
        
@app.get("/v1/groups/{group_id}/members")
def get_group_members(group_id: str):
    with engine.connect() as conn:
        members = conn.execute(
            text("""
                SELECT g.name,g.description,gm.user_id
                FROM group_members gm 
                JOIN groups g ON g.id = gm.group_id
                WHERE g.id = :group_id
            """),
            {"group_id": group_id}
        ).fetchall()
    return [
    {
        "group_name": row[0],
        "description": row[1],
        "user_id": str(row[2])
    }
    for row in members
]
      
@app.get("/v1/groups/{group_id}/feed")
def get_group_feed(group_id: str):
    # check cache first
    cache_key = f"group_feed:{group_id}"
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # cache miss — fetch from DB
    for attempt in range(3):
        try:
            with engine.connect() as conn:
                posts = conn.execute(
                    text("""
                        SELECT gp.id, gp.user_id, u.name, gp.completed_tasks, 
                               gp.uncompleted_tasks, gp.agent_reaction, gp.created_at
                        FROM group_posts gp
                        JOIN users u ON gp.user_id = u.id
                        WHERE gp.group_id = :group_id
                        ORDER BY gp.created_at ASC
                    """),
                    {"group_id": group_id}
                ).fetchall()
                
                result = {"posts": [
                    {
                        "id": str(row[0]),
                        "user_id": str(row[1]),
                        "user_name": row[2],
                        "completed_tasks": row[3],
                        "uncompleted_tasks": row[4],
                        "agent_reaction": row[5],
                        "created_at": str(row[6])
                    }
                    for row in posts
                ]}
                
                # store in cache until new post arrives (24 hours max)
                redis_client.setex(cache_key, 86400, json.dumps(result))
                
                return result
        except Exception:
            if attempt == 2:
                raise
            engine.dispose()
            continue

@app.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


# one timezone for the whole app (simplification: per-user timezones can come later)
APP_TZ = ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Kolkata"))

@app.post("/v1/groups/{group_id}/post")
def post_to_group(
    group_id: str,
    user_id: str,
    completed_tasks: list[str],
    uncompleted_tasks: list[str] = [],
    completed_task_ids: list[uuid.UUID] = [],
    uncompleted_task_ids: list[uuid.UUID] = [],
):  
    reject_if_injection(*completed_tasks, *uncompleted_tasks)
    today = datetime.now(APP_TZ).date()   # the user's day, not the server's (UTC) day
    with engine.connect() as conn:
        post_id = conn.execute(
            text("""
                INSERT INTO group_posts (
                    group_id, user_id,
                    completed_tasks, uncompleted_tasks,
                    completed_task_ids, uncompleted_task_ids,
                    post_date
                )
                VALUES (
                    :group_id, :user_id,
                    :completed_tasks, :uncompleted_tasks,
                    CAST(:completed_task_ids AS uuid[]),
                    CAST(:uncompleted_task_ids AS uuid[]),
                    :today
                )
                RETURNING id
            """),
            {
                "group_id": group_id,
                "user_id": user_id,
                "completed_tasks": completed_tasks,
                "uncompleted_tasks": uncompleted_tasks,
                "completed_task_ids": [str(i) for i in completed_task_ids],
                "uncompleted_task_ids": [str(i) for i in uncompleted_task_ids],
                "today": today,
            }
        ).fetchone()[0]

        # streak = days in a row the user sent a post. ONE statement checks and updates,
        # so simultaneous posts cannot both add 1.
        conn.execute(
            text("""
                UPDATE users SET
                    streak_count = CASE
                        WHEN last_post_date = CAST(:today AS date)     THEN streak_count      -- 2nd post today: no change
                        WHEN last_post_date = CAST(:today AS date) - 1 THEN streak_count + 1  -- posted yesterday: continue
                        ELSE 1                                                                -- first post, or missed a day
                    END,
                    last_post_date = CAST(:today AS date)
                WHERE id = :user_id
            """),
            {"today": today, "user_id": user_id}
        )
        conn.commit()

    # trigger the agent ONCE for the whole post. It reads the task ids from the
    # group_posts row, so only the post id travels in the event.
    redis_client.xadd("task_completed", {
        "user_id": user_id,
        "post_id": str(post_id),
        "description": ", ".join(completed_tasks),
        "group_id": group_id,
        "timestamp": str(datetime.now())
    })
    redis_client.delete(f"group_feed:{group_id}")
    return {"post_id": str(post_id)}

@app.get("/v1/groups/all")
def get_all_groups():
    for attempt in range(3):
        try:
            with engine.connect() as conn:
                groups = conn.execute(
                    text("SELECT id, name, description FROM groups ORDER BY created_at DESC")
                ).fetchall()
                return {"groups": [
                    {"id": str(g[0]), "name": g[1], "description": g[2]}
                    for g in groups
                ]}
        except Exception:
            if attempt == 2:
                raise
            engine.dispose()

@app.get("/v1/groups/{group_id}/stream")
async def group_stream(group_id: str):
    """
    SSE endpoint — client connects once, server pushes signal when new post arrives.
    Frontend then calls /feed to get actual data.
    """
    def read_counts():
        # blocking DB work: runs in a worker thread, never on the event loop
        with engine.connect() as conn:
            posts = conn.execute(
                text("SELECT COUNT(*) FROM group_posts WHERE group_id = :group_id"),
                {"group_id": group_id}
            ).fetchone()[0]
            reactions = conn.execute(
                text("SELECT COUNT(*) FROM group_posts WHERE group_id = :group_id AND agent_reaction IS NOT NULL"),
                {"group_id": group_id}
            ).fetchone()[0]
        return posts, reactions

    async def event_generator():
        last_posts = 0
        last_reactions = 0

        while True:
            try:
                new_posts, new_reactions = await asyncio.to_thread(read_counts)

                if new_posts > last_posts or new_reactions > last_reactions:
                    last_posts = new_posts
                    last_reactions = new_reactions
                    yield "data: new_post\n\n"

            except Exception as e:
                print(f"SSE error: {e}")

            await asyncio.sleep(3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )