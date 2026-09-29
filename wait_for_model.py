import time
from memory import get_mental_model

for attempt in range(20):
    m = get_mental_model("brand-voice")
    content = (m.get("content") or "") if isinstance(m, dict) else ""
    if content and "Generating content" not in content:
        print("\nReady. Full Brand Voice content:\n")
        print(content)
        break
    print(f"not ready yet (attempt {attempt + 1}/20), waiting 20s...")
    time.sleep(20)