from celery import Celery
from dotenv import load_dotenv
import redis
import os
import time
import sys
sys.path.insert(0, '/app')
from metrics import agent_latency
from agent import motivai_agent
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
    
    while True:
        try:
            messages = redis_client.xreadgroup(
            "agent-workers",
            "worker-1",
            {"task_completed": ">"},
            count=1,
            block=2000
        )
        except Exception as e:
            print(f"Redis error: {e} — retrying...")
            time.sleep(1)
            continue
        if messages:
            for stream_name, stream_messages in messages:
                for message_id, message_data in stream_messages:
                    user_id = message_data.get(b"user_id", b"").decode()
                    task_id = message_data.get(b"task_id", b"").decode()
                    description = message_data.get(b"description", b"").decode()
                    
                    # idempotency check
                    idempotency_key = f"task:processed:{task_id}"
                    acquired = redis_client.set(
                        idempotency_key,
                        "1",
                        ex=86400,  # expire after 24 hours
                        nx=True    # only set if not exists
                    )
                    
                    if not acquired:
                        # already processed — skip
                        print(f"Task {task_id} already processed — skipping")
                        redis_client.xack("task_completed", "agent-workers", message_id)
                        continue
                    
                    # first time processing
                    print(f"Agent triggered for user {user_id} — task: {description}")
                    
                    start = time.time()
                    result = motivai_agent.invoke({
                        "user_id": user_id,
                        "task_id": task_id,
                        "description": description,
                        "past_tasks": [],
                        "reaction": ""
                    })
                    print(f"Agent reaction: {result['reaction']}")
                    agent_latency.observe(time.time() - start)
            
                    # acknowledge message
                    redis_client.xack("task_completed", "agent-workers", message_id)
                    print(f"Message {message_id} acknowledged")


if __name__ == "__main__":
    process_stream()