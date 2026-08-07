"""Method 3: the same agent on the Antigravity SDK, tools via MCP.

The harness owns everything: the loop, built-in file and shell tools,
deny-by-default permission policies. BigQuery arrives over MCP, and there is no server to run: this
points at Google's fully managed BigQuery MCP endpoint. That endpoint takes
OAuth only (no API keys), so a Bearer token rides in the headers.

The SDK has no macOS x86_64 wheel; on an Intel Mac run ./method3_container.sh,
which executes this file in a Linux container.

Requires your Cloud account, no API key: GOOGLE_GENAI_USE_ENTERPRISE=TRUE,
GOOGLE_CLOUD_PROJECT, application default credentials, and
BIGQUERY_OAUTH_TOKEN (method3_container.sh mints it from gcloud).
"""

import asyncio
import os
import sys

from google.antigravity import Agent, LocalAgentConfig
from google.antigravity.types import McpStreamableHttpServer

HN_TABLE = "bigquery-public-data.hacker_news.full"

bigquery_mcp = McpStreamableHttpServer(
    name="bigquery",
    type="http",
    url="https://bigquery.googleapis.com/mcp",
    headers={
        "Authorization": f"Bearer {os.environ['BIGQUERY_OAUTH_TOKEN']}",
        "x-goog-user-project": os.environ["GOOGLE_CLOUD_PROJECT"],
    },
    # Read-only by allowlist: the plain execute_sql tool is not enabled.
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
    system_instructions=(
        "You answer questions about opinions on Hacker News using the "
        f"bigquery MCP tools. The data lives in `{HN_TABLE}`; inspect its "
        "schema with get_table_info if needed. Prefer comments "
        "(type='comment') matching the topic in `text`, recent first, and "
        "skim enough of them to summarize the range of opinions with short "
        "quotes. Keep queries cheap: select only needed columns, filter by "
        "timestamp, LIMIT 50. Run BigQuery jobs in project "
        + os.environ["GOOGLE_CLOUD_PROJECT"]
    ),
    mcp_servers=[bigquery_mcp],
)

async def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "What do people on Hacker News think about Rust?"
    async with Agent(config) as agent:
        response = await agent.chat(question)
        print(await response.text())

asyncio.run(main())
