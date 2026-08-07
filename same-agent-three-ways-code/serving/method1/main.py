"""Method 1 served: the Interactions API agent behind FastAPI on Cloud Run.

The service is stateless: conversation state lives with the Interactions API,
so clients continue a conversation by sending back interaction_id. On Cloud
Run, Gemini needs GOOGLE_API_KEY mounted from Secret Manager (the
Interactions API is Gemini-API-only; the Enterprise platform rejects it),
while BigQuery uses the service account. Must run a flash model: pro models
have zero free-tier quota.
"""

import json
import os

from fastapi import FastAPI
from google import genai
from google.cloud import bigquery
from pydantic import BaseModel

MODEL = os.environ.get("HN_AGENT_MODEL", "gemini-3.6-flash")
HN_TABLE = "bigquery-public-data.hacker_news.full"

execute_sql_tool = {
    "type": "function",
    "name": "execute_sql",
    "description": (
        f"Run a BigQuery Standard SQL SELECT query against `{HN_TABLE}`, the "
        "public Hacker News dataset (stories and comments since 2006). "
        "Columns: id INT, type STRING (story/comment/job/poll), title STRING "
        "(stories only), text STRING (body, HTML-escaped), `by` STRING "
        "(username), score INT, parent INT, descendants INT, timestamp "
        "TIMESTAMP, url STRING, dead BOOL, deleted BOOL. "
        "Returns at most 50 rows."
    ),
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}

def execute_sql(query: str) -> list[dict]:
    if not query.lstrip().lower().startswith(("select", "with")):
        return [{"error": "Only SELECT queries are allowed."}]
    client = bigquery.Client()
    config = bigquery.QueryJobConfig(maximum_bytes_billed=20 * 10**9)
    rows = client.query_and_wait(query, job_config=config, max_results=50)
    return [{k: str(v) for k, v in dict(row).items()} for row in rows]

INSTRUCTION = (
    "You answer questions about opinions on Hacker News. Use execute_sql to "
    "query the dataset described in the tool. Prefer comments (type='comment') "
    "matching the topic in `text`, recent first, and skim enough of them to "
    "summarize the range of opinions with short quotes. Keep queries cheap: "
    "select only needed columns, filter by timestamp, LIMIT 50."
)

app = FastAPI()
client = genai.Client()

class Ask(BaseModel):
    question: str
    interaction_id: str | None = None

@app.post("/ask")
def ask(body: Ask):
    interaction = client.interactions.create(
        model=MODEL,
        input=body.question,
        system_instruction=INSTRUCTION,
        tools=[execute_sql_tool],
        previous_interaction_id=body.interaction_id,
    )
    while True:
        calls = [s for s in interaction.steps if s.type == "function_call"]
        if not calls:
            break
        results = [{
            "type": "function_result",
            "name": s.name,
            "call_id": s.id,
            "result": [{"type": "text", "text": json.dumps(execute_sql(**s.arguments))}],
        } for s in calls]
        interaction = client.interactions.create(
            model=MODEL,
            input=results,
            system_instruction=INSTRUCTION,
            tools=[execute_sql_tool],
            previous_interaction_id=interaction.id,
        )
    return {"answer": interaction.output_text, "interaction_id": interaction.id}
