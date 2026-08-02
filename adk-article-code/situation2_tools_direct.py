"""The google-genai SDK's automatic function calling.

Pass a plain Python function as a tool and the SDK builds the schema from
the signature and docstring, runs the call-execute-respond loop client-side
(up to 10 rounds by default), and hands you the final text. One call, no
hand-rolled loop. Works with Gemini and hosted Gemma 4.
Requires GOOGLE_API_KEY in the environment.
"""

from google import genai
from google.genai import types

def get_weather(city: str) -> dict:
    """Get current weather for a city."""
    return {"city": city, "temp_c": 21, "conditions": "sunny"}

client = genai.Client()

for model in ["gemini-3.6-flash", "gemma-4-26b-a4b-it"]:
    response = client.models.generate_content(
        model=model,
        contents="What's the weather in Tokyo?",
        config=types.GenerateContentConfig(tools=[get_weather]),
    )
    print(f"[{model}] {response.text.strip()}")
