"""The ADK weather agent on Gemma 4: the only change from situation2_tools_adk.py
is the model string. Hosted Gemma 4 has native function calling, so no
LiteLLM wrapper or prompt-parsing shim is needed.

For self-hosted Gemma (Ollama, vLLM on Cloud Run), point a LiteLlm wrapper
at the endpoint instead:
    from google.adk.models.lite_llm import LiteLlm
    model=LiteLlm(model="ollama_chat/gemma4", api_base="http://localhost:11434")
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
    model="gemma-4-26b-a4b-it",
    instruction="Answer weather questions using the get_weather tool.",
    tools=[get_weather],
)

async def main():
    runner = InMemoryRunner(root_agent)
    await runner.run_debug("What's the weather in Tokyo?")

asyncio.run(main())
