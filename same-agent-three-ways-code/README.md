# Code for "the same agent, three ways"

One agent ("what does Hacker News think about X?") over the public BigQuery
Hacker News dataset, built on three runtimes. Each method is self-contained and
takes the question as an optional CLI argument.

```bash
pip install -r requirements.txt
export GOOGLE_API_KEY="your-key-from-aistudio.google.com"
gcloud auth application-default login   # BigQuery runs as you, free tier OK
python method1_interactions.py "What do people on HN think about Rust?"
```

| File | What it shows |
|---|---|
| `method1_interactions.py` | Interactions API: hand-written execute_sql tool, you run the loop, server keeps state |
| `method2_adk.py` | ADK: the first-party BigQuery toolset, framework runs the loop, agent discovers schema |
| `method3_antigravity.py` | Antigravity SDK: prepackaged harness, BigQuery via Google's hosted MCP endpoint |
| `method3_container.sh` | Runs method 3 in a Linux container (no google-antigravity wheel for Intel macOS) |
| `_run_with_gcloud_creds.py` | Test-only ADC shim for this machine, not article material |

Test status (2026-08-06):

- Method 1: VERIFIED end to end on the Gemini API free tier (`gemini-3.6-flash`);
  strong answer with real quotes and usernames.
- Method 2: VERIFIED on Gemini Enterprise Agent Platform, the platform formerly
  named Vertex AI; the API and env vars keep the old name
  (`GOOGLE_GENAI_USE_ENTERPRISE=TRUE`, location `global`); real agent-issued SELECTs confirmed in BigQuery job history.
  Gotchas: needs backoff retries (in the file) because one question is 4-6
  model calls; the toolset's `search_catalog` tool 403s on public datasets
  (`dataplex.projects.search` denied on `bigquery-public-data`) and the agent
  routes around it.
- Method 3: VERIFIED end to end on GEAP + the hosted BigQuery MCP endpoint
  (real usernames, 2026-fresh threads in the answer). Gotcha: the MCP tools
  take a required projectId argument; name the project in the system instructions.
  `Dockerfile.method3` bakes the image (`method3-antigravity`) for fast starts.

Serving (Cloud Run, us-central1, all IAM-gated): all three smoke-tested and
working. hn-agent-interactions uses the API key from Secret Manager
(Interactions API is Gemini-API-only, GEAP rejects it) and must run a flash
model: pro models have limit 0 on the free tier (the earlier "blocked" state
was `HN_AGENT_MODEL=gemini-3.1-pro-preview`, not the daily reset; switched to
`gemini-3.6-flash` 2026-08-07 and verified).

Quota notes: free tier measured at 5 requests/min AND 20 requests/day per
model; agent loops burst through both. GEAP (ex-Vertex) on a billed project has no such
caps (transient 429s handled by retries). `HN_AGENT_MODEL` switches model.
