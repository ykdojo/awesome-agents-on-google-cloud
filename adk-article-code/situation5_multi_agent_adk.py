"""Multi-agent delegation in ADK: a coordinator routes each question to the
right specialist. The routing is LLM-driven; there is no routing code to
write, only descriptions for the coordinator to go on.
Requires GOOGLE_API_KEY in the environment.
"""

import asyncio

from google.adk import Agent
from google.adk.runners import InMemoryRunner

def get_weather(city: str) -> dict:
    """Get current weather for a city."""
    return {"city": city, "temp_c": 21, "conditions": "sunny"}

def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    """Convert an amount between currencies."""
    return {"result": round(amount * 0.0067, 2), "rate": 0.0067}

weather_agent = Agent(
    name="weather_agent",
    model="gemini-3.6-flash",
    description="Handles weather questions.",
    instruction="Answer weather questions using the get_weather tool.",
    tools=[get_weather],
)

finance_agent = Agent(
    name="finance_agent",
    model="gemini-3.6-flash",
    description="Handles currency conversion questions.",
    instruction="Answer currency questions using the convert_currency tool.",
    tools=[convert_currency],
)

root_agent = Agent(
    name="coordinator",
    model="gemini-3.6-flash",
    instruction="Route each question to the right specialist.",
    sub_agents=[weather_agent, finance_agent],
)

async def main():
    runner = InMemoryRunner(root_agent)
    await runner.run_debug("How much is 10000 yen in dollars?")

asyncio.run(main())
