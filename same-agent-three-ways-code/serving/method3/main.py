"""Method 3 served: the Antigravity SDK agent behind FastAPI on Cloud Run.

The MCP Authorization header needs a fresh OAuth token; on Cloud Run we mint
and refresh it from the service account instead of a local gcloud login.
Gemini goes through the GOOGLE_GENAI_USE_ENTERPRISE env vars, so this
service has no API keys.
"""

import os

import google.auth
import google.auth.transport.requests
from fastapi import FastAPI
from google.antigravity import Agent, LocalAgentConfig
from google.antigravity.types import McpStreamableHttpServer
from pydantic import BaseModel

HN_TABLE = "bigquery-public-data.hacker_news.full"

credentials, project = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)

def bearer_token() -> str:
    if not credentials.valid:
        credentials.refresh(google.auth.transport.requests.Request())
    return credentials.token

INSTRUCTION = (
    "You answer questions about opinions on Hacker News using the bigquery "
    f"MCP tools. The data lives in `{HN_TABLE}`; inspect its schema with "
    "get_table_info if needed. Prefer comments (type='comment') matching the "
    "topic in `text`, recent first, and skim enough of them to summarize the "
    "range of opinions with short quotes. Keep queries cheap: select only "
    "needed columns, filter by timestamp, LIMIT 50. Run BigQuery jobs in "
    "project " + os.environ.get("GOOGLE_CLOUD_PROJECT", project)
)

app = FastAPI()

class Ask(BaseModel):
    question: str

@app.post("/ask")
async def ask(body: Ask):
    bigquery_mcp = McpStreamableHttpServer(
        name="bigquery",
        type="http",
        url="https://bigquery.googleapis.com/mcp",
        headers={
            "Authorization": f"Bearer {bearer_token()}",
            "x-goog-user-project": os.environ.get("GOOGLE_CLOUD_PROJECT", project),
        },
        enabled_tools=[
            "execute_sql_readonly",
            "list_dataset_ids",
            "list_table_ids",
            "get_dataset_info",
            "get_table_info",
        ],
    )
    config = LocalAgentConfig(
        model=os.environ.get("HN_AGENT_MODEL", "gemini-3.6-flash"),
        system_instructions=INSTRUCTION,
        mcp_servers=[bigquery_mcp],
    )
    async with Agent(config) as agent:
        response = await agent.chat(body.question)
        return {"answer": await response.text()}
