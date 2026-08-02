# Code for "To ADK or not to ADK"

Every file is a self-contained, runnable script, named after the situation in the article it belongs to. All of them ran successfully against the Gemini API free tier on 2026-08-01 with `google-genai 2.16.0` and `google-adk 2.6.1` (Python 3.10+).

```bash
pip install -r requirements.txt
export GOOGLE_API_KEY="your-key-from-aistudio.google.com"
python situation1_call.py
```

| File | What it shows |
|---|---|
| `situation1_call.py` | One model call, no framework; same code for Gemini and Gemma 4 |
| `situation1_chat.py` | Multi-turn chat; the SDK keeps history client-side |
| `situation1_adk.py` | The same two things in ADK: a bare agent, two turns, one session |
| `situation2_tools_direct.py` | The SDK's automatic function calling: the agent loop built in |
| `situation2_tools_adk.py` | The same tool-using agent in ADK |
| `situation2_tools_adk_gemma.py` | The ADK agent on Gemma 4: a one-string change |
| `situation3_persist_direct.py` | Raw persistence: chat history round-trips through JSON |
| `situation3_persist_adk.py` | ADK persistence: swap in a database session service (run twice) |
| `situation3_interactions_aside.py` | The Interactions API: server-side state via previous_interaction_id |
| `situation4_memory_adk.py` | User-scoped memory: a fact saved in one session, recalled in another |
| `situation5_multi_agent_direct.py` | Hand-rolled multi-agent on the raw SDK: specialists wrapped as functions |
| `situation5_multi_agent_adk.py` | A coordinator delegating to specialist sub-agents, zero routing code |
| `situation5_workflow.py` | An ADK 2.0 workflow graph: two agents wired in sequence |
| `situation6_service.md` | Serving: adk api_server and adk deploy cloud_run (commands, not code) |
| `situation7_production.md` | Evals, tracing, resilience: the commands and config (not code) |

Heads-up on the free tier: quotas are per model per day and tight (we measured 20 requests/day/model). Space your runs out, or attach billing.
