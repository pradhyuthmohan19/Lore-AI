# Lore AI – Memory-Powered Content Strategy Agent

Lore AI is a content strategy agent that uses Hindsight to build a persistent memory of every post a creator has made — what they posted, what worked, what didn't, and how they talk to their audience. Instead of generating generic content ideas from nothing, Lore AI synthesizes a creator's entire posting history — past topics, engagement patterns, saved reply voice, outcome feedback — into grounded, specific suggestions that actually reflect this creator's account.

**Author:** Pradhyuth Mohan ([GitHub](https://github.com/pradhyuthmohan19))

## Why Lore AI?

Most AI content tools give you a generic caption generator with zero memory of your account. Lore AI gives you an agent that remembers what happened on every previous post:

- What topics has this creator already covered, and which ones flopped?
- What time and day does this specific account's audience actually engage?
- What's the creator's own voice when replying to fans — not a generic tone?
- Did the last suggestion work? Should the next plan repeat it or avoid it?

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Flask (Python) |
| Language | Python |
| Frontend | Vanilla JS, HTML, CSS |
| Memory Engine | Hindsight (Vectorize) |
| LLM Backend | Groq (`openai/gpt-oss-120b`, with automatic fallback models) |
| Data Layer | CSV-seeded post history, per-account JSON outcome cache |

## Features

#### 1. Plan From Your Own Notes
Paste rough notes about your week and get a full content plan back — exact format, concrete suggestion (what to actually film or shoot), caption, hashtags, and best posting day/time, all grounded in this creator's real past posts.

#### 2. Multi-Account Intelligence
One creator can run several accounts (Tech, Food, Fashion, etc.) from a single dropdown. Each account has its own Hindsight memory bank, its own post history, and its own best-time-to-post data — never mixed together.

#### 3. Outcome Learning Loop
Mark any suggestion 👍 worked or 👎 didn't land. The very next plan generated shows a "Learned from your feedback" banner naming the exact past topics it's avoiding or leaning into — visible proof the agent is using real feedback, not just guessing.

#### 4. Batch Comment Reply Automation
Paste every comment on a post at once. One LLM call returns a matched reply for each comment, written in the creator's own saved reply voice — solving the actual creator pain point of replying to dozens of comments, not a one-comment-at-a-time toy.

#### 5. Memory Bank Transparency
A live tab shows real numbers pulled straight from the creator's Hindsight bank — total memories, documents, links, and exactly which memories were recalled to produce each answer — so the agent is never a black box.

## Project Structure

```
Content Strategy Agent/
├── app.py                  # Flask routes / API
├── actions.py               # Core agent logic (planning, outcomes, replies)
├── llm.py                   # Groq LLM client + fallback chain
├── memory.py                # Hindsight memory wrapper
├── seed_data.py              # Turns a creator's CSV into Hindsight memories
├── setup_persona.py          # One-time memory bank setup per persona
├── list_models.py            # Utility: lists Groq models available to your key
├── outcomes_store.json       # Local cache of 👍/👎 outcomes (proof-of-learning)
├── requirements.txt
├── .env.example
├── data/                     # Per-account CSV post histories
│   ├── fashion_creator_1000_realistic_2026.csv
│   ├── prasad_tech.csv
│   └── prasad_food.csv
└── static/
    └── index.html             # Frontend UI
```

## Getting Started

### Prerequisites
- Python 3.10+
- A [Groq API key](https://console.groq.com)
- A Hindsight API key

### Installation
```bash
git clone https://github.com/pradhyuthmohan19/Lore-Ai.git
cd "Content Strategy Agent"
pip install -r requirements.txt
cp .env.example .env
```
Fill in your keys in `.env`.

### Seed a Persona's Memory Bank (one-time, per account)
```bash
python setup_persona.py --persona prasad-fashion
python setup_persona.py --persona prasad-tech
python setup_persona.py --persona prasad-food
```

### Run the App
```bash
python app.py
```
Open `http://localhost:5000` in your browser.

## Demo Flow

1. **Pick an account** — switch between Prasad Fashion / Tech / Food from the dropdown.
2. **Monday Autopilot** → paste a few notes → get a full week's content plan back.
3. **Mark outcomes** — click 👍 on one suggestion, 👎 on another.
4. **Re-plan** → the new plan shows a "Learned from your feedback" banner reflecting those exact marks.
5. **Replies tab** → paste several fan comments at once → get every reply drafted in a single pass.
6. **Memory bank tab** → see the live Hindsight numbers behind everything the agent just did.

## Environment Variables

| Variable | Description |
|---|---|
| `GROQ_API_KEY` | Your Groq API key, used for all plan/reply generation |
| `HINDSIGHT_API_KEY` | Your Hindsight API key, used for memory retain/recall |

## License

MIT
