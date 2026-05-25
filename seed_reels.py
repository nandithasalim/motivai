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
    # FITNESS
    {"title": "Beginner yoga flow", "summary": "Simple yoga routine for complete beginners to improve flexibility and reduce stress", "tags": ["fitness", "yoga"]},
    {"title": "10 min abs workout", "summary": "Quick core workout targeting abs and obliques with no equipment needed", "tags": ["fitness", "core"]},
    {"title": "Running tips for beginners", "summary": "Essential tips for starting a running habit including pace breathing and form", "tags": ["fitness", "running"]},
    {"title": "Full body stretching", "summary": "Complete stretching routine for recovery and flexibility after workouts", "tags": ["fitness", "recovery"]},
    {"title": "Home workout no equipment", "summary": "Effective bodyweight exercises for strength and cardio at home", "tags": ["fitness", "home"]},
    {"title": "Strength training basics", "summary": "Introduction to strength training covering compound movements and progressive overload", "tags": ["fitness", "strength"]},
    {"title": "Cardio vs weights", "summary": "Comparing cardio and weight training for fat loss muscle gain and overall health", "tags": ["fitness", "cardio"]},
    {"title": "Sleep and recovery", "summary": "How quality sleep improves workout performance recovery and muscle growth", "tags": ["fitness", "sleep"]},
    {"title": "Plank variations", "summary": "Five plank variations to build core strength from beginner to advanced", "tags": ["fitness", "core"]},
    {"title": "Jump rope workout", "summary": "High intensity jump rope workout to burn calories and improve coordination", "tags": ["fitness", "cardio"]},

    # CODING
    {"title": "Python decorators explained", "summary": "Understanding Python decorators with simple examples and real use cases", "tags": ["coding", "python"]},
    {"title": "REST API design", "summary": "Best practices for designing clean and scalable REST APIs", "tags": ["coding", "api"]},
    {"title": "Docker for beginners", "summary": "Getting started with Docker containers and images for development", "tags": ["coding", "docker"]},
    {"title": "SQL vs NoSQL", "summary": "When to use SQL vs NoSQL databases with real world examples", "tags": ["coding", "database"]},
    {"title": "Clean code principles", "summary": "Writing readable maintainable code using clean code principles", "tags": ["coding", "best practices"]},
    {"title": "GitHub Actions CI/CD", "summary": "Setting up automated testing and deployment with GitHub Actions", "tags": ["coding", "devops"]},
    {"title": "FastAPI tutorial", "summary": "Building production ready APIs with FastAPI and Python", "tags": ["coding", "python"]},
    {"title": "Redis caching patterns", "summary": "Common Redis caching patterns including cache aside and write through", "tags": ["coding", "redis"]},
    {"title": "PostgreSQL performance", "summary": "Optimizing PostgreSQL queries with indexes and query planning", "tags": ["coding", "database"]},
    {"title": "Async Python explained", "summary": "Understanding async await in Python for concurrent programming", "tags": ["coding", "python"]},

    # READING
    {"title": "Deep Work summary", "summary": "Key lessons from Cal Newport on focused work and eliminating distraction", "tags": ["reading", "productivity"]},
    {"title": "The Psychology of Money", "summary": "Timeless lessons on wealth greed and happiness from Morgan Housel", "tags": ["reading", "finance"]},
    {"title": "How to read more books", "summary": "Practical strategies to read more books and retain what you learn", "tags": ["reading", "habits"]},
    {"title": "Thinking Fast and Slow", "summary": "Daniel Kahneman on the two systems of thinking and cognitive biases", "tags": ["reading", "psychology"]},
    {"title": "Note taking while reading", "summary": "Effective note taking methods to remember and apply what you read", "tags": ["reading", "learning"]},

    # MEDITATION
    {"title": "Body scan meditation", "summary": "Guided body scan meditation to release tension and improve awareness", "tags": ["meditation", "mindfulness"]},
    {"title": "Mindfulness for anxiety", "summary": "Using mindfulness techniques to reduce anxiety and stress daily", "tags": ["meditation", "anxiety"]},
    {"title": "Breath awareness practice", "summary": "Simple breath awareness meditation for beginners to build focus", "tags": ["meditation", "breathing"]},
    {"title": "Evening wind down routine", "summary": "Calming evening meditation routine to improve sleep quality", "tags": ["meditation", "sleep"]},
    {"title": "Walking meditation guide", "summary": "How to practice mindfulness during walking as a daily habit", "tags": ["meditation", "mindfulness"]},

    # NUTRITION
    {"title": "Meal prep for beginners", "summary": "Simple meal prep strategies to eat healthy on a busy schedule", "tags": ["nutrition", "habits"]},
    {"title": "Protein sources guide", "summary": "Complete guide to protein sources for muscle building and recovery", "tags": ["nutrition", "fitness"]},
    {"title": "Sugar and energy levels", "summary": "How sugar affects energy levels focus and mood throughout the day", "tags": ["nutrition", "health"]},
    {"title": "Intermittent fasting basics", "summary": "Introduction to intermittent fasting methods benefits and risks", "tags": ["nutrition", "health"]},
    {"title": "Hydration and performance", "summary": "How proper hydration affects physical and mental performance", "tags": ["nutrition", "fitness"]},

    # PRODUCTIVITY
    {"title": "Pomodoro technique", "summary": "Using the Pomodoro technique to improve focus and beat procrastination", "tags": ["productivity", "focus"]},
    {"title": "Morning routine design", "summary": "How to design a morning routine that sets you up for a productive day", "tags": ["productivity", "habits"]},
    {"title": "Time blocking method", "summary": "Using time blocking to schedule deep work and protect your calendar", "tags": ["productivity", "planning"]},
    {"title": "Digital minimalism", "summary": "Reducing digital distractions to reclaim focus and mental clarity", "tags": ["productivity", "focus"]},
    {"title": "Weekly review habit", "summary": "How to do a weekly review to stay on track with your goals", "tags": ["productivity", "habits"]},
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
                INSERT INTO reels (title, summary, tags, embedding, search_vector)
                VALUES (:title, :summary, :tags, :embedding,to_tsvector('english', :title || ' ' || :summary))
            """),
            {
                "title": reel["title"], #bcuz reel is a python variable
                "summary": reel["summary"],
                "tags": reel["tags"],
                "embedding": str(embedding)
                
            }
    
        )
        
        
    conn.commit()
    print(f"Seeded {len(reels)} reels successfully")