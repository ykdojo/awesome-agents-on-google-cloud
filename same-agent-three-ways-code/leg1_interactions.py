"""Leg 1: the Interactions API with a hand-written BigQuery tool.

You write the tool (a plain function) and run the tool loop yourself; the
server keeps conversation state via previous_interaction_id. Remote MCP is
not yet available for plain model calls, which is why this leg hand-rolls.

Requires GOOGLE_API_KEY and application default credentials
(gcloud auth application-default login).
"""

import json
import sys

from google import genai
from google.cloud import bigquery

MODEL = "gemini-3.6-flash"
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
    """The whole tool: run the SQL, cap the cost, return rows as dicts."""
    if not query.lstrip().lower().startswith(("select", "with")):
        return [{"error": "Only SELECT queries are allowed."}]
    client = bigquery.Client()
    config = bigquery.QueryJobConfig(maximum_bytes_billed=20 * 10**9)
    rows = client.query_and_wait(query, job_config=config, max_results=50)
    return [{k: str(v) for k, v in dict(row).items()} for row in rows]

TOOLS = {"execute_sql": execute_sql}

INSTRUCTION = (
    "You answer questions about opinions on Hacker News. Use execute_sql to "
    "query the dataset described in the tool. Prefer comments (type='comment') "
    "matching the topic in `text`, recent first, and skim enough of them to "
    "summarize the range of opinions with short quotes. Keep queries cheap: "
    "select only needed columns, filter by timestamp, LIMIT 50."
)

client = genai.Client()

question = sys.argv[1] if len(sys.argv) > 1 else "What do people on Hacker News think about Rust?"
interaction = client.interactions.create(
    model=MODEL,
    input=question,
    system_instruction=INSTRUCTION,
    tools=[execute_sql_tool],
)

# The loop is yours: execute every function call, send results back, repeat.
while True:
    calls = [s for s in interaction.steps if s.type == "function_call"]
    if not calls:
        break
    results = []
    for step in calls:
        print(f"  tool call: {step.name}({json.dumps(step.arguments)[:120]}...)")
        result = TOOLS[step.name](**step.arguments)
        results.append({
            "type": "function_result",
            "name": step.name,
            "call_id": step.id,
            "result": [{"type": "text", "text": json.dumps(result)}],
        })
    interaction = client.interactions.create(
        model=MODEL,
        input=results,
        system_instruction=INSTRUCTION,
        tools=[execute_sql_tool],
        previous_interaction_id=interaction.id,
    )

print(interaction.output_text.strip())
