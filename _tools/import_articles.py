"""One-time import: Resource App/Asset Text/*.md  ->  Article Library/articles/<topic>/<slug>.md

What it does
- Groups the 36 archive themes into 8 topics and files each article under the topic
  of its first theme (flyers and poster copy go to their own topic).
- Gives every file a clean, URL-safe name taken from its title.
- Tidies titles ("Postcards from Corinth • Chapter Excerpt" -> the real title, "power power" -> "Power").
- Merges duplicate copies of the same text (same title, near-identical body) into one file
  and records where the other copies lived in `also_filed`.
- Rewrites the header as simple front matter and drops the generated title/summary lines
  from the body (the site renders those from the front matter).

Run:  python3 _tools/import_articles.py [path/to/Asset Text]
It wipes and rewrites articles/. After that, articles/ is the source of truth: edit it directly.
"""
import difflib, json, os, re, shutil, sys, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "..", "Resource App", "Asset Text")
OUT = os.path.join(ROOT, "articles")

# topic slug -> (title, themes that belong to it)
TOPICS = {
    "evangelism": ("Evangelism & Outreach", [
        "Personal evangelism & gospel conversations", "Evangelism tools", "Outreach events & campaigns", "Apologetics"]),
    "discipleship": ("Discipleship & Spiritual Growth", [
        "Discipleship & follow-up", "Spiritual disciplines", "Prayer", "Holy Spirit & the Spirit-filled life",
        "Spiritual multiplication", "Gospel-centred living"]),
    "bible-and-theology": ("Bible & Theology", [
        "Bible study & interpretation", "Knowing God & doctrine", "Assurance, grace & forgiveness", "Revival & awakening"]),
    "small-groups": ("Small Groups & Community", [
        "Small groups", "Weekly meetings", "Community & fellowship", "Conferences & retreats"]),
    "leadership": ("Leadership & Movement Building", [
        "Launching a new ministry", "Vision & strategic planning", "Team leadership & coaching", "Movement building & growth",
        "Leader character & development", "Evaluation & results", "Fundraising & support raising"]),
    "life-and-character": ("Life, Identity & Character", [
        "Identity & emotional health", "Sexual purity", "Dating, marriage & singleness", "Trials & suffering",
        "Conflict, confrontation & accountability", "Calling, vocation & God's will", "Life after college"]),
    "mission-and-justice": ("Mission, Justice & Culture", [
        "Missions & the Great Commission", "Justice & compassion", "Ethnic & contextualized ministry",
        "Summer projects, internships & staff"]),
    "flyers-and-promo": ("Flyers, Posters & Promo", []),
}
THEME_TOPIC = {th: slug for slug, (_, ths) in TOPICS.items() for th in ths}
TYPES = {"Article / guide": "Article", "Flyer / poster": "Flyer", "Editable text": "Handout", "Slides": "Slides"}

GENERIC = {"instructions", "some time", "to the", "postcards from corinth", "flesh by rick james", "article excerpt",
           "chapter excerpt", "overview", "section text"}
SMALL = set("a an and as at but by for from in into nor of on or per the to vs via with".split())


def parse(path):
    text = open(path, encoding="utf-8").read()
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    meta = {}
    for line in m.group(1).split("\n"):
        k, _, v = line.partition(": ")
        try: meta[k] = json.loads(v)
        except ValueError: meta[k] = v
    return meta, strip_header(text[m.end():])


def strip_header(body):
    """Drop the generated '# Title', '*Source:*', '> **Summary:**', '**Themes:**/**For:**' blocks at the top."""
    blocks = re.split(r"\n\s*\n", body.strip())
    while blocks:
        b = blocks[0].strip()
        if (b.startswith("# ") and "\n" not in b) or b.startswith("*Source:") or b.startswith("> **Summary:**") \
                or b.startswith("**Themes:**") or b.startswith("**For:**"):
            blocks.pop(0)
        else:
            break
    return "\n\n".join(blocks).strip() + "\n"


def smart_title(s):
    if s != s.lower() and s != s.upper(): return s
    words = s.lower().split()
    return " ".join(w if (i and w in SMALL) else w[:1].upper() + w[1:] for i, w in enumerate(words))


def name_from_file(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = re.sub(r"\b(copy|copy \d+)\b", "", stem, flags=re.I)
    stem = re.sub(r"^\d+\.\s*", "", stem).replace("_", " ")
    stem = re.sub(r"\s+", " ", stem).strip(" -")
    return smart_title(stem) if stem else "Untitled"


def clean_title(meta, path):
    t = unicodedata.normalize("NFC", meta["title"]).strip()
    t = re.split(r"\s+•\s+", t)[0]
    series = meta.get("series", "")
    for cut in filter(None, [series, "white papers critical concept series", "postcards from corinth", "intransition groupzine"]):
        i = t.lower().find(cut.lower())
        if i > 3: t = t[:i]
    t = re.sub(r"^—\s*\w+ \w+\s+", "", t)                    # leading attribution "—David Dark ..."
    words = t.split()
    if len(words) >= 2 and len(words) % 2 == 0 and words[: len(words) // 2] == words[len(words) // 2:]:
        t = " ".join(words[: len(words) // 2])                # "power power" -> "power"
    t = re.sub(r"\b(\w+)- (\w+)", r"\1\2", t)                 # "Re- Sources", "peace- makers"
    t = re.sub(r"(?<=\w)-k (?=ept)", "-k", t).replace("best-k ept", "best-kept")
    t = t.strip(" .,:;-—“”\"")
    low = t.lower()
    if not t or low in GENERIC or low == series.lower() or len(t) < 4:
        t = name_from_file(path)
        folder = os.path.basename(os.path.dirname(path))
        if t.lower() in GENERIC or t.lower().startswith("week") or t.lower().startswith("overview"):
            t = f"{name_from_file(folder)}: {t}"
    return smart_title(t)


def slugify(s):
    s = re.sub(r"[—–/]", " ", s.replace("’", "").replace("'", ""))
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    if len(s) > 64: s = s[:64].rsplit("-", 1)[0]
    return s or "untitled"


def topic_for(meta):
    if meta["type"] == "Flyer / poster" or "Posters and Publicity" in meta["source"]:
        return "flyers-and-promo"
    for th in meta.get("themes", []):
        if th in THEME_TOPIC: return THEME_TOPIC[th]
    return "leadership"


def same_text(a, b):
    wa, wb = a.split(), b.split()
    if not wa or not wb or abs(len(wa) - len(wb)) > 0.08 * max(len(wa), len(wb)): return False
    # compare as bags of words: copies extracted from different PDFs can differ in paragraph order
    return difflib.SequenceMatcher(None, wa, wb, autojunk=False).quick_ratio() > 0.93


def preference(rec):
    """Lower is better when choosing which duplicate to keep."""
    p = rec["path"]
    return (bool(re.search(r"\bcopy\b", p, re.I)), "_" in os.path.basename(p), "Starter_Kit-1" in p, len(p))


def fm_value(v):
    return json.dumps(v, ensure_ascii=False)


def main():
    recs = []
    for r, _, fs in os.walk(SRC):
        for f in sorted(fs):
            if not f.endswith(".md") or f == "README.md": continue
            path = os.path.join(r, f)
            meta, body = parse(path)
            rel = os.path.relpath(path, SRC)
            recs.append({"path": rel, "meta": meta, "body": body, "title": clean_title(meta, rel)})

    # merge duplicates: same cleaned title (or same original title) and near-identical text
    recs.sort(key=preference)
    kept = []
    for rec in recs:
        dup = None
        for k in kept:
            if (k["title"].lower() == rec["title"].lower() or k["meta"]["title"].lower() == rec["meta"]["title"].lower()) \
                    and same_text(k["body"], rec["body"]):
                dup = k; break
        if dup:
            dup.setdefault("also", []).append(rec["meta"]["source"])
            for th in rec["meta"].get("themes", []):
                if th not in dup["meta"]["themes"]: dup["meta"]["themes"].append(th)
        else:
            kept.append(rec)

    if os.path.isdir(OUT): shutil.rmtree(OUT)
    used = set()
    counts = {}
    for rec in sorted(kept, key=lambda x: x["path"]):
        m = rec["meta"]
        topic = topic_for(m)
        base = slug = slugify(rec["title"])
        n = 2
        while slug in used:
            slug = f"{base}-{n}"; n += 1
        used.add(slug)
        topics = []
        for th in m.get("themes", []):
            t = THEME_TOPIC.get(th)
            if t and t not in topics: topics.append(t)
        if topic not in topics: topics.insert(0, topic)
        else: topics.insert(0, topics.pop(topics.index(topic)))
        fm = [("title", rec["title"]), ("topic", topic), ("also_topics", topics[1:]), ("type", TYPES.get(m["type"], m["type"])),
              ("themes", m.get("themes", [])), ("audience", m.get("audience", []))]
        if m.get("authors"): fm.append(("authors", m["authors"]))
        if m.get("series"): fm.append(("series", m["series"]))
        fm += [("words", m.get("words", len(rec["body"].split()))), ("summary", m.get("summary", ""))]
        if m.get("note"): fm.append(("note", m["note"]))
        fm.append(("source", m["source"].replace("Assets/CruPress Green Archive/", "")))
        if rec.get("also"): fm.append(("also_filed", [s.replace("Assets/CruPress Green Archive/", "") for s in rec["also"]]))
        head = "---\n" + "\n".join(f"{k}: {fm_value(v)}" for k, v in fm) + "\n---\n\n"
        os.makedirs(os.path.join(OUT, topic), exist_ok=True)
        with open(os.path.join(OUT, topic, slug + ".md"), "w", encoding="utf-8") as fh:
            fh.write(head + rec["body"])
        counts[topic] = counts.get(topic, 0) + 1
    print(f"{len(recs)} source files -> {len(kept)} articles ({len(recs) - len(kept)} duplicates merged)")
    for t, (name, _) in TOPICS.items():
        print(f"  {counts.get(t, 0):4}  {t:22} {name}")


if __name__ == "__main__":
    main()
