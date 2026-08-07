"""Method 2 served: the same ADK agent, laid out for `adk deploy cloud_run`.

No server code at all: ADK generates the FastAPI app, container, and deploy
config. On Cloud Run, credentials come from the service account via ADC.
"""

import os

import google.auth
from google.adk import Agent
from google.adk.integrations.bigquery import (
    BigQueryCredentialsConfig,
    BigQueryToolset,
)
from google.adk.integrations.bigquery.config import BigQueryToolConfig, WriteMode
from google.adk.models.google_llm import Gemini
from google.genai import types

HN_TABLE = "bigquery-public-data.hacker_news.full"

credentials, _ = google.auth.default()
toolset = BigQueryToolset(
    credentials_config=BigQueryCredentialsConfig(credentials=credentials),
    bigquery_tool_config=BigQueryToolConfig(write_mode=WriteMode.BLOCKED),
)

root_agent = Agent(
    name="hn_opinion_agent",
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
