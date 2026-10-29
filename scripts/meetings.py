"""Builds app/meetings.json for Psalmist on the web: the next few weeks' meeting
song numbers and the videos each meeting plays (as publication references only).
Browsers can't read wol.jw.org themselves, so this runs on GitHub Actions twice a
week. Song titles, video titles and files are loaded from jw.org by the app."""
import datetime
import html
import json
import re
import sys
import urllib.request

WOL = "https://wol.jw.org/en/wol"
UA = {"User-Agent": "Mozilla/5.0 (Psalmist meeting schedule)"}


def get(url: str) -> str:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).replace(" ", " ").strip()


def article(doc: str) -> str:
    m = re.search(r"<article[\s\S]*?</article>", doc)
    return m.group(0) if m else doc


def songs(doc: str) -> list[int]:
    """Song numbers in the order they're sung, from links into the songbook."""
    out = []
    for m in re.finditer(r'<a[^>]*href="/en/wol/pc/[^"]*"[^>]*>([\s\S]*?)</a>', article(doc)):
        n = re.search(r"(?i)\bsong\s+(\d{1,3})\b", text(m.group(1)))
        if n:
            out.append(int(n.group(1)))
    return out


def videos(doc: str) -> list[dict]:
    """Videos the schedule says to play: data-video="webpubvid://?pub=…&issue=…&track=…"."""
    out, seen = [], set()
    for m in re.finditer(r'<a[^>]*data-video="webpubvid://\?([^"]*)"[^>]*>[\s\S]*?</a>([\s\S]{0,400}?)</p>', article(doc)):
        q = dict(p.split("=", 1) for p in html.unescape(m.group(1)).split("&") if "=" in p)
        if not q.get("pub"):
            continue
        em = re.search(r"<em>([\s\S]*?)</em>", m.group(2))
        v = {"pub": q["pub"], "issue": q.get("issue") or None, "track": int(q.get("track") or 0),
             "title": text(em.group(1)).rstrip(". ") if em else ""}
        key = (v["pub"], v["issue"], v["track"])
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out


def heading(doc: str, tag: str) -> str:
    for m in re.finditer(rf"<{tag}[^>]*>([\s\S]*?)</{tag}>", article(doc)):
        t = text(m.group(1))
        if t:
            return t
    return ""


def meeting(doc: str, title: str, subtitle: str, labels_for: dict[int, list[str]]) -> dict | None:
    s = songs(doc)
    if not s:
        return None
    labels = labels_for.get(len(s), ["Song"] * len(s))
    return {"title": title, "subtitle": subtitle, "songs": [{"label": l, "number": n} for l, n in zip(labels, s)], "videos": videos(doc)}


def week(monday: datetime.date) -> dict:
    year, wk, _ = monday.isocalendar()
    page = get(f"{WOL}/meetings/r1/lp-e/{year}/{wk}")
    title = re.search(r"<title>([\s\S]*?)</title>", page)
    dates = text(title.group(1)).split(" — ")[0].strip() if title else ""
    # The page links the workbook week first, then the Watchtower Study article.
    ids = list(dict.fromkeys(re.findall(r'href="/en/wol/d/r1/lp-e/(\d{6,})"', page)))
    docs = [get(f"{WOL}/d/r1/lp-e/{i}") for i in ids[:2]]
    return {
        "monday": monday.isoformat(),
        "dates": dates,
        "midweek": meeting(docs[0], "Midweek Meeting", heading(docs[0], "h2").title(), {3: ["Opening song", "Middle song", "Closing song"]}) if docs else None,
        "weekend": meeting(docs[1], "Weekend Meeting", heading(docs[1], "h1"), {2: ["Watchtower Study", "Closing song"]}) if len(docs) > 1 else None,
    }


def main(out_path: str) -> None:
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    weeks = []
    for i in range(-1, 4):
        try:
            weeks.append(week(monday + datetime.timedelta(weeks=i)))
        except Exception as e:  # one bad week shouldn't stop the rest
            print(f"week {i}: {e}", file=sys.stderr)
    if not any(w["midweek"] or w["weekend"] for w in weeks):
        sys.exit("No schedule found; keeping the old file")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(), "weeks": weeks}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "app/meetings.json")
