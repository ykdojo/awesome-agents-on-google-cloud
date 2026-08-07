"""Method 2: the same agent in ADK with the first-party BigQuery toolset.

The framework owns the loop and ships the tools: execute_sql plus metadata
tools (get_table_info, list_table_ids, ...), so the agent can discover the
schema itself instead of being told. WriteMode.BLOCKED makes it read-only.

Note the import path: google.adk.tools.bigquery is deprecated as of ADK 2.6
in favor of google.adk.integrations.bigquery, and the toolset needs the
google-cloud-dataplex package installed.

Requires your Cloud account, no API key: GOOGLE_GENAI_USE_ENTERPRISE=TRUE,
GOOGLE_CLOUD_PROJECT, and application default credentials.
"""

import asyncio
import os
import sys

import google.auth
from google.adk import Agent
from google.adk.integrations.bigquery import (
    BigQueryCredentialsConfig,
    BigQueryToolset,
)
from google.adk.integrations.bigquery.config import BigQueryToolConfig, WriteMode
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import types

HN_TABLE = "bigquery-public-data.hacker_news.full"

credentials, _ = google.auth.default()
toolset = BigQueryToolset(
    credentials_config=BigQueryCredentialsConfig(credentials=credentials),
    bigquery_tool_config=BigQueryToolConfig(write_mode=WriteMode.BLOCKED),
)

root_agent = Agent(
    name="hn_opinion_agent",
    # Agent loops burst through per-minute quotas: one question is several
    # model calls. Backoff-retry on 429 instead of dying mid-answer.
    model=Gemini(
        model=os.environ.get("HN_AGENT_MODEL", "gemini-3.6-flash"),
        retry_options=types.HttpRetryOptions(attempts=6, initial_delay=20, max_delay=80),
    ),
    instruction=(
        "You answer questions about opinions on Hacker News using the BigQuery "
        f"tools. The data lives in `{HN_TABLE}`; inspect its schema with "
        "get_table_info if needed. Prefer comments (type='comment') matching "
        "the topic in `text`, recent first, and skim enough of them to "
        "summarize the range of opinions with short quotes. Keep queries "
        "cheap: select only needed columns, filter by timestamp, LIMIT 50."
    ),
    tools=[toolset],
)

async def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "What do people on Hacker News think about Rust?"
    runner = InMemoryRunner(root_agent)
    await runner.run_debug(question)

asyncio.run(main())
