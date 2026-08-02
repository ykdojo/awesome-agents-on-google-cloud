"""Persisting a chat with the raw SDK: dump the history to JSON, load it
back next run. No pickling needed; Content objects round-trip cleanly.

Run it twice to see memory survive a restart:
    python situation3_persist_direct.py "My favorite city is Kyoto. Remember that."
    python situation3_persist_direct.py "What's my favorite city?"

This covers one transcript. Multiple users, sessions per user, state that
outlives a conversation, tool-call events: that bookkeeping is yours to build.
Requires GOOGLE_API_KEY in the environment.
"""

import json
import os
import sys

from google import genai
from google.genai import types

client = genai.Client()

history = []
if os.path.exists("history.json"):
    with open("history.json") as f:
        history = [types.Content.model_validate(c) for c in json.load(f)]

chat = client.chats.create(model="gemini-3.6-flash", history=history)

message = sys.argv[1] if len(sys.argv) > 1 else "What's my favorite city?"
print(chat.send_message(message).text)

with open("history.json", "w") as f:
    json.dump([c.model_dump(exclude_none=True, mode="json") for c in chat.get_history()], f)
