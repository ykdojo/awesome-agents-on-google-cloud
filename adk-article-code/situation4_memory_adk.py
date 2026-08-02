"""User-scoped memory in ADK: a tool saves a fact under a "user:" key, and
any future session with the same user can read it back. State lives in the
same SQLite database as situation 3's sessions, so it survives restarts.

Run it twice, in two DIFFERENT sessions, to see the fact cross over:
    python situation4_memory_adk.py session_a "Remember that I prefer metric units."
    python situation4_memory_adk.py session_b "What units do I prefer?"

Requires GOOGLE_API_KEY in the environment, plus:
    pip install "google-adk[db]" aiosqlite
"""

import asyncio
import sys

from google.adk import Agent, Runner
from google.adk.sessions import DatabaseSessionService
from google.adk.tools import ToolContext
from google.genai import types

def remember(fact_name: str, fact_value: str, tool_context: ToolContext) -> dict:
    """Save a fact about the user for future conversations."""
    tool_context.state[f"user:{fact_name}"] = fact_value
    return {"saved": {fact_name: fact_value}}

def recall(fact_name: str, tool_context: ToolContext) -> dict:
    """Look up a previously saved fact about the user."""
    return {fact_name: tool_context.state.get(f"user:{fact_name}", "unknown")}

root_agent = Agent(
    name="assistant",
    model="gemini-3.6-flash",
    instruction="Use the remember tool to save facts the user tells you, and the recall tool to look them up.",
    tools=[remember, recall],
)

async def main():
    session_service = DatabaseSessionService(db_url="sqlite+aiosqlite:///./sessions.db")
    runner = Runner(agent=root_agent, app_name="memory_demo", session_service=session_service)

    session_id = sys.argv[1] if len(sys.argv) > 1 else "session_a"
    if await session_service.get_session(app_name="memory_demo", user_id="u1", session_id=session_id) is None:
        await session_service.create_session(app_name="memory_demo", user_id="u1", session_id=session_id)

    message = sys.argv[2] if len(sys.argv) > 2 else "What units do I prefer?"
    content = types.Content(role="user", parts=[types.Part(text=message)])
    async for event in runner.run_async(user_id="u1", session_id=session_id, new_message=content):
        if event.content and event.content.parts and event.content.parts[0].text:
            print(event.content.parts[0].text.strip())

asyncio.run(main())
