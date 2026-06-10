import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import create_engine, text
from datetime import datetime

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
engine = create_engine(os.getenv("LOCAL_DATABASE_URL"))

def generate_reaction_for_eval(task_completed: str, context: list[str]) -> str:
    with open("prompts/v1/agent_reaction.txt", "r") as f:
        prompt_template = f.read()
    context_text = "\n".join([f"- {t}" for t in context])
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": prompt_template},
            {"role": "user", "content": f"User completed: {task_completed}\nPast tasks:\n{context_text if context_text else 'none'}"}
        ],
        max_tokens=200
    )
    return response.choices[0].message.content.strip()

def score_reaction(task: str, context: list[str], reaction: str, expected_theme: str) -> dict:
    prompt = f"""Score this AI reaction on two metrics from 0 to 1:

Task completed: {task}
Past tasks context: {context}
Reaction generated: {reaction}
Expected theme: {expected_theme}

Score these:
1. faithfulness (0-1): does the reaction use the past tasks context?
2. relevance (0-1): is the reaction relevant to the task completed?

Respond ONLY in this JSON format:
{{"faithfulness": 0.0, "relevance": 0.0}}"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    
    result = json.loads(response.choices[0].message.content.strip())
    return result

def run_evals():
    with open("tests/golden_dataset.json", "r") as f:
        golden_data = json.load(f)
    
    faithfulness_scores = []
    relevance_scores = []
    
    print(f"Running evals on {len(golden_data[:5])} rows...")
    
    for i, row in enumerate(golden_data[:5]):
        print(f"Row {i+1}/5: {row['task_completed']}")
        
        reaction = generate_reaction_for_eval(
            row["task_completed"],
            row["retrieved_context"]
        )
        print(f"Reaction: {reaction[:80]}...")
        
        scores = score_reaction(
            row["task_completed"],
            row["retrieved_context"],
            reaction,
            row["expected_reaction_theme"]
        )
        
        faithfulness_scores.append(scores["faithfulness"])
        relevance_scores.append(scores["relevance"])
        print(f"Scores: faithfulness={scores['faithfulness']:.2f}, relevance={scores['relevance']:.2f}")
    
    avg_faithfulness = sum(faithfulness_scores) / len(faithfulness_scores)
    avg_relevance = sum(relevance_scores) / len(relevance_scores)
    
    print(f"\n=== Eval Results ===")
    print(f"Faithfulness:  {avg_faithfulness:.3f}")
    print(f"Relevance:     {avg_relevance:.3f}")
    
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO evals 
                (faithfulness, answer_relevancy, context_recall, context_precision)
                VALUES (:faithfulness, :answer_relevancy, :context_recall, :context_precision)
            """),
            {
                "faithfulness": avg_faithfulness,
                "answer_relevancy": avg_relevance,
                "context_recall": avg_relevance,
                "context_precision": avg_faithfulness
            }
        )
        conn.commit()
    
    print("Scores saved to DB.")
    return {"faithfulness": avg_faithfulness, "relevance": avg_relevance}

if __name__ == "__main__":
    run_evals()