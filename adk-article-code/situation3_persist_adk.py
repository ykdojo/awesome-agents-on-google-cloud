"""The same restart-proof memory in ADK: swap the in-memory session service
for a database-backed one. Sessions are keyed by app, user, and session id,
so this scales past one transcript without new code.

Run it twice to see memory survive a restart:
    python situation3_persist_adk.py "My favorite city is Kyoto. Remember that."
    python situation3_persist_adk.py "What's my favorite city?"

Requires GOOGLE_API_KEY in the environment, plus:
    pip install "google-adk[db]" aiosqlite
"""

import asyncio
import sys

from google.adk import Agent, Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types

root_agent = Agent(
    name="assistant",
    model="gemini-3.6-flash",
    instruction="You are a concise assistant.",
)

async def main():
    session_service = DatabaseSessionService(db_url="sqlite+aiosqlite:///./sessions.db")
    runner = Runner(agent=root_agent, app_name="persist_demo", session_service=session_service)

    if await session_service.get_session(app_name="persist_demo", user_id="u1", session_id="demo") is None:
        await session_service.create_session(app_name="persist_demo", user_id="u1", session_id="demo")

    message = sys.argv[1] if len(sys.argv) > 1 else "What's my favorite city?"
    content = types.Content(role="user", parts=[types.Part(text=message)])
    async for event in runner.run_async(user_id="u1", session_id="demo", new_message=content):
        if event.content and event.content.parts and event.content.parts[0].text:
            print(event.content.parts[0].text.strip())

asyncio.run(main())
