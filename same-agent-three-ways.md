# I built the same agent three ways: Interactions API, ADK, and the Antigravity SDK

Google's stack now gives you three genuinely different ways to build an agent: the [Interactions API](https://ai.google.dev/gemini-api/docs/interactions-overview) (the Gemini API's agent-era surface), [ADK](https://adk.dev/) (the framework), and the [Antigravity SDK](https://antigravity.google/docs/sdk/overview) (the harness behind the Antigravity CLI). The cleanest way to compare them is to build the same agent on all three and watch what changes: who supplies the agent loop, how you hand it tools, and which models are compatible. We're also going to deploy each one on Cloud Run.

The agent we're building answers one kind of question: "what does Hacker News think about X?" It queries `bigquery-public-data.hacker_news.full`, the public BigQuery dataset with all 49 million HN stories and comments, refreshed to about a day behind. Each version needs the same three abilities: turn a question into SQL, run it, and summarize the opinions it finds.

Each build also wires in BigQuery a different way: a hand-written function on the Interactions API, the first-party toolset on ADK, and MCP on the Antigravity SDK.

## Setup and follow along

For this, we need to set up two credentials:

```bash
export GOOGLE_API_KEY="..."   # get this at aistudio.google.com
gcloud auth application-default login
```

| Credential for | Local | Cloud Run |
|---|---|---|
| Model, Interactions API | API key | API key, from Secret Manager |
| Model, ADK and Antigravity | your Cloud account (`gcloud` login + `GOOGLE_GENAI_USE_ENTERPRISE=TRUE`) | service account |
| BigQuery, all three | gcloud login | service account |

Why the split: the way this post uses the Interactions API runs on the Gemini API, and the Gemini API authenticates with a key. ADK and the Antigravity SDK talk to your Cloud project and never touch a key.

More precisely, the Interactions API can address a model (`model=`) or an agent hosted on Google's side (`agent=`), where the platform runs the whole loop server-side with tools it can reach. Our tool is a local Python function, so this build uses `model=` and runs the tool loop itself. The Gemini Enterprise Agent Platform (formerly known as Vertex AI) has an experimental Interactions API of its own, but it rejected `model=` interactions with every model I tried.

BigQuery's free tier (1 TB of queries/month) easily covers the demo queries (scans of roughly 1 to 17 GB). Versions at time of writing: `google-genai 2.17.0`, `google-adk 2.6.2`, `google-antigravity 0.1.10`, model `gemini-3.6-flash`.

If you want to follow along, every snippet in this post is a [runnable file in this repo](same-agent-three-ways-code/).

## Method 1: Interactions API, you write the tool and the loop

`pip install google-genai google-cloud-bigquery`

The tool is a plain function, about 10 lines:

```python
def execute_sql(query: str) -> list[dict]:
    client = bigquery.Client()
    config = bigquery.QueryJobConfig(maximum_bytes_billed=20 * 10**9)
    rows = client.query_and_wait(query, job_config=config, max_results=50)
    return [{k: str(v) for k, v in dict(row).items()} for row in rows]
```

This runs whatever SQL the model wrote and returns up to 50 rows as plain dicts for the model to read. `maximum_bytes_billed` caps a single query at 20 GB of scanning, so no query gets expensive. There's no explicit credential handling because `bigquery.Client()` picks up the gcloud login from the local environment. On Cloud Run the same line silently uses the service account instead.

The model never sees the function's body, only what you declare, so the declaration carries the schema:

```python
execute_sql_tool = {
    "type": "function",
    "name": "execute_sql",
    "description": (
        "Run a BigQuery Standard SQL SELECT query against "
        "`bigquery-public-data.hacker_news.full`, the public Hacker News "
        "dataset (stories and comments since 2006). Columns: id INT, "
        "type STRING (story/comment/job/poll), title STRING (stories only), "
        "text STRING (body, HTML-escaped), `by` STRING (username), score INT, "
        "parent INT, descendants INT, timestamp TIMESTAMP, url STRING, "
        "dead BOOL, deleted BOOL. Returns at most 50 rows."
    ),
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}
```

The `parameters` block is minimal, one required string holding the SQL. The description is where the leverage is: it's the only place the model learns the table name and columns, and a better description gets you better SQL.

That leaves the tool loop, which you can run yourself in about a dozen lines:

```python
while True:
    calls = [s for s in interaction.steps if s.type == "function_call"]
    if not calls:
        break
    results = [{
        "type": "function_result",
        "name": step.name,
        "call_id": step.id,
        "result": [{"type": "text", "text": json.dumps(execute_sql(**step.arguments))}],
    } for step in calls]
    interaction = client.interactions.create(
        model=MODEL,
        input=results,
        system_instruction=INSTRUCTION,
        tools=[execute_sql_tool],
        previous_interaction_id=interaction.id,
    )
```

Each round executes whatever `function_call` steps the model produced, sends the results back as the next input, and repeats until a response has no function calls left. Note what never gets sent: the conversation history. The server already has it, and `previous_interaction_id` just points at the previous turn, so each request carries only what's new. The `client` is the SDK's entry point to the Gemini API, and creating it with no arguments makes it read `GOOGLE_API_KEY` from the environment locally. On Cloud Run the same key arrives as an env var mounted from Secret Manager (details below). The model does the rest: it decides what SQL to run and when it has enough to answer. ([Full file.](same-agent-three-ways-code/method1_interactions.py))

Why not MCP here? Because it's not supported yet. The [Interactions API docs](https://ai.google.dev/gemini-api/docs/interactions-overview) list it as a limitation: "Gemini 3 does not support remote MCP, this is coming soon."

**Verdict: the most code, the fewest dependencies, and total control.**

## Method 2: ADK, the framework brings the tools

`pip install google-adk google-cloud-dataplex google-cloud-bigquery`

```python
import google.auth
from google.adk import Agent
from google.adk.integrations.bigquery import BigQueryCredentialsConfig, BigQueryToolset
from google.adk.integrations.bigquery.config import BigQueryToolConfig, WriteMode

credentials, _ = google.auth.default()
toolset = BigQueryToolset(
    credentials_config=BigQueryCredentialsConfig(credentials=credentials),
    bigquery_tool_config=BigQueryToolConfig(write_mode=WriteMode.BLOCKED),
)
root_agent = Agent(name="hn_opinion_agent", model=..., instruction=..., tools=[toolset])
```

`BigQueryToolset` is ADK's built-in BigQuery integration: it ships `execute_sql` plus metadata tools like `get_table_info`, so the agent inspects the table schema itself instead of being told. `WriteMode.BLOCKED` makes it read-only in one line.

Auth never touches the API key. The BigQuery toolset wants an explicit credentials object, and `google.auth.default()` provides one: it returns the gcloud login from the local environment, plus a project ID this build ignores. The model side is just the env var: `GOOGLE_GENAI_USE_ENTERPRISE=TRUE` sends model calls through your Cloud account. On Cloud Run, the BigQuery queries and the model calls both run as the service account.

The framework runs the loop and keeps sessions, including the conversation history across turns: in memory here, in a database when you need it to persist. ([Full file.](same-agent-three-ways-code/method2_adk.py))

**Verdict: the least code for the most capability, with prebuilt tools that let the agent explore the data on its own.**

## Method 3: Antigravity SDK, the harness plus MCP

`pip install google-antigravity`

```python
from google.antigravity import Agent, LocalAgentConfig
from google.antigravity.types import McpStreamableHttpServer

bigquery_mcp = McpStreamableHttpServer(
    name="bigquery",
    type="http",
    url="https://bigquery.googleapis.com/mcp",
    headers={"Authorization": f"Bearer {token}",
             "x-goog-user-project": project},
    enabled_tools=["execute_sql_readonly", "get_table_info", ...],
)
config = LocalAgentConfig(system_instructions=..., mcp_servers=[bigquery_mcp])
async with Agent(config) as agent:
    response = await agent.chat(question)
```

This hands the harness a system instruction and one MCP server, and `agent.chat()` does everything: planning, tool calls, and the final summary come back in one response. The agent loop here is the one that powers the Antigravity CLI, including its built-in file and shell tools.

BigQuery arrives over MCP. `bigquery.googleapis.com/mcp` is Google's fully managed endpoint. It takes OAuth only (`gcloud auth print-access-token`). `enabled_tools` is the allowlist of MCP tools the agent is allowed to use. The endpoint offers both `execute_sql` and `execute_sql_readonly`, and listing only the readonly one is what makes this agent read-only. Model auth works like ADK's: your Cloud account locally, the service account on Cloud Run. ([Full file.](same-agent-three-ways-code/method3_antigravity.py))

Two things to know before picking this one:

- Gemini only. The Antigravity IDE offers Claude and GPT-OSS models; the SDK doesn't (local OpenAI-compatible servers like Ollama are the one escape hatch).
- Put your project ID in the system instructions. Every tool on the hosted endpoint has a required `projectId` argument that says which Cloud project runs the query, and it's the model that fills that argument in when it calls the tool.

**Verdict: a convenient path to an agent with built-in capabilities to edit files and run shell commands.**

## The comparison

| | Interactions API | ADK | Antigravity SDK |
|---|---|---|---|
| Who supplies the loop | you | the framework | the harness |
| BigQuery wiring | your function | first-party toolset | MCP (hosted endpoint) |
| Conversation state | server-side via `previous_interaction_id` | sessions, in memory or in a database | harness-managed, saved to disk and resumable |
| Models | Gemini, Gemma | widest: Gemini, Gemma, LiteLLM for the rest | Gemini (+ local OpenAI-compat) |
| MCP support | not yet ("coming soon") | `MCPToolset`, stdio + HTTP | `mcp_servers`, stdio + HTTP |

## Serving it

All three deploy on Cloud Run. The difference is how much of the service you write.

- **Interactions API**: wrap the loop in a small FastAPI app ([code](same-agent-three-ways-code/serving/method1/main.py)). Since conversation state is server-side, your service stays stateless; clients just send back `previous_interaction_id`. One catch: the Interactions API still can't use the service account, so this is the one service that needs an API key. Mount it from Secret Manager.
- **ADK**: no server code to write. `adk api_server` serves locally; `adk deploy cloud_run` generates the server, container, and deploy config ([code](same-agent-three-ways-code/serving/method2/hn_opinion_agent/agent.py)). Two catches: the toolset's extra dependencies (bigquery, dataplex) must be in the agent folder's own requirements.txt, and the deploy doesn't forward env vars, so set `GOOGLE_GENAI_USE_ENTERPRISE` on the service afterward. (Agent Runtime is the fully managed alternative if you'd rather not own a service.)
- **Antigravity SDK**: wrap `agent.chat()` yourself ([code](same-agent-three-ways-code/serving/method3/main.py)) and package it as a container image for Cloud Run. One serving-only change: the MCP Authorization header can't come from your laptop's gcloud login anymore; mint and refresh the token from the service account.

Locking the services down is quick. Deploy with `--no-allow-unauthenticated` and only callers you grant IAM access can reach them. To test, send an identity token (`curl -H "Authorization: Bearer $(gcloud auth print-identity-token)"`) or use `gcloud run services proxy`. For browser access, put IAP in front.

## A note on the service account

The service account needed almost no setup. Every Cloud Run service runs as an identity, and by default that's the project's default compute service account. That one identity covered the BigQuery queries for all three services, plus the model calls for the ADK and Antigravity builds. The single grant I added by hand was for the Interactions service: permission to read the API key secret (`roles/secretmanager.secretAccessor`, granted on the secret itself).

One caveat before copying this setup: the default account is broad. On many projects, mine included, it carries the project-level Editor role. For anything beyond a demo, create a dedicated service account per service with only the roles it needs, and pass it at deploy time with `--service-account`.

## Which one to use

This experience made it clearer to me that a sensible default for building an agent is ADK plus Cloud Run. You get a comprehensive toolset plus MCP support. Sessions, including the conversation history, are easy to manage. You can also use any model you want, not just Gemini and Gemma. However, if you want to understand how agents work, the Interactions API is a good way to do that. And if you want your agent to be able to edit files and run shell commands, the Antigravity SDK is a solid option as well.
