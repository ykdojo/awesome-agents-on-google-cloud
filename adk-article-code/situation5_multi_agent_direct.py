"""Multi-agent, hand-rolled on the raw SDK: each specialist is a function
that runs its own model call with its own tools, and a router model picks
which specialist function to call via automatic function calling.

It works, but it's flat: control always returns to the router, the
specialists share no state or history, and transfer semantics, streaming,
and error handling are yours to build.
Requires GOOGLE_API_KEY in the environment.
"""

from google import genai
from google.genai import types

client = genai.Client()
MODEL = "gemini-3.6-flash"

def get_weather(city: str) -> dict:
    """Get current weather for a city."""
    return {"city": city, "temp_c": 21, "conditions": "sunny"}

def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    """Convert an amount between currencies."""
    return {"result": round(amount * 0.0067, 2), "rate": 0.0067}

def ask_weather_agent(question: str) -> str:
    """Answer a weather question."""
    response = client.models.generate_content(
        model=MODEL,
        contents=question,
        config=types.GenerateContentConfig(
            system_instruction="Answer weather questions using the get_weather tool.",
            tools=[get_weather],
        ),
    )
    return response.text

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
print(response.text)
