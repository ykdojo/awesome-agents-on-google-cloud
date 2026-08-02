"""Multi-turn chat with the google-genai SDK. The chat object keeps the
conversation history for you (client-side, in your process): you only ever
send the new message.
Requires GOOGLE_API_KEY in the environment.
"""

from google import genai

client = genai.Client()

chat = client.chats.create(model="gemini-3.6-flash")
print(chat.send_message("Name one famous AI agent from science fiction.").text)
print(chat.send_message("In one sentence: would it pass today's definition of an agent?").text)
