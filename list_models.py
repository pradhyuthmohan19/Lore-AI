"""One-off helper: prints every model id your GROQ_API_KEY can actually use.
Run: python list_models.py
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()
r = requests.get(
    "https://api.groq.com/openai/v1/models",
    headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
)
if r.status_code != 200:
    print("Could not list models:", r.status_code, r.text)
else:
    ids = sorted(m["id"] for m in r.json().get("data", []))
    print(f"{len(ids)} models available to this key:\n")
    for i in ids:
        print(" -", i)