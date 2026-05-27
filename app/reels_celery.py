from celery import Celery
from openai import OpenAI
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os
import json

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
engine = create_engine(os.getenv("DATABASE_URL"))

celery_app = Celery(
    "motivai",
    broker=os.getenv("REDIS_URL"),
    backend=os.getenv("REDIS_URL")
)

@celery_app.task(bind=True, max_retries=3, default_retry_delay=5)
def process_reel(self, reel_id: str, file_path: str):
    try:
        # step 1: transcribe with Whisper
        with open(file_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        transcript_text = transcript.text

        # step 2: moderation — check transcript for inappropriate content
        moderation_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": f"""Is this transcript appropriate for all ages? 
                Check for violence, adult content, hate speech.
                Reply YES or NO only.
                
                Transcript: {transcript_text}"""
            }]
        )
        
        is_appropriate = moderation_response.choices[0].message.content.strip().upper()
        
        if is_appropriate == "NO":
            # flag reel and stop pipeline
            with engine.connect() as conn:
                conn.execute(
                    text("UPDATE reels SET flagged = TRUE WHERE id = :reel_id"),
                    {"reel_id": reel_id}
                )
                conn.commit()
            os.remove(file_path)
            return {"status": "flagged", "reel_id": reel_id}

        # step 3: extract tags with GPT
        with open("prompts/reel_tagger.txt", "r") as f:
            prompt_template = f.read()
        prompt = prompt_template.replace("{{transcript}}", transcript_text)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        tags = json.loads(response.choices[0].message.content)

        # step 4: embed summary
        embedding_response = client.embeddings.create(
            model="text-embedding-3-small",
            input=transcript_text[:500]
        )
        embedding = embedding_response.data[0].embedding

        # step 5: store in DB
        with engine.connect() as conn:
            conn.execute(
                text("""
                    UPDATE reels 
                    SET embedding = :embedding,
                        tags = :tags,
                        summary = :summary
                    WHERE id = :reel_id
                """),
                {
                    "embedding": str(embedding),
                    "tags": tags,
                    "summary": transcript_text[:500],
                    "reel_id": reel_id
                }
            )
            conn.commit()

        os.remove(file_path)

    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries) # exponential backoff