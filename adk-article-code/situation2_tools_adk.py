"""The same weather agent in ADK. The framework owns the loop: schema
generation, tool dispatch, history, sessions, events, retries.

Swap the model string to "gemma-4-26b-a4b-it" and it runs on Gemma 4
unchanged (see situation2_tools_adk_gemma.py).
Requires GOOGLE_API_KEY in the environment.
"""

import asyncio

from google.adk import Agent
from google.adk.runners import InMemoryRunner

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

asyncio.run(main())
