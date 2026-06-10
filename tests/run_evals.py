import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import create_engine, text
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_recall, context_precision
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
engine = create_engine(os.getenv("LOCAL_DATABASE_URL"))

# configure RAGAS to use OpenAI
llm = LangchainLLMWrapper(ChatOpenAI(model="gpt-4o-mini"))
embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings())

faithfulness.llm = llm
answer_relevancy.llm = llm
answer_relevancy.embeddings = embeddings
context_recall.llm = llm
context_precision.llm = llm

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
    raw = response.choices[0].message.content.strip()
    
    # extract just message text from JSON
    try:
        data = json.loads(raw)
        return data.get("message", raw)
    except:
        return raw

def run_evals():
    with open("tests/golden_dataset.json", "r") as f:
        golden_data = json.load(f)
    
    task_completed = []
    reactions = []
    contexts = []
    expected_reaction = []
    
    for i, row in enumerate(golden_data[:5]):
        print(f"Row {i+1}/5: {row['task_completed']}")
        result = generate_reaction_for_eval(row["task_completed"], row["retrieved_context"])
        print(f"Reaction: {result[:80]}...")
        reactions.append(result)
        task_completed.append(row["task_completed"])
        contexts.append(row["retrieved_context"] if row["retrieved_context"] else ["no past tasks"])
        expected_reaction.append(row["expected_reaction_theme"])
    
    dataset = Dataset.from_dict({
        "question": task_completed,
        "answer": reactions,
        "contexts": contexts,
        "ground_truth": expected_reaction
    })
    
    print("\nRunning RAGAS evaluation...")
    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_recall, context_precision]
    )
    scores = result.to_pandas()
    print(f"\n=== RAGAS Scores ===")
    print(f"Faithfulness:      {scores['faithfulness'].mean():.3f}")
    print(f"Answer Relevancy:  {scores['answer_relevancy'].mean():.3f}")
    print(f"Context Recall:    {scores['context_recall'].mean():.3f}")
    print(f"Context Precision: {scores['context_precision'].mean():.3f}")
    
    with engine.connect() as conn:
        conn.execute(
            text("""
            INSERT INTO evals 
            (faithfulness, answer_relevancy, context_recall, context_precision)
            VALUES (:faithfulness, :answer_relevancy, :context_recall, :context_precision)
        """),
        {
            "faithfulness": float(scores['faithfulness'].mean()),
            "answer_relevancy": float(scores['answer_relevancy'].mean()),
            "context_recall": float(scores['context_recall'].mean()),
            "context_precision": float(scores['context_precision'].mean())
        }
    )
        conn.commit()
    
    print("Scores saved to DB.")
    return result

if __name__ == "__main__":
    run_evals()