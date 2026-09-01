#!/usr/bin/env python3
"""
Generates stats.svg, streak.svg, langs.svg, year.svg from the GitHub GraphQL API.
Stdlib only — nothing to break in CI.

Env vars required:
  GITHUB_TOKEN  - provided automatically by Actions (secrets.GITHUB_TOKEN)
  GH_LOGIN      - GitHub username, provided automatically as github.repository_owner
"""
import json
import os
import urllib.request
import datetime as dt

TOKEN = os.environ["GITHUB_TOKEN"]
LOGIN = os.environ["GH_LOGIN"]
OUT_DIR = "assets"
os.makedirs(OUT_DIR, exist_ok=True)

# Same 13-character ramp used by the portrait, so everything shares one visual language.
RAMP = " .`:-=+*cs#%@"

# ---- pin the window to whole UTC days: two runs minutes apart must agree ----
today = dt.datetime.now(dt.timezone.utc).date()
FROM = dt.datetime.combine(today - dt.timedelta(days=364), dt.time(0, 0, 0), dt.timezone.utc)
TO = dt.datetime.combine(today, dt.time(23, 59, 59), dt.timezone.utc)


def gql(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": LOGIN,
        },
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks {
          contributionDays { date contributionCount }
        }
      }
    }
    repositories(first: 100, privacy: PUBLIC, ownerAffiliations: OWNER,
                  isFork: false) {
      nodes {
        languages(first: 5, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""


def fetch():
    data = gql(QUERY, {
        "login": LOGIN,
        "from": FROM.isoformat(),
        "to": TO.isoformat(),
    })
    return data["user"]


def svg_header(w, h):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="{w}" height="{h}" font-family="monospace">')


def text(x, y, s, size=13, fill="var(--fgColor-default, #ccc)", weight="normal"):
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" '
            f'font-weight="{weight}">{s}</text>')


# ---------------------------------------------------------------- stats.svg
def build_stats(days):
    total = sum(d["contributionCount"] for d in days)
    # last 12 whole weeks, aggregated — a bar per week, not a line through sparse days
    weeks = [days[i:i + 7] for i in range(0, len(days), 7)][-12:]
    weekly = [sum(d["contributionCount"] for d in wk) for wk in weeks]
    maxw = max(weekly) or 1

    w, h = 420, 160
    parts = [svg_header(w, h)]
    parts.append(text(16, 34, f"{total}", size=32, weight="bold"))
    parts.append(text(16, 54, "contributions in the last year", size=12,
                       fill="var(--fgColor-muted, #888)"))

    bar_w = (w - 32) / len(weekly)
    base_y = 140
    for i, v in enumerate(weekly):
        bh = 0 if maxw == 0 else round((v / maxw) * 60)
        x = 16 + i * bar_w
        parts.append(
            f'<rect x="{x:.1f}" y="{base_y - bh}" width="{bar_w * 0.7:.1f}" '
            f'height="{bh}" fill="var(--fgColor-accent, #58a6ff)" rx="1"/>'
        )
    parts.append(f'<line x1="16" y1="{base_y}" x2="{w-16}" y2="{base_y}" '
                  f'stroke="var(--borderColor-default, #444)" stroke-width="1"/>')
    parts.append(text(16, 156, "weekly totals, last 12 weeks", size=10,
                       fill="var(--fgColor-muted, #888)"))
    parts.append("</svg>")
    return "\n".join(parts)


# --------------------------------------------------------------- streak.svg
def build_streak(days):
    # current streak: consecutive non-zero days ending today (or yesterday)
    cur = 0
    for d in reversed(days):
        if d["contributionCount"] > 0:
            cur += 1
        else:
            break

    longest = 0
    run = 0
    longest_range = (None, None)
    run_start = None
    for d in days:
        if d["contributionCount"] > 0:
            if run == 0:
                run_start = d["date"]
            run += 1
            if run > longest:
                longest = run
                longest_range = (run_start, d["date"])
        else:
            run = 0

    cur_start = None
    if cur > 0:
        cur_start = days[len(days) - cur]["date"]
    cur_end = days[-1]["date"] if cur > 0 else "-"

    w, h = 420, 130
    parts = [svg_header(w, h)]
    parts.append(text(16, 34, f"{cur}", size=28, weight="bold"))
    parts.append(text(70, 30, "current streak", size=12,
                       fill="var(--fgColor-muted, #888)"))
    parts.append(text(70, 44, f"{cur_start or '-'} \u2192 {cur_end}", size=10,
                       fill="var(--fgColor-muted, #888)"))

    parts.append(text(16, 84, f"{longest}", size=28, weight="bold"))
    parts.append(text(70, 80, "longest streak", size=12,
                       fill="var(--fgColor-muted, #888)"))
    parts.append(text(70, 94, f"{longest_range[0] or '-'} \u2192 {longest_range[1] or '-'}",
                       size=10, fill="var(--fgColor-muted, #888)"))
    parts.append("</svg>")
    return "\n".join(parts)


# ---------------------------------------------------------------- langs.svg
def build_langs(repos):
    totals = {}
    for r in repos:
        for e in r["languages"]["edges"]:
            name = e["node"]["name"]
            totals[name] = totals.get(name, 0) + e["size"]
    ordered = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:6]
    grand = sum(v for _, v in ordered) or 1

    w = 420
    h = 40 + 26 * len(ordered)
    parts = [svg_header(w, h)]
    parts.append(text(16, 24, "top languages, by bytes", size=12,
                       fill="var(--fgColor-muted, #888)"))
    y = 44
    bar_max = w - 140
    for name, size in ordered:
        pct = size / grand
        bw = round(bar_max * pct)
        parts.append(text(16, y + 12, name, size=12))
        parts.append(
            f'<rect x="130" y="{y+2}" width="{bw}" height="10" rx="2" '
            f'fill="var(--fgColor-accent, #58a6ff)"/>'
        )
        parts.append(text(130 + bar_max + 8, y + 12, f"{pct*100:.0f}%", size=11,
                           fill="var(--fgColor-muted, #888)"))
        y += 26
    parts.append("</svg>")
    return "\n".join(parts)


# ----------------------------------------------------------------- year.svg
def ramp_char(count, maxc):
    if maxc == 0 or count == 0:
        return RAMP[0]
    idx = min(len(RAMP) - 1, 1 + round((count / maxc) * (len(RAMP) - 2)))
    return RAMP[idx]


def build_year(days):
    maxc = max((d["contributionCount"] for d in days), default=0)
    weeks = [days[i:i + 7] for i in range(0, len(days), 7)]

    cell = 11
    w = 24 + len(weeks) * cell
    h = 24 + 7 * cell
    parts = [svg_header(w, h)]
    parts.append(
        f'<style>text{{font-family:monospace}}</style>'
    ) if False else None  # style blocks don't survive on the profile page; kept out
    for wi, wk in enumerate(weeks):
        for di, d in enumerate(wk):
            ch = ramp_char(d["contributionCount"], maxc)
            x = 16 + wi * cell
            y = 16 + di * cell
            parts.append(
                f'<text x="{x}" y="{y}" font-size="11" '
                f'fill="var(--fgColor-accent, #58a6ff)">{ch}</text>'
            )
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    user = fetch()
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = [d for wk in weeks for d in wk["contributionDays"]]
    repos = user["repositories"]["nodes"]

    outputs = {
        "stats.svg": build_stats(days),
        "streak.svg": build_streak(days),
        "langs.svg": build_langs(repos),
        "year.svg": build_year(days),
    }
    for name, svg in outputs.items():
        path = os.path.join(OUT_DIR, name)
        with open(path, "w") as f:
            f.write(svg)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
