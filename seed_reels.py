from sqlalchemy import create_engine, text
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

engine = create_engine(os.getenv("LOCAL_DATABASE_URL"))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

reels = [
    {"title": "Morning HIIT workout", "summary": "High intensity interval training for beginners to burn fat and build stamina", "tags": ["fitness", "workout"]},
    {"title": "5km run guide", "summary": "Step by step plan to run your first 5km in 4 weeks", "tags": ["fitness", "running"]},
    {"title": "Healthy meal prep", "summary": "Simple meal prep ideas for a week of clean eating on a budget", "tags": ["fitness", "nutrition"]},
    {"title": "Python list comprehensions", "summary": "Master Python list comprehensions to write cleaner and faster code", "tags": ["coding", "python"]},
    {"title": "System design basics", "summary": "Learn the fundamentals of designing scalable backend systems", "tags": ["coding", "system design"]},
    {"title": "Git workflow tips", "summary": "Essential Git commands and branching strategies every developer needs", "tags": ["coding", "git"]},
    {"title": "Atomic Habits summary", "summary": "Key lessons from Atomic Habits by James Clear on building good habits", "tags": ["reading", "habits"]},
    {"title": "Speed reading technique", "summary": "Simple techniques to double your reading speed without losing comprehension", "tags": ["reading", "productivity"]},
    {"title": "Box breathing technique", "summary": "Four count box breathing method to reduce stress and improve focus instantly", "tags": ["meditation", "breathing"]},
    {"title": "Morning meditation guide", "summary": "Ten minute morning meditation routine to start your day with clarity", "tags": ["meditation", "mindfulness"]},
    {"title": "How I cope with study anxiety", "summary": "Methods to cope with study anxiety and stay focused", "tags": ["studying", "mental health"]},
    {"title": "How to reduce weight", "summary": "How to reduce weight through consistent exercise and healthy habits", "tags": ["fitness", "habits"]},
]

with engine.connect() as conn:
    for reel in reels:
        # 1. embed the summary
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=reel["summary"]
        )
        embedding = response.data[0].embedding
        
        # 2. insert into reels table
        conn.execute(
            text("""
                INSERT INTO reels (title, summary, tags, embedding)
                VALUES (:title, :summary, :tags, :embedding)
            """),
            {
                "title": reel["title"],
                "summary": reel["summary"],
                "tags": reel["tags"],
                "embedding": str(embedding)
            }
        )
    conn.commit()
    print(f"Seeded {len(reels)} reels successfully")