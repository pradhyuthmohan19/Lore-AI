import time
from actions import ask_with_memory, ask_without_memory

QUESTIONS = [
    "Which post format should I focus on, and why?",
    "What are my followers asking me for the most?",
    "Which of my past posts should I take hook ideas from?",
]

for q in QUESTIONS:
    print("=" * 78)
    print("QUESTION:", q)
    print("\n--- WITHOUT MEMORY ---")
    print(ask_without_memory(q))
    time.sleep(5)  # stay under the Groq free-tier tokens-per-minute limit
    print("\n--- WITH HINDSIGHT MEMORY ---")
    print(ask_with_memory(q))
    time.sleep(5)