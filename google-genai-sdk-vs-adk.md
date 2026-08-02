# Google GenAI SDK vs ADK: which one to use and when

[Agent Development Kit (ADK)](https://adk.dev/) is Google's open-source, code-first framework for building AI agents: you define an agent in Python (or Go, Java, TypeScript, Kotlin), hand it tools as plain functions, and the framework runs the loop, manages state, and deploys to Google Cloud. If you're already in the Google ecosystem, it's also the default by momentum: Google's own agent codelabs and guides now mostly open with `pip install google-adk`. But a framework existing is not an argument that your project needs it. So this post walks through seven situations, simple to complex, from one API call to a multi-agent service. Each one compares the [GenAI SDK](https://googleapis.github.io/python-genai/) (google-genai, the plain client library for the Gemini API) against ADK, on both Gemini and Gemma. At the end: what the alternatives on Google Cloud look like, and a one-table decision guide.

Here are the situations:

- **Situation 1**: a call, then a chat
- **Situation 2**: add tools
- **Situation 3**: conversation history that survives a restart
- **Situation 4**: long-term memory about your users
- **Situation 5**: more than one agent
- **Situation 6**: make it a service
- **Situation 7**: prototype to production

Each situation compares the two approaches and ends with a verdict. Wherever code tells the story, a runnable version is linked.

## Follow along

If you want to follow along, every snippet in this post is a [runnable file in this repo](https://github.com/ykdojo/awesome-agents-on-google-cloud/tree/main/adk-article-code), named after the situation it belongs to. At the time of writing, I used these versions: [google-adk 2.6.1](https://pypi.org/project/google-adk/), [google-genai 2.16.0](https://pypi.org/project/google-genai/), models `gemini-3.6-flash` and `gemma-4-26b-a4b-it`. Everything ran on the Gemini API free tier, no billing attached.

## Situation 1: a call, then a chat

The GenAI SDK baseline, [in full](https://github.com/ykdojo/awesome-agents-on-google-cloud/blob/main/adk-article-code/situation1_call.py):

```python
from google import genai

client = genai.Client()  # reads GOOGLE_API_KEY

response = client.models.generate_content(
    model="gemini-3.6-flash",
    contents="In one sentence: what is an AI agent?",
)
print(response.text)
```

This sends one prompt, asking what an AI agent is, and prints the model's one-sentence answer. Swap the model string to `gemma-4-26b-a4b-it` and the same code runs on an open-weights model. Gemma 4 [landed on the Gemini API in April 2026](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api) with the native system instructions and function calling that Gemma 3 lacked.

Multi-turn? The SDK's [chat object](https://googleapis.github.io/python-genai/#chats) tracks the conversation so you only ever send the new message ([full file](https://github.com/ykdojo/awesome-agents-on-google-cloud/blob/main/adk-article-code/situation1_chat.py)):

```python
chat = client.chats.create(model="gemini-3.6-flash")
print(chat.send_message("Name one famous AI agent from science fiction.").text)
print(chat.send_message("In one sentence: would it pass today's definition of an agent?").text)
```

This creates a chat object and sends two messages, the second referring back to the first. The model follows along because the chat object resends the accumulated history on every call.

The ADK version of both, for comparison ([full file](https://github.com/ykdojo/awesome-agents-on-google-cloud/blob/main/adk-article-code/situation1_adk.py)):

```python
from google.adk import Agent
from google.adk.runners import InMemoryRunner

root_agent = Agent(
    name="assistant",
    model="gemini-3.6-flash",
    instruction="You are a concise assistant.",
)

async def main():
    runner = InMemoryRunner(root_agent)
    await runner.run_debug([
        "Name one famous AI agent from science fiction.",
        "In one sentence: would it pass today's definition of an agent?",
    ])
```

This defines a bare agent, no tools, and sends the same two questions in one session. The second one can still refer back to the first because the session carries the history. It works, but you've imported a framework to do what three lines of SDK did. **Verdict: go with the GenAI SDK.**

## Situation 2: add tools

An agent in the minimal sense is a model, tools, and a loop: call the model, run the tool it asks for, feed the result back, repeat until it answers in text. You could write that loop by hand, but the SDK ships it as [automatic function calling](https://googleapis.github.io/python-genai/#automatic-python-function-support). Pass a plain Python function as a tool and the SDK generates the schema from the signature and docstring, runs calls when the model asks, and iterates up to 10 rounds by default, all inside one `generate_content()` call ([full file](https://github.com/ykdojo/awesome-agents-on-google-cloud/blob/main/adk-article-code/situation2_tools_direct.py)):

```python
def get_weather(city: str) -> dict:
    """Get current weather for a city."""
    return {"city": city, "temp_c": 21, "conditions": "sunny"}

response = client.models.generate_content(
    model="gemini-3.6-flash",
    contents="What's the weather in Tokyo?",
    config=types.GenerateContentConfig(tools=[get_weather]),
)
print(response.text)  # "The current weather in Tokyo is sunny with a temperature of 21°C."
```

The user asks for the weather in Tokyo. The model can't know that, so it asks for our `get_weather` function. The SDK runs it, hands the model the result, and you get the final answer, all in one call. It even works with `gemma-4-26b-a4b-it`: the [Gemma docs](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api) only show the manual style of function calling, but I ran the automatic version and it works.

The same agent in ADK ([full file](https://github.com/ykdojo/awesome-agents-on-google-cloud/blob/main/adk-article-code/situation2_tools_adk.py)):

```python
def get_weather(city: str) -> dict:
    """Get current weather for a city."""
    return {"city": city, "temp_c": 21, "conditions": "sunny"}

root_agent = Agent(
    name="weather_agent",
    model="gemini-3.6-flash",
    instruction="Answer weather questions using the get_weather tool.",
    tools=[get_weather],
)

async def main():
    runner = InMemoryRunner(root_agent)
    await runner.run_debug("What's the weather in Tokyo?")
```

This wraps the same weather tool in an ADK agent and asks the same question. The runner executes the turn and prints each event: tool call, tool result, final answer. Gemma works here too: change the model string to `gemma-4-26b-a4b-it` and it runs unchanged ([full file](https://github.com/ykdojo/awesome-agents-on-google-cloud/blob/main/adk-article-code/situation2_tools_adk_gemma.py)), since hosted Gemma 4 has native function calling. Self-hosting Gemma instead, with Ollama locally or [vLLM on Cloud Run GPUs](https://docs.cloud.google.com/run/docs/run-gemma-on-cloud-run), works too. ADK's [LiteLLM wrapper](https://adk.dev/agents/models/ollama/) points at any OpenAI-compatible endpoint.

The two versions are nearly the same length, and that's the honest core of this comparison: **ADK's value is not the loop.** "Use a framework so you don't have to write the tool loop" is an outdated argument. The loop is table stakes on both sides. **Verdict: if tools are all you need, still go with the GenAI SDK.** One caveat: if you might want to switch to non-Google models later, ADK's native LiteLLM support makes that a one-line model change.

## Situation 3: conversation history that survives a restart

Real apps have users who come back tomorrow. Everything above forgets on restart: the chat object's history lives in your process, and so does ADK's in-memory runner. On [Cloud Run](https://cloud.google.com/run) it's worse: with scale-to-zero and multiple instances, in-process state may not survive even between requests.

With the GenAI SDK, the fix is less painful than you might guess: just have the chat history round-trip through plain JSON ([full file](https://github.com/ykdojo/awesome-agents-on-google-cloud/blob/main/adk-article-code/situation3_persist_direct.py)):

```python
history = []
if os.path.exists("history.json"):
    with open("history.json") as f:
        history = [types.Content.model_validate(c) for c in json.load(f)]

chat = client.chats.create(model="gemini-3.6-flash", history=history)
print(chat.send_message(message).text)

with open("history.json", "w") as f:
    json.dump([c.model_dump(exclude_none=True, mode="json") for c in chat.get_history()], f)
```

This loads any saved history from a JSON file, continues the chat with it, and saves the updated history back. Run it once with "My favorite city is Kyoto", run it again in a fresh process asking "What's my favorite city?", and it remembers. This works fine for one transcript. But it's one transcript in one file. Multiple users, multiple sessions per user, state that outlives a conversation, a real database instead of a JSON file: all of that bookkeeping is now yours.

ADK makes that bookkeeping a constructor argument ([full file](https://github.com/ykdojo/awesome-agents-on-google-cloud/blob/main/adk-article-code/situation3_persist_adk.py)):

```python
session_service = DatabaseSessionService(db_url="sqlite+aiosqlite:///./sessions.db")
runner = Runner(agent=root_agent, app_name="persist_demo", session_service=session_service)
```

This swaps the session backend for a SQLite database, and the agent code doesn't change. Same two-run Kyoto test, same result. Sessions are now keyed by app, user, and session id, with [state scopes](https://adk.dev/sessions/state/) per session, per user (`user:`), and per app (`app:`). Moving to Postgres is a URL change (`postgresql+asyncpg://...`), and a managed backend is [one more option](https://adk.dev/sessions/session/). One gotcha I hit: ADK 2.x requires an async database driver, so it's `pip install "google-adk[db]" aiosqlite` and `sqlite+aiosqlite://`, not the plain `sqlite://` that many tutorials show.

A third option exists: the [Interactions API](https://ai.google.dev/gemini-api/docs/interactions), which Google's current [function calling guide](https://ai.google.dev/gemini-api/docs/function-calling) is written against, keeps conversation state server-side. You pass `previous_interaction_id` instead of resending history, and tools like `{"type": "google_search"}` and `{"type": "mcp_server", ...}` are built in ([full file](https://github.com/ykdojo/awesome-agents-on-google-cloud/blob/main/adk-article-code/situation3_interactions_aside.py)). But it stores conversation history only, it has no notion of users (mapping interaction IDs to your users is still your job), and retention is limited (1 day on the free tier, 55 days paid). It's a convenience, not a session store you own.

**Verdict: it depends on how much control you need. If server-kept history within the retention limits is enough, the Interactions API handles it for you. The moment you want the history in your own database, this is ADK's first clear win.**

## Situation 4: long-term memory about your users

History is only half of memory. The [previous post](https://ykdojo.github.io/awesome-agents-on-google-cloud/anatomy-of-an-ai-agent-on-google-cloud) drew the key distinction: **session state**, the scratchpad of the current conversation, versus **memory**, distilled facts that survive across sessions ("prefers metric units", not a transcript). Situation 3 was all session state. This one is about what your agent knows about a user next month.

The GenAI SDK has nothing in this category: you'd design the fact schema, decide when to extract facts from conversations, store them, and inject them into future prompts yourself.

ADK's first answer is user-scoped state. Give the agent a tool for saving facts ([full file](https://github.com/ykdojo/awesome-agents-on-google-cloud/blob/main/adk-article-code/situation4_memory_adk.py)):

```python
def remember(fact_name: str, fact_value: str, tool_context: ToolContext) -> dict:
    """Save a fact about the user for future conversations."""
    tool_context.state[f"user:{fact_name}"] = fact_value
    return {"saved": {fact_name: fact_value}}
```

Tell the agent "Remember that I prefer metric units" and it calls this tool, which stores the value under a `user:` key. Ask "What units do I prefer?" in a different session, in a fresh process, and it answers "metric". That's the whole mechanism: [state](https://adk.dev/sessions/state/) saved under a `user:` key is visible to every session belonging to that user, and it lives in the same database as situation 3's sessions, so it survives restarts.

The second answer is a pluggable [memory interface](https://adk.dev/sessions/memory/) whose managed backend is [Memory Bank](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank): instead of you deciding what to save, it uses the model to extract and consolidate facts about each user, which the agent recalls in later sessions.

**Verdict: ADK.**

## Situation 5: more than one agent

The GenAI SDK has no multi-agent primitive: no delegation, no handoff, no orchestration. The closest hand-rolled equivalent is to wrap each specialist as a plain function that runs its own model call with its own tools, and let a router model dispatch to them through the same automatic function calling from situation 2 ([full file](https://github.com/ykdojo/awesome-agents-on-google-cloud/blob/main/adk-article-code/situation5_multi_agent_direct.py)):

```python
def ask_finance_agent(question: str) -> str:
    """Answer a currency conversion question."""
    response = client.models.generate_content(
        model=MODEL,
        contents=question,
        config=types.GenerateContentConfig(
            system_instruction="Answer currency questions using the convert_currency tool.",
            tools=[convert_currency],
        ),
    )
    return response.text

response = client.models.generate_content(
    model=MODEL,
    contents="How much is 10000 yen in dollars?",
    config=types.GenerateContentConfig(
        system_instruction="Route each question to the right specialist.",
        tools=[ask_weather_agent, ask_finance_agent],
    ),
)
```

Asked how much 10,000 yen is in dollars, the router model calls `ask_finance_agent`, which runs its own model call with its own currency tool and returns the answer as a tool result. It works. But notice what it is: agents pretending to be functions. Control always returns to the router, the specialists share no history or state, and streaming, error handling, and any real transfer of control are yours to build.

ADK makes delegation a first-class concept instead ([full file](https://github.com/ykdojo/awesome-agents-on-google-cloud/blob/main/adk-article-code/situation5_multi_agent_adk.py)):

```python
root_agent = Agent(
    name="coordinator",
    model="gemini-3.6-flash",
    instruction="Route each question to the right specialist.",
    sub_agents=[weather_agent, finance_agent],
)
```

This defines a coordinator with two specialist sub-agents, one for weather and one for finance. Same yen question, but this time the coordinator actually transfers control to the finance agent, which owns the conversation until it's done. Zero routing code. The coordinator routes on the sub-agents' `description` strings.

For pipelines where the order is fixed, ADK 2.0's graph engine is the sharper tool ([full file](https://github.com/ykdojo/awesome-agents-on-google-cloud/blob/main/adk-article-code/situation5_workflow.py)):

```python
root_agent = Workflow(
    name="root_agent",
    edges=[("START", researcher, writer)],
)
```

Two agents, a researcher and a writer, wired in sequence: the researcher's output becomes the writer's input, no glue code. The same syntax scales to bigger, branching workflows. Google's own [Why we built ADK 2.0](https://developers.googleblog.com/why-we-built-adk-20/) frames it well: stop using the LLM for "routing, scheduling, and error handling that traditional code already excels at." Deterministic structure in code, LLM reasoning inside the nodes.

**Verdict: ADK.**

## Situation 6: make it a service

Your agent is a script. Users need an endpoint. With the GenAI SDK, the path is a hand-rolled FastAPI app: routes, session management, streaming, then `gcloud run deploy`. ADK ships the server:

```bash
adk api_server   # your agent folder becomes a REST API on :8000
```

I ran it, and one command turned the agent folder into a working API: endpoints for managing sessions and running the agent, streaming included, plus interactive docs, with zero server code written. `adk deploy cloud_run` puts that same server on Cloud Run, and a flag connects it to situation 3's database.

In short, ADK gives you a convenient command that wraps everything in a server at once. But writing your own server and deploying it in a container with `gcloud run deploy` is a well-worn path too. **Verdict: ADK is slightly more convenient, but the GenAI SDK path is also solid enough.**

## Situation 7: prototype to production

The gap between a demo and something you can operate is the part practitioners complain about most. As one widely-echoed take puts it, the biggest challenge isn't the framework, it's observability, evaluation, and error recovery. This is where ADK's case is strongest:

- **Evaluation.** With the GenAI SDK, you can score outputs with external services, but there's no recorder and no test format: you can't save yesterday's good conversation as a regression test. With ADK, chat with your agent in the [dev UI](https://adk.dev/runtime/web-interface/) (`adk web`), save the session as an evalset, and [`adk eval`](https://adk.dev/evaluate/) replays it in CI, scoring tool-call trajectories and final responses (exact match, text similarity, or an LLM judge).
- **Observability.** The GenAI SDK has no built-in instrumentation, and the community OTel package for it is still marked experimental and can only see model calls. ADK emits OpenTelemetry traces for every agent, tool, and model step. One env var points them at any OTLP collector, and [`--otel_to_cloud`](https://adk.dev/observability/traces/) sends them to Cloud Trace.
- **Resilience.** Both SDKs retry failed HTTP calls. Only ADK has semantics above that: a [plugin](https://adk.dev/integrations/reflect-and-retry/) that feeds tool errors back to the model for self-correction, and [resumability](https://adk.dev/runtime/resume/) that checkpoints events so a crashed or paused run resumes without redoing completed tool calls.

**Verdict: ADK's strongest argument.**

## The alternatives, still on Google Cloud

ADK is not the only framework that's compatible with Google Cloud. [Agent Runtime](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime), the managed runtime, also accepts LangGraph, LangChain, LlamaIndex, and AG2 agents, and anything containerized runs on Cloud Run regardless of framework. [LangGraph](https://www.langchain.com/langgraph) is the strongest cross-cloud alternative if portability is your priority.

## The decision guide

All seven situations in one table:

| Situation | Recommendation |
|---|---|
| 1. A call, or a chat | GenAI SDK |
| 2. A tool-using agent | GenAI SDK; ADK if you may want non-Google models later |
| 3. Conversation history that survives restarts | Interactions API if hands-off history is enough; ADK to own it |
| 4. Long-term memory about your users | ADK |
| 5. More than one agent | ADK |
| 6. Serving it on Cloud Run | Either; ADK saves you the server code |
| 7. Evals, tracing, error recovery | ADK |

The shortest honest version: **the GenAI SDK for prototypes, ADK for production.** A call, a chat, a tool loop: the GenAI SDK covers all of it with less machinery. But the moment you're hand-building sessions, delegation, serving, evals, or error recovery, you're not avoiding a framework, you're writing one. Escalate on real pain, not anticipation: ADK's tools are plain Python functions, so migrating later mostly means moving functions you already have.

## Go deeper

The first episode of Google's [Agent Factory podcast](https://www.youtube.com/watch?v=aLYrV61rJG4) covers exactly this question (agents, their frameworks, and when to use them), and [Stop guessing and start testing your AI agents with ADK](https://youtu.be/20W-tHXcsb4) on the Google Cloud Tech channel makes the eval case. From there, the [ADK foundation codelab](https://codelabs.developers.google.com/devsite/codelabs/build-agents-with-adk-foundation) and [adk-samples](https://github.com/google/adk-samples) are the fastest path from decision to working code.
