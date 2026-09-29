from memory import recall_posts, reflect, get_mental_model, retain_post
from llm import ask_llm
import json, re, os

RULES = """Rules:
- Every number or date you cite must appear in the evidence below. Never estimate or round up counts.
- If the evidence gives no exact count, say "several" instead of inventing one.
- Quote durations exactly as written in the evidence (for example "139 days"). Never convert days into weeks or months.
- The data ends on 2026-08-31. Never refer to "today" or the present date.
- Engagement rate and views are different metrics. Name which one you mean.
- "N comments across M posts" means N comments and M posts. Never confuse the two.
- Only call something a pattern if at least 3 posts in the evidence show it. Only cite a feature (punctuation, word count) if at least 3 of the hooks you cite have it.
- When you cite a caption or hook, copy it exactly as written in the evidence.
- Only use words like "highest", "most", "always" or "consistently" if the evidence states that comparison across all posts. Otherwise say "among the posts shown".
- Do not invent timing, schedules, hashtags or plans. Never call a modified caption "exact".
- Do not claim a cause. If two things happen together, say they coincide.
- Use only hashtags and emojis that appear in the BRAND VOICE PROFILE or the evidence, spelled exactly as written.
- Do not invent names, places, products, series, scenes or plans that are not in the evidence.
- If the evidence is too thin, say so plainly."""

STYLE = """Formatting: write clean, friendly Markdown for a busy creator.
- Open with one bold sentence that directly answers the question.
- Then short sections. Use ### headings only when they help, plain bullets (one level), and at most one table (max 3 columns, one fact per cell, no line breaks inside cells).
- Put any caption the creator can post in a blockquote (start each line with > ) using real line breaks.
- Never write \\n, <br> or triple backticks. Keep the whole answer under 220 words."""


ASK_STYLE = r"""Formatting: Markdown for a busy creator. Keep the whole answer under 110 words.
- Line 1: one bold sentence that answers the question. Nothing before it.
- Then a heading written exactly as: ### Do this
- Then EXACTLY 3 bullets. Each starts with a 2 to 4 word bold label, a colon, then one short sentence (max 18 words) with the key figure or date from the evidence.
- Only if a ready-to-post caption helps, add ONE blockquote after the bullets (start each line with > ). Otherwise skip it.
- No tables, no other headings, no extra paragraphs. Never write \\n, <br> or triple backticks."""


def _meta(r):
    """Keep only small, safe fields from a Hindsight recall result (used for the UI trace)."""
    ents = r.get("entities") or []
    ents = [e if isinstance(e, str) else str(e.get("text") or e.get("name") or "") for e in ents if e]
    when = r.get("occurred_start") or r.get("mentioned_at") or ""
    score = next((r[k] for k in ("score", "similarity", "relevance") if isinstance(r.get(k), (int, float))), None)
    return {"type": str(r.get("type") or r.get("fact_type") or ""), "entities": [e for e in ents if e][:6],
            "date": str(when)[:10], "score": score}


def _recall_texts(query, limit=10, bank=None, trace=None):
    data = recall_posts(query, bank_id=bank)
    results = data.get("results", []) if isinstance(data, dict) else []
    texts = [r.get("text", "")[:700] for r in results]
    if trace is not None:
        trace.append({"op": "recall", "query": query, "found": len(texts), "used": texts[:limit],
                      "meta": [_meta(r) for r in results[:limit]],
                      "fields": sorted(results[0].keys()) if results else []})
    return texts[:limit]


def _bullets(items):
    return "\n".join(f"- {t}" for t in items) or "- (none found)"


def brand_voice(bank=None, trace=None):
    model = get_mental_model("brand-voice", bank_id=bank)
    content = (model.get("content") or "") if isinstance(model, dict) else ""
    if "Generating content" in content:
        content = ""
    if trace is not None:
        trace.append({"op": "mental model", "query": "brand-voice", "found": 1 if content else 0,
                      "used": [content[:400]] if content else []})
    return content


def ask_without_memory(question):
    return ask_llm(f"You are a content strategy assistant for a social media creator. "
                   f"You know nothing about this creator's history. Answer in clean Markdown, under 110 words: "
                   f"one bold sentence, then a heading '### Do this', then exactly 3 short bullets.\n\nQuestion: {question}")


def ask_with_memory(question, bank=None, trace=None, deep=False):
    voice = brand_voice(bank, trace)
    evidence = _recall_texts(question, 10, bank, trace)
    facts = _recall_texts(question + " exact totals, monthly figures, series status", 8, bank, trace)
    evidence = list(dict.fromkeys(evidence + facts))[:16]
    extra = ""
    if deep:  # reflect is expensive (10k-40k tokens); opt-in only
        data = reflect(question, bank_id=bank)
        extra = data.get("text", "") if isinstance(data, dict) else ""
        if trace is not None:
            trace.append({"op": "reflect", "query": question, "found": 1 if extra else 0, "used": [extra[:400]]})
    prompt = f"""You are a content strategist for this creator.

BRAND VOICE PROFILE:
{voice}

EVIDENCE FROM MEMORY:
{_bullets(evidence)}
{('SYNTHESIS FROM HINDSIGHT REFLECT:' + chr(10) + extra) if extra else ''}

{RULES}

Question: {question}
Answer specifically, citing dates and numbers from the evidence. Suggest a concrete next action.

{ASK_STYLE}"""
    return ask_llm(prompt)


def hook_pattern_draft(topic, bank=None, trace=None):
    top = _recall_texts("posts ranked in the top 10% for engagement rate or views, with their caption hook lines", 20, bank, trace)
    top = [t for t in top if "Instagram story" not in t][:10]
    formats = _recall_texts("format averaged reach views and engagement rate across all posts", 4, bank, trace)
    prompt = f"""You are a content strategist for this creator.

BRAND VOICE PROFILE:
{brand_voice(bank, trace)}

TOP-RANKED POSTS:
{_bullets(top)}

FORMAT PERFORMANCE (exact figures):
{_bullets(formats)}

{RULES}

Task: draft a post about: {topic}
Write these three parts in Markdown:
**Hook** - one opening line. Match the length and style of the caption hooks in the evidence and do not make it longer than the longest of them.
**Ready-to-post caption** - a blockquote with the hook, then 1 to 3 emojis chosen from emojis that appear in the evidence or brand voice (skip emojis if none appear), then 2 to 4 hashtags copied exactly from the evidence or brand voice (skip hashtags if none appear).
**Based on** - a short bullet list of the specific posts (with dates) the hook pattern comes from.

{STYLE}"""
    return ask_llm(prompt)


def reply_to_comment(comment, bank=None, trace=None):
    """Comment Reply Agent: draft a reply to one audience comment in the creator's own
    voice. Gets more personal the more saved reply examples exist (see save_reply_example) —
    first reply is generic-ish, later ones sound like the creator because memory has real
    examples of how they actually reply."""
    voice = brand_voice(bank, trace)
    examples = _recall_texts("an example of how this creator replied to a fan comment, in their own words", 6, bank, trace)
    examples = [e for e in examples if "replied:" in e]
    tone_ref = _recall_texts("top audience comments on posts and their theme", 6, bank, trace)
    prompt = f"""You are drafting an Instagram reply for this creator, in their own voice — short, warm, sounds like a real person typing back, not a brand.

BRAND VOICE PROFILE:
{voice}

{f"SAVED EXAMPLES OF HOW THIS CREATOR ACTUALLY REPLIES (match this style closely — this is the strongest signal you have):{chr(10)}{_bullets(examples)}{chr(10)}" if examples else "No saved reply examples yet for this creator — use the brand voice profile and keep it natural, not corporate."}

OTHER COMMENTS SEEN ON THIS ACCOUNT (tone reference only):
{_bullets(tone_ref[:4])}

{RULES}

The fan's comment: "{comment}"

Write ONLY the reply text itself — one to two short sentences, casual, no quotation marks around it, no hashtags, no "Reply:" prefix, no explanation. Use an emoji only if the brand voice or the examples show the creator using them."""
    return ask_llm(prompt).strip().strip('"').strip()


def _parse_str_array(raw, n):
    """Same tolerant JSON extraction as _parse_plan, but for a plain array of reply strings."""
    raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S)
    raw = re.sub(r"```(?:json)?", "", raw)
    m = re.search(r"\[.*\]", raw, flags=re.S)
    if not m:
        print("[REPLY-BATCH] no JSON array found. Raw reply:\n", raw)
        raise ValueError("The model did not return replies.")
    text = m.group(0)
    text = text.replace("“", "'").replace("”", "'")
    text = re.sub(r",\s*\]", "]", text)
    arr = json.loads(text, strict=False)
    arr = [str(x).strip() for x in arr if isinstance(x, (str, int, float))]
    while len(arr) < n:
        arr.append("(no reply drafted — click Draft replies again)")
    return arr[:n]


def reply_batch(comments_text, bank=None, trace=None):
    """The real pain point isn't drafting one reply — it's the pile of comments after every
    post. Paste the whole batch (one per line), get every reply back in one click, each in
    the creator's own voice. This is the actual automation: minutes of typing collapsed into
    one click, not a one-comment-at-a-time toy."""
    comments = [re.sub(r"^[-•\d.\)\s]+", "", c).strip() for c in (comments_text or "").splitlines()]
    comments = [c for c in comments if c][:20]
    if not comments:
        raise ValueError("Paste at least one comment to reply to.")

    voice = brand_voice(bank, trace)
    examples = _recall_texts("an example of how this creator replied to a fan comment, in their own words", 6, bank, trace)
    examples = [e for e in examples if "replied:" in e]
    tone_ref = _recall_texts("top audience comments on posts and their theme", 4, bank, trace)
    comments_block = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(comments))

    prompt = f"""You are drafting Instagram replies for this creator, in their own voice — short, warm, sounds like a real person typing back, not a brand.

BRAND VOICE PROFILE:
{voice}

{f"SAVED EXAMPLES OF HOW THIS CREATOR ACTUALLY REPLIES (match this style closely — this is the strongest signal you have):{chr(10)}{_bullets(examples)}{chr(10)}" if examples else "No saved reply examples yet for this creator — use the brand voice profile and keep it natural, not corporate."}

OTHER COMMENTS SEEN ON THIS ACCOUNT (tone reference only):
{_bullets(tone_ref)}

{RULES}

Here are {len(comments)} fan comments from the same post, in order:
{comments_block}

Task: write one reply per comment, each specific to that comment — never a generic reply reused across two comments, even if two comments are similar.
Each reply is one to two short sentences, casual, no quotation marks around it, no hashtags, no "Reply:" prefix, no explanation. Use an emoji only if the brand voice or the examples show the creator using them.
Never use the double quote character (") inside a reply; use single quotes (') instead.
Return ONLY a JSON array of exactly {len(comments)} strings, one reply per comment in the same order. No text before or after, no code fences."""

    raw = ask_llm(prompt)
    replies = _parse_str_array(raw, len(comments))
    if trace is not None:
        trace.append({"op": "reply_batch", "query": f"{len(comments)} comments", "found": len(replies), "used": replies})
    return [{"comment": c, "reply": r} for c, r in zip(comments, replies)]


def save_reply_example(comment, reply, bank=None, trace=None):
    """The creator approves/edits a drafted reply and saves it as 'this is how I'd say it' —
    retained as a memory so the NEXT reply this agent drafts is grounded in a real example,
    not just a generic voice profile. This is what makes replies visibly get more personal."""
    fact = f"When a fan commented \"{comment}\", the creator replied: \"{reply}\". This is a saved example of the creator's own reply style."
    retain_post(fact, bank_id=bank)
    if trace is not None:
        trace.append({"op": "retain", "query": "reply example", "found": 1, "used": [fact]})
    return fact


def audience_ask_digest(bank=None, trace=None):
    totals = _recall_texts("audience comment theme totals comments across posts between 2026-03 and 2026-08", 8, bank, trace)
    theme = ask_llm(f"""FACTS:
{_bullets(totals)}

Which audience comment theme has the highest total number of COMMENTS?
Reply with ONLY the theme name, nothing else.""").strip().splitlines()[0].strip("'\". ")

    monthly = _recall_texts(f"in each month the audience comment theme '{theme}' had comments across posts", 12, bank, trace)
    series = [t for t in _recall_texts("The last part of the series was part N, posted on a date. The series has had no new part for N days.", 25, bank, trace)
              if "series" in t.lower()][:5]
    related = _recall_texts(f"the creator's own posts and captions about {theme}", 6, bank, trace)
    prompt = f"""You are a content strategist analysing audience comments.

TOP THEME: {theme}

TOTALS:
{_bullets(totals)}

MONTH-BY-MONTH FACTS FOR THIS THEME:
{_bullets(monthly)}

SERIES STATUS:
{_bullets(series)}

CREATOR'S OWN RELATED POSTS:
{_bullets(related)}

BRAND VOICE PROFILE:
{brand_voice(bank, trace)}

{RULES}

Task:
1. State the top theme and list the per-month comment counts and post counts from the facts above.
2. Say whether the creator has addressed it recently. Use SERIES STATUS: give the last part number, the date of the last part, and the exact number of days quoted there (for example "139 days"). If SERIES STATUS is empty, say series status is unknown.
3. State the growth from the first month to the last month for this theme, and note whether it grew while no new part of a series was posted. Say the two coincide; do not claim a cause.
4. Draft a short caption in the creator's voice that tells the audience the request was heard. Use one exact number from the evidence and call it comments, not people. If you mention the next episode of a series, use the last part number in SERIES STATUS plus one. Do not invent scenes or characters.

{STYLE}"""
    return ask_llm(prompt)


AUTO_RULES = "\n".join(l for l in RULES.splitlines() if "hashtag" not in l.lower()) + r"""
- Do not invent timing or schedules.
- Hashtags: exactly 5 per post, each starting with #. Take them from the BRAND VOICE PROFILE or the evidence first. If fewer than 5 exist there, add short, relevant hashtags for this creator's niche.
- Emojis only if they appear in the BRAND VOICE PROFILE or the evidence."""


def _five_tags(given, fallback_texts):
    """Always return exactly 5 unique hashtags: the model's own first, then the most common ones seen in memory."""
    if isinstance(given, str):
        given = re.findall(r"#\w+", given)
    tags, seen = [], set()
    def add(t):
        t = "#" + str(t).strip().lstrip("#").replace(" ", "")
        if len(t) > 1 and t.lower() not in seen:
            seen.add(t.lower()); tags.append(t)
    for t in (given or []):
        add(t)
    freq = {}
    for txt in fallback_texts:
        for t in re.findall(r"#\w+", txt or ""):
            freq[t.lower()] = freq.get(t.lower(), 0) + 1
    for t, _ in sorted(freq.items(), key=lambda kv: -kv[1]):
        if len(tags) >= 5:
            break
        add(t)
    return tags[:5]


# Real numbers computed from data/*.csv (posts only, no stories): avg engagement % by weekday (Mon..Sun) and top hours (IST)
BEST = {
    "scratch-chaos-3": {"d": [7.2, 7.17, 7.19, 7.11, 7.23, 7.04, 7.25], "h": {23: 7.32, 11: 7.2, 17: 7.19}},
    "persona-fashion": {"d": [3.6, 3.32, 3.32, 3.6, 3.45, 3.89, 3.56], "h": {1: 7.46, 11: 7.33, 21: 7.23}},
    "persona-prasad-tech": {"d": [4.98, 4.76, 4.67, 5.31, 5.3, 4.93, 4.91], "h": {21: 5.54, 22: 5.3, 17: 5.15}},
    "persona-prasad-food": {"d": [5.75, 5.47, 5.03, 5.36, 5.22, 5.39, 5.05], "h": {20: 5.7, 18: 5.55, 12: 5.48}},
}
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
FULL = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"}


def _hr(h):
    return f"{(h + 11) % 12 + 1} {'am' if h < 12 else 'pm'}"


def _slot(bank, i):
    """Best day and hour for post i, from real data. Returns (label, is_best_day)."""
    b = BEST.get(bank) or next(iter(BEST.values()))
    hours = sorted(b["h"].items(), key=lambda kv: -kv[1])
    h, v = hours[i % len(hours)]
    top = b["d"].index(max(b["d"]))
    return f"{_hr(h)} IST (avg {v:.2f}% engagement at this hour)", i == top


def _parse_plan(raw):
    """Turn the model's reply into a list of post dicts, tolerating common JSON mistakes."""
    raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S)
    raw = re.sub(r"```(?:json)?", "", raw)
    m = re.search(r"\[.*\]", raw, flags=re.S)
    if not m:
        print("[PLAN] no JSON array found. Raw reply:\n", raw)
        raise ValueError("The model did not return a plan.")
    text = m.group(0)
    text = text.replace("\u201c", "'").replace("\u201d", "'")   # curly double quotes
    text = re.sub(r",\s*([\]}])", r"\1", text)                  # trailing commas
    try:
        plan = json.loads(text, strict=False)
    except json.JSONDecodeError as e:
        print("[PLAN] JSON error:", e, "\nRaw reply:\n", raw)
        raise
    return [p for p in plan if isinstance(p, dict)]


def _has_dupes(plan):
    """True if two days share (almost) the same suggestion/topic — the model copying one
    top post's idea into several days instead of varying each one."""
    seen = set()
    for p in plan:
        key = re.sub(r"\W+", "", (str(p.get("suggestion") or p.get("caption") or "")[:30])).lower()
        if not key:
            continue
        if key in seen:
            return True
        seen.add(key)
    return False


def _run_plan(prompt, n, label):
    """Ask for a plan, retrying (with a nudge) on bad JSON or on two days repeating the same hook."""
    plan = None
    for attempt in range(4):
        nudge = "" if attempt == 0 else f"\n\n(Attempt {attempt + 1}: the previous attempt repeated the same hook/topic on two different days — give every day a genuinely different hook, topic and caption this time.)"
        try:
            candidate = _parse_plan(ask_llm(prompt + nudge))[:n]
            if candidate and not _has_dupes(candidate):
                plan = candidate
                break
            plan = plan or candidate  # keep the best attempt so far as a fallback
        except (ValueError, json.JSONDecodeError) as e:
            print(f"[{label}] attempt {attempt + 1} failed: {e}")
    if not plan:
        raise ValueError("The model kept returning invalid JSON. Please click Plan my week again.")
    return plan


# Outcomes are ALSO retained as a real Hindsight memory (see record_outcome below) so the
# memory bank genuinely grows — but the plan-changing "proof" reads from this small local
# file instead of recall(). Hindsight's recall is semantic search over the whole bank and
# can take a few seconds to index a brand-new memory; a demo can't wait on that, so the
# outcome the creator JUST marked is available to the next plan instantly and reliably.
_OUTCOMES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outcomes_store.json")


def _load_outcomes():
    if os.path.exists(_OUTCOMES_PATH):
        try:
            with open(_OUTCOMES_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_outcome(bank, record):
    store = _load_outcomes()
    key = bank or "default"
    store.setdefault(key, []).append(record)
    store[key] = store[key][-30:]  # keep it small
    with open(_OUTCOMES_PATH, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)


def record_outcome(format_, topic, suggestion, liked, note="", bank=None, trace=None):
    """The creator marks a planned post as posted and says whether it worked. Saved two
    places: retained as a real Hindsight memory (grows the memory bank for real), and
    written to a small local file the NEXT plan reads instantly — that's the feedback loop
    that makes the agent visibly get better with use instead of staying static."""
    verdict = "worked well — the creator liked the result" if liked else "did not land — the creator was not happy with the result"
    fact = f"The creator posted a {format_} about '{topic}' ({suggestion}). It {verdict}."
    if note:
        fact += f" Creator's note: {note}"
    retain_post(fact, bank_id=bank)
    _save_outcome(bank, {"format": format_, "topic": topic, "suggestion": suggestion, "liked": bool(liked), "note": note, "fact": fact})
    if trace is not None:
        trace.append({"op": "retain", "query": "post outcome", "found": 1, "used": [fact]})
    return fact


def _past_outcomes(bank=None, trace=None):
    records = _load_outcomes().get(bank or "default", [])[-6:]
    texts = [r["fact"] for r in records]
    if trace is not None and texts:
        trace.append({"op": "recall", "query": "past post outcomes this creator marked (read instantly, not a semantic search)", "found": len(texts), "used": texts})
    return texts


def _parse_outcome(text):
    """Pull {format, topic, liked} back out of a retained outcome sentence (see
    record_outcome) — used to prove, in plain sight, exactly what the plan learned."""
    m = re.match(r"The creator posted a (\w+) about '(.*?)'.*?It (worked well|did not land)", text)
    if not m:
        return None
    return {"format": m.group(1), "topic": m.group(2), "liked": m.group(3) == "worked well"}


def _learned_summary(outcomes):
    """Deterministic (not model-written) proof of what this plan learned from feedback,
    so the creator can see exactly why a post was avoided or repeated — not just trust it."""
    items = [x for x in (_parse_outcome(t) for t in outcomes) if x]
    if not items:
        return "", items
    avoided = [x["topic"] for x in items if not x["liked"]]
    worked = [x["topic"] for x in items if x["liked"]]
    parts = []
    if avoided:
        parts.append(f"avoiding repeats of {', '.join(avoided[:3])} — you said {'it' if len(avoided)==1 else 'these'} didn't land")
    if worked:
        parts.append(f"leaning into {', '.join(worked[:3])} — you said {'it' if len(worked)==1 else 'these'} worked")
    return ("Learned from your feedback: " + "; ".join(parts) + ".") if parts else "", items


def weekly_plan(bank=None, trace=None):
    """Monday Autopilot: one full week of ready-to-post content built from this creator's own memory."""
    voice = brand_voice(bank, trace)
    formats = _recall_texts("format averaged reach views and engagement rate across all posts", 4, bank, trace)
    top = _recall_texts("posts ranked in the top 10% for engagement rate or views, with their caption hook lines", 20, bank, trace)
    top = [t for t in top if "Instagram story" not in t][:8]
    asks = _recall_texts("audience comment theme totals comments across posts between 2026-03 and 2026-08", 6, bank, trace)
    series = [t for t in _recall_texts("The last part of the series was part N, posted on a date. The series has had no new part for N days.", 12, bank, trace)
              if "series" in t.lower()][:3]
    outcomes = _past_outcomes(bank, trace)
    prompt = f"""You are a content strategist planning ONE week (7 posts, Monday to Sunday) for this creator.

BRAND VOICE PROFILE:
{voice}

FORMAT PERFORMANCE (exact figures):
{_bullets(formats)}

TOP-RANKED POSTS:
{_bullets(top)}

WHAT THE AUDIENCE ASKS FOR (comment themes):
{_bullets(asks)}

SERIES STATUS:
{_bullets(series)}
{f"{chr(10)}PAST OUTCOMES (posts this creator already tried and told you whether they worked — learn from these, do not repeat what did not land):{chr(10)}{_bullets(outcomes)}{chr(10)}" if outcomes else ""}
{AUTO_RULES}

Task: plan the week. Use only these formats: Reel, Carousel, Image (never Story). Favour the formats with the best figures, but keep the week varied. Cover what the audience asks for, and bring back a series that has gone quiet if SERIES STATUS shows one.
If PAST OUTCOMES is present, lean into what worked and avoid repeating what did not land.
TOP-RANKED POSTS is a reference for STYLE only — never copy the same hook or opening line into more than one day. Every one of the 7 days must have its own distinct topic, hook and caption; two days about the same idea is not allowed.
Never use the double quote character (") inside any value; use single quotes (') instead.
Return ONLY a JSON array of exactly 7 objects, in order Mon, Tue, Wed, Thu, Fri, Sat, Sun. No text before or after, no code fences. Each object has these keys:
"format": Reel, Carousel or Image
"topic": a short topic, at most 12 words
"suggestion": ONE plain sentence telling the creator exactly what to film or shoot, written like you're talking to them — for example "Film a get-ready-with-me trying on the kurta, twirl for the camera, end on a close-up of the fabric." Must match the format (a Reel suggestion describes short clips/motion, a Carousel suggestion describes a set of photos, an Image suggestion describes one shot).
"caption": the ready-to-post caption, catchy and punchy. Exactly 2 short lines, about 20 to 35 words in total (never less than one and a half lines). Separate the two lines with \\n. Do NOT put hashtags in the caption.
"hashtags": an array of exactly 5 hashtag strings
"why": one sentence naming the exact figure or post from the evidence that backs this choice. Do not add timing; that is added separately."""

    plan = _run_plan(prompt, 7, "PLAN")
    learned, learned_items = _learned_summary(outcomes)

    days = []
    for i, p in enumerate(plan):
        when, best = _slot(bank, i)
        cap = str(p.get("caption", "")).replace("\\n", "\n").strip()
        tags = _five_tags(p.get("hashtags"), top + [voice])
        days.append({
            "day": FULL[DAYS[i]], "format": p.get("format", ""), "topic": p.get("topic", ""),
            "suggestion": p.get("suggestion", ""),
            "caption": cap, "hashtags": tags, "why": p.get("why", ""), "when": when, "best": best,
        })

    md = ["**Your week is planned: 7 posts.**", ""]
    if learned:
        md += [f"*{learned}*", ""]
    for d in days:
        md += [f"### {d['day']}: {d['format']}{' (best day)' if d['best'] else ''}",
               f"**Make this:** {d['suggestion']}",
               "**Caption:**", f"> {d['caption'].replace(chr(10), chr(10) + '> ')}", ">", f"> {' '.join(d['hashtags'])}",
               f"**Why:** {d['why']}", ""]
    return {"answer": "\n".join(md), "days": days, "learned": learned, "learned_items": learned_items}


def notes_plan(notes_text, bank=None, trace=None):
    """Monday Autopilot, driven by the creator's own notes about what they're actually
    doing ("buy jeans at Inorbit Mall", "try the party outfit") instead of only their
    past post stats. One note in → one day planned. More notes than a week → the model
    picks the best 7. Memory still supplies the voice, hook style and best format."""
    notes = [re.sub(r"^[-•\d.\)\s]+", "", n).strip() for n in (notes_text or "").splitlines()]
    notes = [n for n in notes if n]
    if not notes:
        raise ValueError("Add at least one note about what you're doing over the next few days.")
    n_days = min(7, len(notes))

    voice = brand_voice(bank, trace)
    formats = _recall_texts("format averaged reach views and engagement rate across all posts", 4, bank, trace)
    top = _recall_texts("posts ranked in the top 10% for engagement rate or views, with their caption hook lines", 20, bank, trace)
    top = [t for t in top if "Instagram story" not in t][:8]
    notes_block = "\n".join(f"{i + 1}. {n}" for i, n in enumerate(notes))
    outcomes = _past_outcomes(bank, trace)

    prompt = f"""You are a content strategist. The creator jotted down real things they're doing over the next few days. Turn the ones with the most content potential into a posting plan.

BRAND VOICE PROFILE:
{voice}

FORMAT PERFORMANCE (exact figures):
{_bullets(formats)}

TOP-RANKED POSTS (style reference only — for hook length/tone, not topics):
{_bullets(top)}

THE CREATOR'S OWN NOTES, {len(notes)} total, in the order written:
{notes_block}
{f"{chr(10)}PAST OUTCOMES (posts this creator already tried and told you whether they worked — learn from these, do not repeat what did not land):{chr(10)}{_bullets(outcomes)}{chr(10)}" if outcomes else ""}
{AUTO_RULES}

Task: {"Use every note below — there are " + str(len(notes)) + f", so plan {n_days} day" + ("s" if n_days != 1 else "") + ", one per note, in the order written." if len(notes) <= 7 else f"Pick the {n_days} notes with the most content potential (most visual, most relatable, best fit with FORMAT PERFORMANCE) and turn each into one day, most time-sensitive or highest-potential note first."}
Each day's topic, hook and caption must be grounded in that day's specific note — never invent a note that wasn't written, and never reuse the same hook, topic or joke on two different days.
If PAST OUTCOMES is present, lean into what worked and avoid repeating what did not land.
Use only these formats: Reel, Carousel, Image (never Story) — pick whichever FORMAT PERFORMANCE shows tends to work best for that kind of moment.
Never use the double quote character (") inside any value; use single quotes (') instead.
Return ONLY a JSON array of exactly {n_days} objects. No text before or after, no code fences. Each object has these keys:
"note": the exact note text (or the relevant part of it) this day is based on
"format": Reel, Carousel or Image
"topic": a short topic, at most 12 words, grounded in the note
"suggestion": ONE plain sentence telling the creator exactly what to film or shoot for THIS note, written like you're talking to them — for example "Make a Reel: film yourself trying on the kurta, twirl for the camera, end on a close-up of the fabric." Must start by naming the format (Make a Reel / Make a Carousel / Post an Image) and must match that format (a Reel suggestion describes short clips/motion, a Carousel suggestion describes a set of photos, an Image suggestion describes one shot).
"caption": the ready-to-post caption, catchy and punchy. Exactly 2 short lines, about 20 to 35 words in total. Separate the two lines with \\n. Do NOT put hashtags in the caption.
"hashtags": an array of exactly 5 hashtag strings
"why": one short sentence: which note this came from, and why (content potential / format evidence)."""

    plan = _run_plan(prompt, n_days, "NOTES-PLAN")
    learned, learned_items = _learned_summary(outcomes)

    days = []
    for i, p in enumerate(plan):
        when, best = _slot(bank, i)
        cap = str(p.get("caption", "")).replace("\\n", "\n").strip()
        tags = _five_tags(p.get("hashtags"), top + [voice])
        days.append({
            "day": f"Day {i + 1}", "format": p.get("format", ""), "topic": p.get("topic", ""),
            "note": p.get("note", ""), "suggestion": p.get("suggestion", ""),
            "caption": cap, "hashtags": tags, "why": p.get("why", ""),
            "when": when, "best": best,
        })

    md = [f"**{len(days)} of your {len(notes)} notes turned into posts.**", ""]
    if learned:
        md += [f"*{learned}*", ""]
    for d in days:
        md += [f"### {d['day']}: {d['format']}{' (best day)' if d['best'] else ''}",
               f"**Make this:** {d['suggestion']}",
               "**Caption:**", f"> {d['caption'].replace(chr(10), chr(10) + '> ')}", ">", f"> {' '.join(d['hashtags'])}",
               f"**Why:** {d['why']}", ""]
    return {"answer": "\n".join(md), "days": days, "learned": learned, "learned_items": learned_items}