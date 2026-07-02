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

STREAM = "task_completed"
GROUP = "agent-workers"
WORKER_ID = f"worker-{os.getenv('RAILWAY_REPLICA_ID', '1')}"
DLQ = "task_failed"
MAX_RETRIES = 3
CLAIM_IDLE_MS = 60000


def create_consumer_group():
    try:
        redis_client.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
        print("Consumer group created")
    except:
        print("Consumer group already exists")


def claim_stuck_messages():
    try:
        pending = redis_client.xpending_range(STREAM, GROUP, "-", "+", count=10)
        for msg in pending:
            message_id = msg["message_id"]
            idle_ms = msg["time_since_delivered"]
            delivery_count = msg["times_delivered"]

            if idle_ms > CLAIM_IDLE_MS:
                if delivery_count >= MAX_RETRIES:
                    print(f"Message {message_id} failed {delivery_count} times → DLQ")
                    redis_client.xadd(DLQ, {
                        "original_message_id": message_id,
                        "delivery_count": str(delivery_count),
                        "reason": "max retries exceeded"
                    })
                    redis_client.xack(STREAM, GROUP, message_id)
                else:
                    print(f"Claiming stuck message {message_id}")
                    redis_client.xclaim(STREAM, GROUP, WORKER_ID, CLAIM_IDLE_MS, [message_id])
    except Exception as e:
        print(f"XCLAIM error: {e}")


def process_stream():
    create_consumer_group()
    print("Agent worker started — listening for task completions...")

    iteration = 0

    while True:
        iteration += 1

        # every 60 seconds check for stuck messages
        if iteration % 30 == 0:
            claim_stuck_messages()

        # read new message
        try:
            messages = redis_client.xreadgroup(
                GROUP, WORKER_ID,
                {STREAM: ">"},
                count=1,
                block=2000
            )
        except Exception as e:
            print(f"Redis error: {e} — retrying...")
            time.sleep(1)
            continue

        if not messages:
            continue

        # extract message
        message_id = messages[0][1][0][0]
        message_data = messages[0][1][0][1]

        user_id = message_data.get(b"user_id", b"").decode()
        task_id = message_data.get(b"task_id", b"").decode()
        description = message_data.get(b"description", b"").decode()
        group_id = message_data.get(b"group_id", b"").decode()

        # idempotency check
        idempotency_key = f"task:processed:{task_id}"
        acquired = redis_client.set(idempotency_key, "1", ex=86400, nx=True)

        if not acquired:
            print(f"Task {task_id} already processed — skipping")
            redis_client.xack(STREAM, GROUP, message_id)
            continue

        # run agent
        print(f"Agent triggered for user {user_id} — task: {description}")
        start = time.time()

        try:
            result = motivai_agent.invoke({
                "user_id": user_id,
                "task_id": task_id,
                "description": description,
                "past_tasks": [],
                "group_id": group_id,
                "reaction": ""
            })
            print(f"Agent reaction: {result['reaction']}")
            agent_latency.observe(time.time() - start)

            # success
            redis_client.xack(STREAM, GROUP, message_id)
            print(f"Message {message_id} acknowledged")

        except Exception as e:
            # agent crashed — delete key so retry can process
            print(f"Agent failed for task {task_id}: {e}")
            redis_client.delete(idempotency_key)
            print(f"Task {task_id} left in pending for retry")


if __name__ == "__main__":
    process_stream()