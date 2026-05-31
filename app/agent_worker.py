from celery import Celery
from dotenv import load_dotenv
import redis
import os
import json
import time

load_dotenv()

celery_app = Celery(
    "agent",
    broker=os.getenv("REDIS_URL"),
    backend=os.getenv("REDIS_URL")
)

redis_client = redis.from_url(os.getenv("REDIS_URL"))

def create_consumer_group():
    try:
        redis_client.xgroup_create(
            "task_completed",  # stream name
            "agent-workers",   # consumer group name
            id="0",
            mkstream=True
        )
        print("Consumer group created")
    except Exception as e:
        # group already exists — ignore
        print(f"Consumer group already exists: {e}")

def process_stream():
    create_consumer_group()
    
    print("Agent worker started — listening for task completions...")
    
    while True:  #always listening for new task completions
        # read undelivered messages
        messages = redis_client.xreadgroup(
            "agent-workers", # consumer group
            "worker-1",      # consumer name
            {"task_completed": ">"},
            count=1,
            block=5000  # wait 5 seconds for message
        )
        
        if messages:
            for stream_name, stream_messages in messages:
                for message_id, message_data in stream_messages:
                    user_id = message_data.get(b"user_id", b"").decode() # decode bytes to string
                    task_id = message_data.get(b"task_id", b"").decode()
                    description = message_data.get(b"description", b"").decode()
                    
                    print(f"Agent triggered for user {user_id} — task: {description}")
                    
                    # stub —  will add real LangGraph agent here
                    
                    # acknowledge message
                    redis_client.xack("task_completed", "agent-workers", message_id)
                    print(f"Message {message_id} acknowledged")

if __name__ == "__main__":
    process_stream()