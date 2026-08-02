"""Step 0 in ADK: a bare agent, no tools. Both messages run in the same
session, so the second one can refer back to the first, like the raw SDK's
chat object.
Requires GOOGLE_API_KEY in the environment.
"""

import asyncio

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

asyncio.run(main())
