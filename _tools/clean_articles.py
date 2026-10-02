"""Tidy the article text in articles/**/*.md (safe to run more than once).

The articles came from PDFs, and the conversion left debris in the text. This removes or repairs:
- page furniture: copyright footers, running headers ("JESUS.DOC • ARTICLE FOUR • 51"), page numbers
  glued to them, and stray letters from decorative word art ("e", "h ...")
- list debris: empty bullets ("- •"), bullets doubled up ("- • Item"), blank fill-in numbers ("2." alone)
- run-on bullets inside a paragraph ("…to focus on: • Evangelism • Prayer") → a real bulleted list
- fake headings: whole sentences marked as headings become ordinary paragraphs, short labels
  ("Discuss:") become bold lines, and garbled ones ("de er r") are removed
- word damage: odd capitals ("fAith"), words split by a hyphen and space ("over- confidence")

Run:  python3 _tools/clean_articles.py        (then python3 _tools/build.py)
      python3 _tools/clean_articles.py --dry  (report what would change, write nothing)
"""
import os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import ART, TOPICS, is_word, tidy_heading, good_heading  # noqa: E402

DRY = "--dry" in sys.argv
stats = {}


def count(k, n=1):
    stats[k] = stats.get(k, 0) + n


# ---------- page furniture ----------
FOOTER = re.compile(
    r"(?:\b\d{2,3}\s+)?(?:(?:Small Groups|Articles|Devotionals)\s+)?"
    r"©\s?(?:\d{4}[,–-]?\s?)+(?:by\s)?(?:Cru ?Press|Campus Crusade for Christ)[^.\n]{0,60}?\.(?:\s*(?:www\.)?Cru ?Press\.com)?"
    r"(?:\s+(?:Small Groups|Articles|Devotionals))?(?:\s+\d{2,3}\b)?", re.I)
RUNNING_HEAD = re.compile(
    r"(?:\b\d{1,3}\s+•\s+)?\b[A-Z][A-Z0-9 .’'&:-]{2,40}\s+•\s+ARTICLE\s+[A-Z]+(?:\s+•\s+[A-Z][A-Z0-9 .’'&:-]{2,40})?(?:\s+•\s+\d{1,3}\b)?")
WORD_ART = re.compile(r"^(?:[a-z]|h \.\.\.|\.\.\.)$")


def strip_furniture(text):
    n0 = len(text)
    text, k = FOOTER.subn(" ", text); count("copyright footers removed", k)
    text, k = RUNNING_HEAD.subn(" ", text); count("running page headers removed", k)
    return text


# ---------- words ----------
PREFIXES = {"non", "self", "well", "co", "re", "pre", "anti", "multi", "cross", "long", "short", "high", "low", "full", "part"}


def fix_words(s):
    def odd_caps(m):
        count("odd capitals fixed"); w = m.group(0); return w[0].upper() + w[1:].lower()
    s = re.sub(r"\b[a-z][A-Z][a-z]{2,}\b", odd_caps, s)                                # "fAith" → "Faith"

    def split_word(m):
        a, b = m.group(1), m.group(2)
        if is_word(a + b) and not (a.lower() in PREFIXES and b[:1].isupper()):
            count("split words rejoined"); return a + b
        if a.lower() in PREFIXES or b[:1].isupper():
            count("split words rejoined"); return f"{a}-{b}"
        return m.group(0)
    s = re.sub(r"\b([A-Za-z]{2,})- ([A-Za-z]{2,})\b", split_word, s)                  # "over- confidence"
    s = re.sub(r"(?<=[A-Za-z])í(?=(s|t|ll|re|ve|d|m)\b)", "’", s)                     # mojibake apostrophe

    def ligature(m):                                                                   # "fi rst fi ve" → "first five"
        w = m.group(1) + m.group(2) + m.group(3)
        if is_word(w): count("ligature splits rejoined"); return w
        return m.group(0)
    s = re.sub(r"\b([A-Za-z]*)(ffi|ffl|fi|fl|ff) ([a-z]+)\b", ligature, s)
    s = re.sub(r"\s*/{3,}\s*", " ", s)                                                 # "Culture ////////"
    s = s.replace("\ufffd", "")                                                          # "�" (unreadable glyph)
    if len(re.findall(r"[A-Za-z]![A-Za-z]", s)) >= 3:                                       # "History!of!Project!Orange!"
        s = re.sub(r"(?<=[A-Za-z,.:])!(?=[A-Za-z(])", " ", s); s = re.sub(r"(?<=[A-Za-z.])!(?=\s|$)", "", s)
        s = s.replace("(orange(", "Orange "); count("! used as spaces fixed")
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s


# ---------- blocks ----------
UL = re.compile(r"^\s*[-*]\s+")
OL = re.compile(r"^\s*\d{1,3}[.)]\s+")


def clean_list_lines(lines):
    out = []
    for l in lines:
        s = l.rstrip()
        if re.match(r"^\s*[-*•]\s*(•\s*)*$", s):                                       # "- •", "- ", "•"
            count("empty bullets removed"); continue
        if re.match(r"^\s*\d{1,3}[.)]?\s*$", s):                                         # "2." fill-in blank
            count("blank numbers removed"); continue
        s2 = re.sub(r"^(\s*)[-*]\s+(?:•\s+)+", r"\1- ", s)                               # "- • Item"
        s2 = re.sub(r"^(\s*)•\s+", r"\1- ", s2)                                          # "• Item" → "- Item"
        if s2 != s: count("doubled bullets fixed")
        m = re.match(r"^(\s*)- (.*)$", s2)
        if m and " • " in m.group(2):                                                    # "- A • B • C" → three items
            parts = [p.strip() for p in m.group(2).split(" • ") if p.strip()]
            if len(parts) > 1 and all(len(p) < 300 for p in parts):
                count("bullets on one line split into items")
                out.extend(f"{m.group(1)}- {p}" for p in parts); continue
        out.append(s2)
    return out


def reorder_numbered(lines):
    """A block made only of numbered items (with wrapped lines) where each number appears once and together
    they form a run like 1–7, but out of order — a two-column list read across. Put them back in order."""
    items = []
    for l in lines:
        m = re.match(r"^\s*(\d{1,3})[.)]\s+", l)
        if m: items.append([int(m.group(1)), [l]])
        elif items and not UL.match(l): items[-1][1].append(l)
        else: return lines
    nums = [n for n, _ in items]
    if len(nums) >= 3 and len(set(nums)) == len(nums) and sorted(nums) == list(range(min(nums), min(nums) + len(nums))) \
            and nums != sorted(nums):
        count("numbered lists put back in order")
        return [l for _, ls in sorted(items) for l in ls]
    return lines


def split_inline_bullets(para):
    """'Lead-in: • First • Second • Third' → lead-in paragraph + bullet list.
    Clusters of empty bullets ('• • • •', where the item text was separated from its bullet) are removed."""
    if "•" not in para: return para
    if re.search(r"•\s*•", para):
        para = re.sub(r"(?:\s*•){2,}\s*", " ", para); count("empty bullet runs removed")
        if para.count("•") == 0: return para.strip()
    parts = [p.strip() for p in re.split(r"\s+•\s+", " " + para + " ")]
    lead, items = parts[0], [p for p in parts[1:] if p]
    if len(items) < 2 or any(len(i) > 400 for i in items):
        return para.replace(" • ", " · ")
    count("run-on bullets made into lists")
    return (lead + "\n\n" if lead else "") + "\n".join("- " + i for i in items)


SHORT_OK = {"a", "i", "an", "as", "at", "be", "by", "do", "go", "he", "if", "in", "is", "it", "me", "my", "no", "of", "on",
            "or", "so", "to", "up", "us", "we", "vs", "tv", "ii", "iv", "vi", "st", "dr", "mr", "jr", "ok", "am", "pm"}
NOISE = re.compile(r"[*@%|=<>~_\\]|/{2,}|\[ \]")


def heading_ok(t):
    """Short, made of real words, starts like a title: fine as a heading even if too plain for the page contents box."""
    words = re.findall(r"[A-Za-z’']+", t)
    return (t and len(t) <= 64 and len(t.split()) <= 10 and re.match(r"[A-Z0-9“\"‘(#]", t) and words
            and sum(is_word(w) for w in words) >= 0.8 * len(words) and not NOISE.search(t)
            and sum(1 for w in words if len(w) == 1 and w.lower() not in ("a", "i")) < 2              # "L e s"
            and not re.search(r"[,;]$|\b(the|a|an|and|of|to|in|with|for|that|when|as|by|from|or|but)$", t, re.I))


def fix_heading(block, authors_first, prior_words, author_names=()):
    m = re.match(r"^(#{2,6})\s+(.*)$", block)
    level, raw = m.group(1), m.group(2).strip()
    raw = re.sub(r"^[•·*-]\s*", "", raw)
    raw = FOOTER.sub(" ", RUNNING_HEAD.sub(" ", raw)).strip()
    if "››" in raw:                                            # "GREEK STUDENTS›› 138›› The Dating Game" (page tabs)
        tail = re.sub(r"^\d{1,3}\s*", "", raw.split("››")[-1].strip())
        raw = tail or re.sub(r"\s*››\s*$", "", raw).strip()
        count("page-tab prefixes removed")
    if not raw: count("empty headings removed"); return ""
    if raw.lower() in author_names: count("author-name headings removed (shown in byline)"); return ""
    t = tidy_heading(raw, authors_first)
    starts_lower = re.match(r"[a-z]", raw) and len(raw.split()) > 3                  # "could. Gospel appointments are…"
    if not starts_lower and (good_heading(t, prior_words, raw) or heading_ok(t)):
        prior_words.update(w.lower() for w in re.findall(r"[A-Za-z’']+", t))
        if t != raw: count("headings tidied")
        return f"{level} {t}"
    words = re.findall(r"[A-Za-z’']+", raw)
    real = sum(is_word(w) for w in words)
    short_bits = sum(1 for w in words if len(w) <= 2 and w.lower() not in SHORT_OK)
    if (not words or re.fullmatch(r"(?:order )?online at \S+\.(?:com|org)", raw, re.I)
            or (NOISE.search(raw) and real < 0.8 * len(words)) or short_bits >= 3
            or (len(words) >= 3 and real < 0.3 * len(words))):
        count("garbled headings and store ads removed"); return ""
    if re.fullmatch(r"(?:[A-Z][a-z]+|[A-Z]\.)(?:\s+(?:[A-Z][a-z’'-]+|[A-Z]\.)){1,3}", raw) and not heading_ok(raw):
        count("name headings made bylines"); return f"*{raw}*"                      # "Tom Hudzina"
    if len(words) == 1 and raw[:1].isupper() and len(raw) <= 30:
        prior_words.add(raw.lower()); count("headings tidied"); return f"{level} {t}"   # "Website", "Planning"
    if len(raw.split()) <= 4 and raw.endswith(":"):
        count("label headings made bold"); return f"**{raw}**"
    count("sentence headings made paragraphs"); return raw


TITLE_SMALL = set("a an and as at but by for from in into nor of on or per the to vs via with is are".split())
LABELS = {"apply", "launch", "explore", "week", "discuss", "commentary", "notes", "read", "big idea", "lesson plan",
          "action point", "scenarios", "objective", "objectives", "always sometimes never"}


def promote_titles(blocks, title, authors_first, prior_words):
    """A short Title-Case line standing alone before a real paragraph is a section title the PDF conversion
    missed: make it a heading. "File: Prayer, Care, and Share.pdf" (handout bundles) becomes "Prayer, Care, and Share"."""
    out = []
    for i, b in enumerate(blocks):
        p = b.strip()
        nxt = blocks[i + 1].strip() if i + 1 < len(blocks) else ""
        m = re.fullmatch(r"File:\s*(.+?)\.(?:pdf|docx?|pptx?)", p, re.I)
        if m:
            out.append("## " + m.group(1).strip()); count("file markers made headings"); continue
        words = p.split()
        if ("\n" not in p and not re.match(r"[#*>-]|\d+[.)] ", p) and 1 <= len(words) <= 9 and len(p) <= 64
                and (not re.search(r"[.,;:]$", p) or p.endswith("?")) and len(nxt) > 120 and not nxt.startswith("#")
                and p.lower() != title.lower() and p.lower().rstrip("?!") not in LABELS):
            caps = [w for w in words if w.lower() not in TITLE_SMALL]
            if caps and p[:1].isupper() and sum(w[:1].isupper() or w[:1].isdigit() for w in caps) >= 0.8 * len(caps):
                t = tidy_heading(p, authors_first)
                if t and good_heading(t, prior_words, p):
                    prior_words.update(w.lower() for w in re.findall(r"[A-Za-z’']+", t))
                    out.append("### " + t); count("standalone titles made headings"); continue
        out.append(b)
    return out


def clean_body(body, meta):
    body = strip_furniture(body)
    authors_first = {a.split()[0].lower() for a in meta.get("authors", []) if a.split()}
    author_names = {a.lower() for a in meta.get("authors", [])}
    blocks = re.split(r"\n\s*\n", body.strip())
    out, prior_words = [], set()
    for i, b in enumerate(blocks):
        lines = [l for l in b.split("\n") if l.strip()]
        if not lines: continue
        if len(lines) == 1 and WORD_ART.match(lines[0].strip()):
            count("word-art letters removed"); continue
        if len(lines) == 1 and re.match(r"^#{2,6}\s", lines[0]):
            h = fix_heading(fix_words(lines[0]), authors_first, prior_words, author_names)
            if h: out.append(h)
            continue
        if len(lines) == 1 and re.sub(r"^(?:by|dr\.?)\s+|[*_]", "", lines[0].strip(), flags=re.I).strip().lower() in author_names:
            count("byline repeats removed"); continue                              # "Dr. Bill Bright" (shown under the title)
        lines = clean_list_lines(lines)
        if not lines: continue
        lines = reorder_numbered(lines)
        text = "\n".join(fix_words(l) for l in lines)
        # a paragraph ending in a stray word-art letter or a fill-in number: "…get back in the race. f", "…meet those needs. 1."
        text2 = re.sub(r"(?<=[.!?”\"])\s+(?:[a-z]|\d{1,2}\.)$", "", text)
        if text2 != text: count("stray trailing letters/numbers removed"); text = text2
        if not (UL.match(lines[0]) or OL.match(lines[0])) and "\n" not in text:
            text = split_inline_bullets(text)
        out.append(text.strip())
    out = promote_titles([x for x in out if x], meta.get("title", ""), authors_first, set())
    return "\n\n".join(out) + "\n"


def main():
    changed = 0
    for topic in TOPICS:
        d = os.path.join(ART, topic)
        if not os.path.isdir(d): continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".md"): continue
            p = os.path.join(d, f)
            text = open(p, encoding="utf-8").read()
            m = re.match(r"(---\n.*?\n---\n)", text, re.S)
            head, body = m.group(1), text[m.end():]
            import json
            meta = {}
            for line in head.strip("-\n").split("\n"):
                k, _, v = line.partition(": ")
                try: meta[k] = json.loads(v)
                except ValueError: pass
            new = head + "\n" + clean_body(body, meta)
            if new != text:
                changed += 1
                if not DRY: open(p, "w", encoding="utf-8").write(new)
    print(f"{'Would change' if DRY else 'Changed'} {changed} articles")
    for k, v in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {v:6}  {k}")


if __name__ == "__main__":
    main()
