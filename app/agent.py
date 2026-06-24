from langgraph.graph import StateGraph, END
from typing import TypedDict
from openai import OpenAI
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os
import json
from pydantic import BaseModel, field_validator
from enum import Enum
import redis
import numpy as np
import time
from langfuse import Langfuse,observe
load_dotenv()


langfuse = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_HOST")
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
from sqlalchemy.pool import NullPool

engine = create_engine(
    os.getenv("DATABASE_URL")
)
redis_client = redis.from_url(os.getenv("REDIS_URL"))

SEMANTIC_CACHE_THRESHOLD = 0.15
MILESTONE_STREAKS = [7, 14, 21, 30, 60, 100]
BANNED_WORDS = ["hate", "kill", "stupid", "idiot", "terrible", "awful"]

def content_filter(text: str) -> bool:
    text_lower = text.lower()
    return any(word in text_lower for word in BANNED_WORDS)

def get_model(streak_count: int) -> str:
    if streak_count in MILESTONE_STREAKS:
        return "gpt-4o"
    return "gpt-4o-mini"

FALLBACK_CHAIN = ["gpt-4o-mini", "gpt-4o"]  # start cheap, escalate if fails
def cosine_distance(a, b):
    a = np.array(a)
    b = np.array(b)
    return 1 - np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def get_semantic_cache(description: str):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=description
    )
    embedding = response.data[0].embedding # list of float
    
    cached_keys = redis_client.keys("reaction_cache:*") # list of bytes - # → [b"reaction_cache:30min run", b"reaction_cache:HIIT workout"]
    
    for key in cached_keys:
        cached = json.loads(redis_client.get(key)) # {"embedding": [...], "reaction": "Great job!"}
        dist = cosine_distance(embedding, cached["embedding"])
        if dist < SEMANTIC_CACHE_THRESHOLD:
            print(f"Semantic cache hit — distance: {dist:.4f}")
            return cached["reaction"]
    
    return None

def set_semantic_cache(description: str, reaction: str):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=description
    )
    embedding = response.data[0].embedding
    key = f"reaction_cache:{description[:50]}"
    redis_client.setex(
        key,
        3600,
        json.dumps({
            "embedding": embedding,
            "reaction": reaction
        })
    )
def call_gpt_with_retry(model: str, messages: list, max_retries: int = 3): 
    for attempt in range(max_retries):
        try:
            response = client.beta.chat.completions.parse(
                model=model,
                messages=messages,
                max_tokens=200,
                response_format=AgentReaction
            )
            return response.choices[0].message.parsed
        except Exception as e:
            wait_time = 2 ** attempt  # 1s, 2s, 4s
            print(f"Attempt {attempt + 1} failed: {e} — retrying in {wait_time}s")
            if attempt < max_retries - 1:
                time.sleep(wait_time)
    return None
# state definition
class AgentState(TypedDict):
    user_id: str
    task_id: str
    description: str
    past_tasks: list
    reaction: object

class ToneEnum(str, Enum):
    motivational = "motivational"
    gentle = "gentle"
    energetic = "energetic"

class AgentReaction(BaseModel):
    message: str
    emoji: str
    streak_count: int
    tone: ToneEnum  

    @field_validator("message")
    @classmethod
    def validate_message(cls, v):
        if len(v) < 10:
            raise ValueError("Message too short")
        if len(v) > 250:
            v = v[:247] + "..."
        return v
    
    @field_validator("emoji")
    @classmethod
    def validate_emoji(cls, v):
        if len(v) > 5:
            raise ValueError("Only one emoji allowed")
        return v

def retrieve_context(state: AgentState) -> AgentState:
    with engine.connect() as conn:
        task = conn.execute(
            text("SELECT embedding FROM tasks WHERE id = :task_id"),
            {"task_id": state["task_id"]}
        ).fetchone()
        
        if not task or task[0] is None:
            state["past_tasks"] = []
            return state
        
        current_embedding = task[0]
        results = conn.execute(
            text("""
                SELECT id, description, completed, created_at
                FROM tasks
                WHERE user_id = :user_id 
                AND completed = TRUE
                AND embedding IS NOT NULL
                AND id != :task_id
                ORDER BY embedding <=> :embedding
                LIMIT 5
            """),
            {
                "user_id": state["user_id"],
                "embedding": str(current_embedding),
                "task_id": state["task_id"]
            }
        ).fetchall()
        
        state["past_tasks"] = [
            {
                "id": str(row[0]),
                "description": row[1],
                "completed": row[2],
                "created_at": str(row[3])
            }
            for row in results
        ]
    
    return state
@observe(name="generate_reaction",as_type="agent")
def generate_reaction(state: AgentState) -> AgentState:
    # check semantic cache 
    cached = get_semantic_cache(state["description"])
    if cached:
        state["reaction"] = AgentReaction(
            message=cached,
            emoji="💪",
            streak_count=0,
            tone=ToneEnum.motivational
        )
        return state
    
    with open("prompts/v1/agent_reaction.txt", "r") as f:
        prompt_template = f.read()
    past_tasks = state["past_tasks"] 
    past_tasks = "\n".join([f"- {t['description']}" for t in past_tasks])  #"- 20min run\n- HIIT workout\n- study Python"
    reaction = None

    with engine.connect() as conn:
        streak_count = conn.execute(
        text("SELECT COUNT(*) FROM tasks WHERE user_id = :user_id AND completed = TRUE"),
        {"user_id": state["user_id"]}
        ).fetchone()[0]
    primary_model = get_model(streak_count)

    FALLBACK_CHAIN = [primary_model, "gpt-4o-mini"] if primary_model == "gpt-4o" else ["gpt-4o-mini", "gpt-4o"]
    messages=[
                {"role": "system", "content": prompt_template},
                {"role": "user", "content": f"User completed: {state['description']}\nPast tasks:\n{past_tasks if past_tasks else 'none'}\nStreak: {streak_count} days"}
            ]
    
    for model in FALLBACK_CHAIN:
        reaction = call_gpt_with_retry(model, messages)
        if reaction:
            print(f"Model used: {model} — streak: {streak_count}")
            break

    # content filter
    if not reaction or content_filter(reaction.message):
        print("Reaction failed content filter — using fallback")
        reaction = AgentReaction(
        message="Great job completing your task! Keep going 💪",
        emoji="💪",
        streak_count=0,
        tone=ToneEnum.motivational
    )

    set_semantic_cache(state["description"], reaction.message)
    state["reaction"] = reaction
    return state


def store_reaction(state: AgentState) -> AgentState:
    with engine.connect() as conn:
        # get all groups user belongs to
        groups = conn.execute(
            text("SELECT group_id FROM group_members WHERE user_id = :user_id"),
            {"user_id": state["user_id"]}
        ).fetchall()
        
        # store reaction in each group's feed
        for group in groups:
            conn.execute(
                text("""
                    INSERT INTO group_posts 
                    (group_id, user_id, completed_tasks, uncompleted_tasks, agent_reaction)
                    VALUES (:group_id, :user_id, :completed_tasks, :uncompleted_tasks, :reaction)
                """),
                {
                    "group_id": str(group[0]),
                    "user_id": state["user_id"],
                    "completed_tasks": [state["description"]],
                    "uncompleted_tasks": [],
                    "reaction": state["reaction"].message
                }
            )
        conn.commit()
    
    return state

def build_agent():
    graph = StateGraph(AgentState)
    
    # add nodes
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("generate_reaction", generate_reaction)
    graph.add_node("store_reaction", store_reaction)
    
    # add edges
    graph.set_entry_point("retrieve_context")
    graph.add_edge("retrieve_context", "generate_reaction")
    graph.add_edge("generate_reaction", "store_reaction")
    graph.add_edge("store_reaction", END)
    
    return graph.compile()

# create agent instance
motivai_agent = build_agent()