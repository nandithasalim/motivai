from celery import Celery
from dotenv import load_dotenv
from sqlalchemy import text
import redis
import os
import time
import sys

sys.path.insert(0, '/app')
from metrics import agent_latency
from agent import motivai_agent, engine

load_dotenv()

celery_app = Celery(
    "agent",
    broker=os.getenv("REDIS_URL"),
    backend=os.getenv("REDIS_URL")
)

redis_client = redis.from_url(os.getenv("REDIS_URL"))

STREAM = "task_completed"   # main Redis stream — tasks arrive here
GROUP = "agent-workers"     # consumer group name
WORKER_ID = f"worker-{os.getenv('RAILWAY_REPLICA_ID', '1')}"  # unique per Railway instance
DLQ = "task_failed"         # dead letter queue — failed messages go here
MAX_RETRIES = 3             # max attempts before sending to DLQ
CLAIM_IDLE_MS = 60000       # a pending message idle this long is considered stuck
CLAIM_EVERY_SEC = 60        # how often to look for stuck messages


def create_consumer_group():
    try:
        redis_client.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
        print("Consumer group created")
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            print("Consumer group already exists")
        else:
            raise


def decode(fields):
    """Redis hands back bytes; turn {b"a": b"b"} into {"a": "b"}."""
    return {k.decode(): v.decode() for k, v in fields.items()}


def post_is_done(post_id):
    """The database is the source of truth for 'done': the post already has a reaction.

    A missing post also counts as done: there is nothing to process, and retrying
    forever would not help.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT agent_reaction FROM group_posts WHERE id = :post_id"),
            {"post_id": post_id}
        ).fetchone()
    return row is None or row[0] is not None


def handle_message(message_id, message_data):
    """Process one message. ACK only when the work is finished (or can never be done).

    - agent finished           -> ACK
    - agent raised an error    -> NO ack, message stays pending and is retried later
    - reaction already stored  -> ACK (an earlier attempt finished; it died before the ACK)
    """
    data = decode(message_data)
    user_id = data.get("user_id", "")
    post_id = data.get("post_id", "")
    description = data.get("description", "")
    group_id = data.get("group_id", "")

    # old-format events (no post_id) can never be processed — drop them
    if not post_id:
        print(f"Message {message_id} has no post_id — dropping")
        redis_client.xack(STREAM, GROUP, message_id)
        return

    if post_is_done(post_id):
        print(f"Post {post_id} already has a reaction — acknowledging")
        redis_client.xack(STREAM, GROUP, message_id)
        return

    print(f"Agent triggered for user {user_id} — task: {description}")
    start = time.time()
    try:
        result = motivai_agent.invoke({
            "user_id": user_id,
            "post_id": post_id,
            "description": description,
            "past_tasks": [],
            "group_id": group_id,
            "reaction": ""
        })
    except Exception as e:
        # no ACK: the message stays pending, so it can be claimed and retried
        print(f"Agent failed for post {post_id}: {e} — left pending for retry")
        return

    print(f"Agent reaction: {result['reaction']}")
    agent_latency.observe(time.time() - start)

    # ACK last, only after the reaction is stored
    redis_client.xack(STREAM, GROUP, message_id)
    print(f"Message {message_id} acknowledged")


def send_to_dlq(message_id, delivery_count):
    """Give up on a message: keep its whole payload in the DLQ so it can be replayed."""
    entries = redis_client.xrange(STREAM, message_id, message_id)
    payload = decode(entries[0][1]) if entries and entries[0][1] else {}
    redis_client.xadd(DLQ, {
        "original_message_id": message_id,
        "delivery_count": str(delivery_count),
        "reason": "max retries exceeded",
        **payload,
    })
    # remove from pending so it doesn't block the queue
    redis_client.xack(STREAM, GROUP, message_id)
    print(f"Message {message_id} failed {delivery_count} times → DLQ")


def claim_stuck_messages():
    """
    Find messages that have been pending too long (the worker probably crashed or
    the agent failed). Retry them, or give up and send them to the DLQ.
    """
    try:
        pending = redis_client.xpending_range(STREAM, GROUP, "-", "+", count=10)
    except Exception as e:
        print(f"XPENDING error: {e}")
        return

    for msg in pending:
        message_id = msg["message_id"]
        if msg["time_since_delivered"] <= CLAIM_IDLE_MS:
            continue

        try:
            if msg["times_delivered"] >= MAX_RETRIES:
                send_to_dlq(message_id, msg["times_delivered"])
                continue

            print(f"Claiming stuck message {message_id}")
            # XCLAIM only changes the owner. It returns the messages, and WE must run them.
            claimed = redis_client.xclaim(STREAM, GROUP, WORKER_ID, CLAIM_IDLE_MS, [message_id])
            for claimed_id, claimed_data in claimed:
                if claimed_data:   # None = the entry no longer exists in the stream
                    handle_message(claimed_id, claimed_data)
        except Exception as e:
            print(f"Retry of {message_id} failed: {e}")


def process_stream():
    create_consumer_group()
    print("Agent worker started — listening for task completions...")

    last_claim = time.time()

    while True:
        if time.time() - last_claim >= CLAIM_EVERY_SEC:
            claim_stuck_messages()
            last_claim = time.time()

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

        _, stream_messages = messages[0]
        message_id, message_data = stream_messages[0]

        try:
            handle_message(message_id, message_data)
        except Exception as e:
            # e.g. database down: leave the message pending, it will be retried
            print(f"Could not handle {message_id}: {e} — left pending")


if __name__ == "__main__":
    process_stream()