from langgraph.graph import StateGraph, END
from typing import TypedDict
from openai import OpenAI
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os
import json
import requests
from pydantic import BaseModel, field_validator
from enum import Enum
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
engine = create_engine(os.getenv("DATABASE_URL"))

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
        if len(v) > 200:
            raise ValueError("Message too long")
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

def generate_reaction(state: AgentState) -> AgentState:
    with open("prompts/v1/agent_reaction.txt", "r") as f:
        prompt_template = f.read()
    past_tasks = state["past_tasks"] 
    past_tasks = "\n".join([f"- {t['description']}" for t in past_tasks])  #"- 20min run\n- HIIT workout\n- study Python"
    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
    {"role": "system", "content": prompt_template},
    {"role": "user", "content": f"User completed: {state['description']}\nPast tasks: {past_tasks}"}],
        response_format=AgentReaction
    )
    state["reaction"] = response.choices[0].message.parsed
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