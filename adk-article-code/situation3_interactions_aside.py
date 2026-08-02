"""A tool-using turn on the Interactions API, the surface Google's current
function-calling guide is written against. Tool execution is manual, but the
server keeps conversation state: you pass previous_interaction_id instead of
resending history.
Requires GOOGLE_API_KEY in the environment.
"""

import json

from google import genai

weather_tool = {
    "type": "function",
    "name": "get_weather",
    "description": "Get current weather for a city.",
    "parameters": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
}

def get_weather(city: str) -> dict:
    return {"city": city, "temp_c": 21, "conditions": "sunny"}

TOOLS = {"get_weather": get_weather}  # dispatch table: the model asks by name

client = genai.Client()

interaction = client.interactions.create(
    model="gemini-3.6-flash",
    input="What's the weather in Tokyo?",
    tools=[weather_tool],
)

for step in interaction.steps:
    if step.type == "function_call":
        print(f"  tool call: {step.name}({step.arguments})")
        result = TOOLS[step.name](**step.arguments)
        interaction = client.interactions.create(
            model="gemini-3.6-flash",
            input=[{
                "type": "function_result",
                "name": step.name,
                "call_id": step.id,
                "result": [{"type": "text", "text": json.dumps(result)}],
            }],
            tools=[weather_tool],
            previous_interaction_id=interaction.id,
        )

print(interaction.output_text.strip())
