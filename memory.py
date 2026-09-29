import os
import requests
from dotenv import load_dotenv
 
load_dotenv()
 
BASE_URL = os.getenv("HINDSIGHT_BASE_URL")
BANK_ID = os.getenv("HINDSIGHT_BANK_ID")
API_KEY = os.getenv("HINDSIGHT_API_KEY")
 
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}
 
 
def _url(path, bank_id=None):
    return f"{BASE_URL}/v1/default/banks/{bank_id or BANK_ID}{path}"
 
 
def retain_post(content, bank_id=None):
    r = requests.post(_url("/memories", bank_id), headers=HEADERS,
                      json={"items": [{"content": content}]})
    print(f"[HINDSIGHT] RETAIN  {r.status_code} | {content[:90]}...")
    return r.json()
 
 
def retain_many(contents, bank_id=None):
    """Retain several short facts in ONE request (each becomes its own item)."""
    r = requests.post(_url("/memories", bank_id), headers=HEADERS,
                      json={"items": [{"content": c} for c in contents]})
    print(f"[HINDSIGHT] RETAIN x{len(contents)} {r.status_code} | {contents[0][:80]}...")
    return r.json()
 
 
def recall_posts(query, bank_id=None):
    r = requests.post(_url("/memories/recall", bank_id), headers=HEADERS,
                      json={"query": query})
    data = r.json()
    count = len(data.get("results", [])) if isinstance(data, dict) else 0
    print(f"[HINDSIGHT] RECALL  {r.status_code} | {count} memories | {query[:70]}")
    return data
 
 
def reflect(query, bank_id=None):
    r = requests.post(_url("/reflect", bank_id), headers=HEADERS,
                      json={"query": query})
    data = r.json()
    tokens = data.get("usage", {}).get("total_tokens", "?") if isinstance(data, dict) else "?"
    print(f"[HINDSIGHT] REFLECT {r.status_code} | {tokens} tokens | {query[:70]}")
    return data
 
 
def create_mental_model(model_id, name, source_query, bank_id=None):
    body = {
        "id": model_id,
        "name": name,
        "source_query": source_query,
        "trigger": {"refresh_after_consolidation": True},
    }
    r = requests.post(_url("/mental-models", bank_id), headers=HEADERS, json=body)
    print(f"[HINDSIGHT] CREATE MENTAL MODEL {r.status_code} | {model_id}")
    return r.json()
 
 
def list_mental_models(bank_id=None):
    r = requests.get(_url("/mental-models", bank_id), headers=HEADERS)
    print(f"[HINDSIGHT] LIST MENTAL MODELS {r.status_code}")
    return r.json()
 
 
def get_mental_model(model_id, bank_id=None):
    r = requests.get(_url(f"/mental-models/{model_id}", bank_id), headers=HEADERS)
    data = r.json()
    preview = (data.get("content") or "")[:200].replace("\n", " ") if isinstance(data, dict) else ""
    print(f"[HINDSIGHT] GET MENTAL MODEL {r.status_code} | {model_id} | {preview}")
    return data


def bank_stats(bank_id=None):
    """Real numbers for a bank, straight from Hindsight (not guessed from the CSV):
    total memories, documents, links, the world/experience/observation split, and
    consolidation status. Used by the Memory bank tab."""
    r = requests.get(_url("/stats", bank_id), headers=HEADERS)
    data = r.json()
    print(f"[HINDSIGHT] STATS   {r.status_code} | {bank_id or BANK_ID}")
    return data if isinstance(data, dict) else {}