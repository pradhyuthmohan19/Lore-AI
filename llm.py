import os
import re
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# These two are confirmed available on this Groq key (checked with list_models.py) —
# don't guess new model ids here without checking that first, wrong ids 404 instead of
# falling back. Both are smaller than the primary (gpt-oss-120b) so they're on a separate,
# usually-less-drained quota bucket when the primary hits its daily token cap.
FALLBACK_MODELS = ["openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
MAX_OUT = 8000  # room for reasoning + a full 7-post JSON plan


def _clean(text):
    """Drop any <think>...</think> block some models put in the reply."""
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


def _call(model, prompt, max_tokens, extra=None):
    kwargs = dict(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=max_tokens,
    )
    if extra:
        kwargs["extra_body"] = extra
    response = client.chat.completions.create(**kwargs)
    choice = response.choices[0]
    if choice.finish_reason == "length":
        print(f"[LLM] WARNING: {model} hit the token limit ({max_tokens}); reply may be cut off")
    return _clean(choice.message.content)


def ask_llm(prompt, model="openai/gpt-oss-120b", max_tokens=MAX_OUT):
    errors = []
    try:
        # low reasoning effort keeps the hidden thinking short so the answer fits
        return _call(model, prompt, max_tokens, extra={"reasoning_effort": "low"})
    except Exception as e:
        errors.append(f"{model}: {e}")
        print(f"[LLM] {model} failed ({e})")
    for fb in FALLBACK_MODELS:
        try:
            print(f"[LLM] falling back to {fb}")
            return _call(fb, prompt, max_tokens)
        except Exception as e:
            errors.append(f"{fb}: {e}")
            print(f"[LLM] {fb} failed ({e})")
    raise RuntimeError(
        "All Groq models failed (likely hit a rate limit or daily token cap on your Groq "
        "account — check console.groq.com/settings/billing). Details: " + " | ".join(errors)
    )