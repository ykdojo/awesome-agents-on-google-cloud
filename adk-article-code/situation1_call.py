"""A single model call with the google-genai SDK. No agent, no framework.

Works identically for Gemini and Gemma: swap the model string.
Requires GOOGLE_API_KEY in the environment.
"""

from google import genai

client = genai.Client()

for model in ["gemini-3.6-flash", "gemma-4-26b-a4b-it"]:
    response = client.models.generate_content(
        model=model,
        contents="In one sentence: what is an AI agent?",
    )
    print(f"[{model}] {response.text.strip()}")
