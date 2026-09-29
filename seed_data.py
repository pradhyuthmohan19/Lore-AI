import argparse
import bisect
import collections
import csv
import re
import statistics
import time


def load_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def spread(items, k):
    if k <= 0 or not items:
        return []
    if k >= len(items):
        return list(items)
    step = len(items) / k
    return [items[int(i * step)] for i in range(k)]


def pick_posts(rows, n):
    rows = sorted(rows, key=lambda r: (r["date_ist"], r["time_ist"]))
    with_themes = [r for r in rows if r["comment_themes"] != "none"]
    half = n // 2
    chosen = spread(with_themes, half) + spread(rows, n - half)
    seen, unique = set(), []
    for r in chosen:
        if r["content_id"] not in seen:
            seen.add(r["content_id"])
            unique.append(r)
    return sorted(unique, key=lambda r: (r["date_ist"], r["time_ist"]))


# ---------- per-post memories, with exact performance ranks ----------

def build_rank_tables(rows):
    return {
        "n": len(rows),
        "eng": sorted(float(r["engagement_rate_pct"]) for r in rows),
        "views": sorted(int(r["views"]) for r in rows),
    }


def top_pct(sorted_vals, value):
    n = len(sorted_vals)
    at_or_above = n - bisect.bisect_left(sorted_vals, value)
    return max(1, round(100 * at_or_above / n))


def themes_text(raw):
    if raw == "none":
        return "no recurring themes in the comments"
    parts = []
    for item in raw.split("|"):
        name, _, count = item.partition(":")
        parts.append(f"{count} comments about '{name.replace('_', ' ')}'")
    return "; ".join(parts)


def row_to_text(r, ranks=None):
    text = (
        f"Instagram {r['content_type']} posted on {r['date_ist']} ({r['weekday']}) at {r['time_ist']} IST. "
        f"Caption/hook: \"{r['caption']}\". Hashtags: {r['hashtags']}. "
        f"The account had {r['followers_at_post']} followers. "
        f"Reach {r['reach']} ({r['reach_pct_of_followers']}% of followers), {r['views']} views, "
        f"{r['likes']} likes, {r['comments']} comments, {r['saves']} saves, {r['shares']} shares. "
        f"{r['profile_visits']} profile visits and {r['follows']} new follows came from this post. "
        f"Engagement rate {r['engagement_rate_pct']}%, follow rate {r['follow_rate_pct']}%. "
        f"Comment themes: {themes_text(r['comment_themes'])}. "
        f"Top comment: \"{r['top_comment']}\"."
    )
    if ranks:
        e = top_pct(ranks["eng"], float(r["engagement_rate_pct"]))
        v = top_pct(ranks["views"], int(r["views"]))
        text += (
            f" Performance rank: engagement rate in the top {e}% and views in the top {v}% "
            f"of all {ranks['n']} of this account's posts."
        )
    return text


# ---------- rollups: exact numbers computed in code, stored as SHORT single-fact sentences ----------
# Long numeric paragraphs get condensed when a memory system extracts facts from them,
# so each fact below is one self-contained sentence, retained as its own item.

def _n(x):
    return f"{int(round(x)):,}"


def format_facts(rows):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["content_type"]].append(r)
    facts = []
    ordered = sorted(by.items(), key=lambda kv: -statistics.mean(int(r["views"]) for r in kv[1]))
    for t, rs in ordered:
        facts.append(
            f"Across all {len(rows)} posts, the format '{t}' ({len(rs)} posts) averaged "
            f"{_n(statistics.mean(int(r['reach']) for r in rs))} reach, "
            f"{_n(statistics.mean(int(r['views']) for r in rs))} views and "
            f"{statistics.mean(float(r['engagement_rate_pct']) for r in rs):.2f}% engagement rate."
        )
    return [("format performance", facts)]


def theme_facts(rows):
    months = sorted({r["date_ist"][:7] for r in rows})
    per = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    for r in rows:
        if r["comment_themes"] == "none":
            continue
        month = r["date_ist"][:7]
        for item in r["comment_themes"].split("|"):
            name, _, k = item.partition(":")
            per[name][month][0] += 1
            per[name][month][1] += int(k)

    groups = []
    for name, by_month in sorted(per.items(), key=lambda kv: -sum(v[1] for v in kv[1].values())):
        label = name.replace("_", " ")
        total_comments = sum(v[1] for v in by_month.values())
        total_posts = sum(v[0] for v in by_month.values())
        facts = [
            f"Audience comment theme '{label}' totals {_n(total_comments)} comments across {_n(total_posts)} posts "
            f"between {months[0]} and {months[-1]}."
        ]
        for m in months:
            if m in by_month:
                posts, comments = by_month[m]
                facts.append(f"In {m}, the audience comment theme '{label}' had {_n(comments)} comments across {posts} posts.")
        groups.append((f"theme {label}", facts))
    return groups


def _plain(caption):
    return re.sub(r"[^\w\s'/-]", "", caption, flags=re.UNICODE).strip()


def series_facts(rows):
    end = max(r["date_ist"] for r in rows)
    series = collections.defaultdict(list)
    for r in rows:
        m = re.match(r"^(.*?)\s*\bpart\s*(\d+)\b", _plain(r["caption"]), re.I)
        if m and m.group(1).strip():
            series[m.group(1).strip().lower()].append((int(m.group(2)), r))

    facts = []
    for name, items in series.items():
        if len({p for p, _ in items}) < 3:
            continue  # ignore things like "poll: part 2 yes or no"
        parts = [p for p, _ in items]
        dates = sorted(r["date_ist"] for _, r in items)
        views = sum(int(r["views"]) for _, r in items)
        eng = statistics.mean(float(r["engagement_rate_pct"]) for _, r in items)
        gap = (_date(end) - _date(dates[-1])).days
        last_part = max(parts)
        facts.append(f"The series '{name}' ran parts {min(parts)} to {last_part} ({len(items)} posts) from {dates[0]} to {dates[-1]}.")
        facts.append(f"The last part of the series '{name}' was part {last_part}, posted on {dates[-1]}.")
        if gap >= 30:
            facts.append(f"As of {end}, the last date in the data, the series '{name}' has had no new part for {gap} days.")
        else:
            facts.append(f"The series '{name}' is still active; the last part was part {last_part} on {dates[-1]}.")
        facts.append(f"The series '{name}' earned {_n(views)} total views with {eng:.2f}% average engagement rate.")
    return [("series", facts)] if facts else []


def _date(s):
    import datetime
    return datetime.date.fromisoformat(s)


def month_facts(rows):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["date_ist"][:7]].append(r)
    groups = []
    for month in sorted(by):
        rs = by[month]
        types = collections.Counter(r["content_type"] for r in rs)
        mix = ", ".join(f"{c} {t}" for t, c in types.most_common())
        follows = sum(int(r["follows"]) for r in rs)
        facts = [
            f"In {month} the account published {len(rs)} posts ({mix}) and gained {_n(follows)} new followers from posts."
        ]
        top = sorted(rs, key=lambda r: int(r["views"]), reverse=True)[:3]
        for i, r in enumerate(top, 1):
            facts.append(
                f"In {month}, post number {i} by views was a {r['content_type']} captioned \"{_plain(r['caption'])[:60]}\" "
                f"posted on {r['date_ist']}, with {_n(int(r['views']))} views and {r['engagement_rate_pct']}% engagement rate."
            )
        groups.append((f"month {month}", facts))
    return groups


def fact_groups(rows):
    return format_facts(rows) + theme_facts(rows) + series_facts(rows) + month_facts(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--n", type=int, default=24, help="number of individual posts to retain")
    parser.add_argument("--bank", default=None, help="bank id (defaults to HINDSIGHT_BANK_ID)")
    parser.add_argument("--dry", action="store_true", help="print only, do not retain")
    parser.add_argument("--no-digests", action="store_true", help="skip the rollup facts")
    args = parser.parse_args()

    all_rows = load_rows(args.csv_path)
    ranks = build_rank_tables(all_rows)
    posts = pick_posts(all_rows, args.n)
    post_texts = [row_to_text(r, ranks) for r in posts]
    groups = [] if args.no_digests else fact_groups(all_rows)
    fact_count = sum(len(f) for _, f in groups)

    print(f"{len(posts)} posts + {fact_count} rollup facts in {len(groups)} groups "
          f"(posts span {posts[0]['date_ist']} to {posts[-1]['date_ist']})\n")

    if args.dry:
        for i, text in enumerate(post_texts, 1):
            print(f"--- post {i} ---\n{text}\n")
        for label, facts in groups:
            print(f"=== {label} ===")
            for f in facts:
                print(f"  * {f}")
            print()
    else:
        from memory import retain_post, retain_many
        total = len(post_texts) + len(groups)
        for i, text in enumerate(post_texts, 1):
            print(f"({i}/{total})", end=" ")
            retain_post(text, bank_id=args.bank)
            time.sleep(1)
        for j, (label, facts) in enumerate(groups, len(post_texts) + 1):
            print(f"({j}/{total}) [{label}]", end=" ")
            retain_many(facts, bank_id=args.bank)
            time.sleep(1)
        print("\nDone seeding.")