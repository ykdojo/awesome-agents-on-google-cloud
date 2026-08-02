"""Where ADK pulls ahead: a two-step workflow as a graph. ADK 2.0's
Workflow wires agents (and plain functions) into a graph with routing,
fan-out, retries, and human-in-the-loop pauses. Hand-rolling this on the
raw API means writing your own orchestrator.
Requires GOOGLE_API_KEY in the environment.
"""

import asyncio

from google.adk import Agent, Workflow
from google.adk.runners import InMemoryRunner

researcher = Agent(
    name="researcher",
    model="gemini-3.6-flash",
    instruction="List three facts about the topic the user gives you. Be terse.",
)

writer = Agent(
    name="writer",
    model="gemini-3.6-flash",
    instruction="Turn the facts you are given into a single punchy sentence.",
)

root_agent = Workflow(
    name="root_agent",
    edges=[("START", researcher, writer)],
)

async def main():
    runner = InMemoryRunner(root_agent)
    await runner.run_debug("the Gemini API")

asyncio.run(main())
