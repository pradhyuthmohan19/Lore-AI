import os
import traceback
from flask import Flask, jsonify, request, send_from_directory
import actions
import memory
from seed_data import load_rows, pick_posts, fact_groups

# label -> Hindsight bank. Add a persona here after seeding its bank.
# "name" is what shows at the top of the app (the creator's name, not the data file name).
# "csv" is the data/*.csv this persona was seeded from — used only to show real numbers on
# the Memory bank tab (total posts, how many were retained, date range). Optional.
# "group" is optional: give two or more personas the same group name (e.g. one creator's
# separate Tech/Food/Lifestyle accounts) and the app shows them as one creator with a
# dropdown to switch between accounts, instead of separate buttons.
PERSONAS = {
    # One creator, Prasad, with three accounts (same "group" name shows them as one
    # creator with a dropdown to switch). All three now have their own dataset —
    # run the seed commands below once each to fill their memory banks.
    "prasad-fashion": {"name": "Prasad Fashion", "niche": "fashion", "bank": "persona-fashion", "csv": "data/fashion_creator_1000_realistic_2026.csv", "group": "Prasad"},
    "prasad-tech": {"name": "Prasad Tech", "niche": "tech reviews", "bank": "persona-prasad-tech", "csv": "data/prasad_tech.csv", "group": "Prasad"},
    "prasad-food": {"name": "Prasad Food", "niche": "food", "bank": "persona-prasad-food", "csv": "data/prasad_food.csv", "group": "Prasad"},
    # "chaos": {"name": "Chaos Goblin", "niche": "college memes", "bank": "scratch-chaos-3", "csv": "data/chaos.goblin.jpg.csv"},
    # "paisa": {"name": "Paisa with Pranav", "niche": "finance", "bank": "persona-paisa", "csv": "data/paisa.with.pranav.csv"},
    # "tanya": {"name": "Trendwatch Tanya", "niche": "trends", "bank": "persona-tanya", "csv": "data/trendwatch.tanya.csv"},
    # "meher": {"name": "FashionVerge", "niche": "fashion", "bank": "persona-meher", "csv": "data/meher.styles.csv"},
}

app = Flask(__name__, static_folder="static")


def bank_of(data):
    key = data.get("persona")
    if key not in PERSONAS:
        key = next(iter(PERSONAS))
    return PERSONAS[key]["bank"]


def persona_of(data):
    key = data.get("persona")
    if key not in PERSONAS:
        key = next(iter(PERSONAS))
    return PERSONAS[key]


def run(fn):
    trace = []
    try:
        return jsonify(fn(trace) | {"trace": trace})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e), "trace": trace}), 500


@app.errorhandler(Exception)
def api_errors(e):
    from werkzeug.exceptions import HTTPException
    if request.path.startswith("/api/"):
        code = e.code if isinstance(e, HTTPException) else 500
        if code == 500:
            traceback.print_exc()
        return jsonify({"error": f"{code}: {getattr(e, 'description', str(e))}", "trace": []}), code
    if isinstance(e, HTTPException):
        return e
    raise e


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/personas")
def personas():
    return jsonify([{"id": k, "name": v["name"], "niche": v.get("niche", ""), "group": v.get("group", v["name"])}
                     for k, v in PERSONAS.items()])


def _get(d, *keys, default=0):
    """Case/spelling-tolerant lookup — Hindsight's /stats field names for these
    sub-objects aren't pinned down in our docs, so try a few reasonable variants."""
    for k in keys:
        if isinstance(d, dict) and k in d:
            return d[k]
    return default


@app.get("/api/bank_stats")
def bank_stats():
    """Real numbers for the Memory bank tab. Tries Hindsight's own GET /stats for this
    bank first (actual memory/link counts, not guesses); if that call fails (bad bank id,
    offline, endpoint differs), falls back to counting straight from the source CSV."""
    p = persona_of({"persona": request.args.get("persona")})
    bank = p["bank"]
    try:
        s = memory.bank_stats(bank)
        total_nodes = _get(s, "total_nodes", "total_memories")
        if total_nodes:
            by_type = _get(s, "nodes_by_fact_type", "nodes_by_type", default={}) or {}
            links_by = _get(s, "links_by_link_type", "links_by_type", default={}) or {}
            world = _get(by_type, "world", "World")
            exp = _get(by_type, "experience", "Experience")
            obs = _get(by_type, "observation", "Observation", "observations")
            total_w = max(world + exp + obs, 1)
            links_total = max(_get(s, "total_links"), 1)
            link_rows = [[k.title(), v, round(100 * v / links_total)] for k, v in links_by.items()] or None
            return jsonify({
                "available": True, "live": True,
                "memories": total_nodes,
                "documents": _get(s, "total_documents"),
                "links": _get(s, "total_links"),
                "world": [world, round(100 * world / total_w)],
                "experience": [exp, round(100 * exp / total_w)],
                "observations": [obs, round(100 * obs / total_w)],
                "link_rows": link_rows,
                "pending": _get(s, "pending_operations"), "failed": _get(s, "failed_operations"),
                "last_write": _get(s, "last_memory_write_at", default=""),
            })
    except Exception as e:
        print(f"[bank_stats] live call failed for {bank}: {e}")

    csv_path = p.get("csv")
    if not csv_path or not os.path.exists(csv_path):
        return jsonify({"available": False})
    rows = load_rows(csv_path)
    posts = pick_posts(rows, 24)
    groups = fact_groups(rows)
    fact_count = sum(len(f) for _, f in groups)
    dates = sorted(r["date_ist"] for r in rows)
    return jsonify({
        "available": True, "live": False,
        "total_posts": len(rows),
        "posts_retained": len(posts),
        "digest_groups": len(groups),
        "facts_in_digests": fact_count,
        "documents": len(posts) + len(groups),
        "date_from": dates[0], "date_to": dates[-1],
    })


@app.post("/api/ask")
def ask():
    d = request.get_json(silent=True) or {}
    def go(t):
        bank = bank_of(d)
        out = {"answer": actions.ask_with_memory(d["question"], bank, t, bool(d.get("deep")))}
        if d.get("compare"):
            out["baseline"] = actions.ask_without_memory(d["question"])
        return out
    return run(go)


@app.post("/api/hook")
def hook():
    d = request.get_json(silent=True) or {}
    return run(lambda t: {"answer": actions.hook_pattern_draft(d["topic"], bank_of(d), t)})


@app.post("/api/autopilot")
def autopilot():
    d = request.get_json(silent=True) or {}
    return run(lambda t: actions.weekly_plan(bank_of(d), t))


@app.post("/api/notes_plan")
def notes_plan():
    d = request.get_json(silent=True) or {}
    return run(lambda t: actions.notes_plan(d.get("notes", ""), bank_of(d), t))


@app.post("/api/mark_posted")
def mark_posted():
    d = request.get_json(silent=True) or {}
    def go(t):
        fact = actions.record_outcome(
            d.get("format", ""), d.get("topic", ""), d.get("suggestion", ""),
            bool(d.get("liked")), d.get("note", ""), bank_of(d), t,
        )
        return {"answer": fact}
    return run(go)


@app.post("/api/reply")
def reply():
    d = request.get_json(silent=True) or {}
    return run(lambda t: {"answer": actions.reply_to_comment(d.get("comment", ""), bank_of(d), t)})


@app.post("/api/reply_batch")
def reply_batch():
    d = request.get_json(silent=True) or {}
    return run(lambda t: {"replies": actions.reply_batch(d.get("comments", ""), bank_of(d), t)})


@app.post("/api/save_reply")
def save_reply():
    d = request.get_json(silent=True) or {}
    def go(t):
        fact = actions.save_reply_example(d.get("comment", ""), d.get("reply", ""), bank_of(d), t)
        return {"answer": fact}
    return run(go)


if __name__ == "__main__":
    app.run(port=5000, debug=False, threaded=True)