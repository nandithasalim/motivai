from langgraph.graph import StateGraph, END
from typing import TypedDict
from openai import OpenAI
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os
import json
import requests

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
engine = create_engine(os.getenv("DATABASE_URL"))

# state definition
class AgentState(TypedDict):
    user_id: str
    task_id: str
    description: str
    past_tasks: list
    reaction: str
    group_ids: list

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