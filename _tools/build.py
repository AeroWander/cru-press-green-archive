"""Build the static website: articles/**/*.md  ->  site/

site/
  index.html                     library home: topics, search, filters
  articles/<topic>/<slug>.html   one reading page per article
  assets/style.css, app.js       shared styles and search code (source: _tools/assets/)
  assets/library.js              metadata index for search (titles, summaries, headings, filters)
  assets/fulltext.js             article text, loaded only when "Search inside articles" is ticked

No dependencies beyond Python 3. Run:  python3 _tools/build.py
"""
import hashlib, html, json, os, re, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from import_articles import TOPICS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(ROOT, "articles")
SITE = os.path.join(ROOT, "site")
ASSETS = os.path.join(ROOT, "_tools", "assets")
SITE_NAME = "Cru Press Green Archive"
VER = "0"  # set in main(): changes whenever the assets or articles change, so browsers fetch fresh copies

TOPIC_BLURB = {
    "evangelism": "Sharing the gospel one-to-one and campus-wide: conversations, tools, outreaches and apologetics.",
    "discipleship": "Following up, building others up, prayer, the Spirit-filled life and multiplying disciples.",
    "bible-and-theology": "Studying Scripture, knowing God, grace and assurance, and the history of revival.",
    "small-groups": "Leading small groups and weekly meetings, building community, conferences and retreats.",
    "leadership": "Launching and leading ministries: vision, planning, teams, coaching and movement growth.",
    "life-and-character": "Identity, purity, relationships, suffering, conflict, calling and life after college.",
    "mission-and-justice": "The Great Commission, justice and compassion, ethnic ministry and summer projects.",
    "flyers-and-promo": "Poster copy, flyer text and promo pieces for groups, outreaches and campaigns.",
}


def esc(s): return html.escape(str(s), quote=True)


def read(path):
    text = open(path, encoding="utf-8").read()
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    meta = {}
    for line in m.group(1).split("\n"):
        k, _, v = line.partition(": ")
        meta[k] = json.loads(v)
    return meta, text[m.end():].strip()


# ---------- Markdown -> HTML (the subset the articles use) ----------
UL = re.compile(r"^\s*[-*•]\s+")
OL = re.compile(r"^\s*(\d{1,3})[.)]\s+")


def inline(s):
    s = esc(s).replace("&#x27;", "’")
    s = re.sub(r"(?<=\S)\s*--\s*(?=\S)", "—", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" rel="noopener">\1</a>', s)
    return s


def hslug(s, used):
    b = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:50] or "section"
    k, n = b, 2
    while k in used: k = f"{b}-{n}"; n += 1
    used.add(k)
    return k


def render_list_block(lines):
    """A block containing list lines. Handles: a lead-in paragraph before the list, wrapped lines that continue
    the previous item, bullets nested under a numbered item (and vice versa), and source numbering that
    skips or repeats (each item keeps its printed number)."""
    html_, lead, items = [], [], []          # items: [kind, number, text, children[(kind, number, text)]]
    for l in lines:
        mu, mo = UL.match(l), OL.match(l)
        if mu or mo:
            kind, num, text = ("ul", None, UL.sub("", l)) if mu else ("ol", int(mo.group(1)), OL.sub("", l))
            if items and kind != items[0][0]:
                items[-1][3].append([kind, num, text])            # other kind under the current item → nested
            else:
                items.append([kind, num, text, []])
        elif items:
            target = items[-1][3][-1] if items[-1][3] else items[-1]
            target[2] += " " + l.strip()                          # wrapped line → same item
        else:
            lead.append(l.strip())
    if lead: html_.append("<p>" + inline(" ".join(lead)) + "</p>")

    def one_list(kind, entries):
        if kind == "ul":
            return "<ul>" + "".join(f"<li>{inline(e[2])}{sub(e)}</li>" for e in entries) + "</ul>"
        start, parts, expect = entries[0][1], [], entries[0][1]
        for e in entries:
            val = f' value="{e[1]}"' if e[1] != expect else ""
            parts.append(f"<li{val}>{inline(e[2])}{sub(e)}</li>"); expect = e[1] + 1
        return f'<ol{f" start={chr(34)}{start}{chr(34)}" if start != 1 else ""}>' + "".join(parts) + "</ol>"

    def sub(e):
        return one_list(e[3][0][0], [c + [[]] for c in e[3]]) if len(e) > 3 and e[3] else ""

    if items: html_.append(one_list(items[0][0], items))
    return "\n".join(html_)


def md_to_html(md, skip_headings=()):
    """skip_headings: lower-cased heading texts to leave out entirely (e.g. author names used as headings)."""
    out, toc, used = [], [], set()
    for block in re.split(r"\n\s*\n", md.strip()):
        lines = [l for l in block.split("\n") if l.strip()]
        if not lines: continue
        m = re.match(r"^(#{1,6})\s+(.*)$", lines[0])
        if m and len(lines) == 1 and m.group(2).strip().lower() in skip_headings:
            continue
        if m and len(lines) == 1:
            lvl = min(4, max(2, len(m.group(1))))
            text = m.group(2).strip()
            hid = hslug(text, used)
            out.append(f'<h{lvl} id="{hid}">{inline(text)}</h{lvl}>')
            if lvl <= 3: toc.append((lvl, hid, text))
        elif m:  # heading followed by text in the same block
            lvl = min(4, max(2, len(m.group(1))))
            hid = hslug(m.group(2), used)
            out.append(f'<h{lvl} id="{hid}">{inline(m.group(2))}</h{lvl}>')
            if lvl <= 3: toc.append((lvl, hid, m.group(2)))
            out.append("<p>" + inline(" ".join(l.strip() for l in lines[1:])) + "</p>")
        elif any(UL.match(l) or OL.match(l) for l in lines):
            out.append(render_list_block(lines))
        elif all(l.startswith(">") for l in lines):
            out.append("<blockquote><p>" + inline(" ".join(l.lstrip("> ").strip() for l in lines)) + "</p></blockquote>")
        elif lines[0].startswith("|") and len(lines) > 1 and re.match(r"^\|?[\s:|-]+\|?$", lines[1]):
            rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in lines if not re.match(r"^\|?[\s:|-]+\|?$", l)]
            t = "<thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in rows[0]) + "</tr></thead><tbody>"
            t += "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
            out.append(f'<div class="tablewrap"><table>{t}</tbody></table></div>')
        else:
            out.append("<p>" + inline(" ".join(l.strip() for l in lines)) + "</p>")
    return "\n".join(out), toc


def plain(md):
    s = re.sub(r"^#{1,6}\s+", "", md, flags=re.M)
    s = re.sub(r"^\s*([-*•>]|\d{1,3}[.)])\s+", "", s, flags=re.M)
    s = s.replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", s).strip()


# ---------- page shell ----------
HEAD_JS = ("<script>(function(){try{var t=localStorage.getItem('al-theme');"
           "if(t)document.documentElement.dataset.theme=t}catch(e){}})();</script>")


def shell(title, desc, depth, body, topic=None, scripts="", page=""):
    up = "../" * depth
    # phones: a search field in the sticky header. On article pages it sends the query to the home page;
    # on the home page app.js wires it to the main search box and shows it once that box scrolls away.
    go = f"location.href='{up}index.html#q='+encodeURIComponent(this.q.value.trim());return false"
    tattr = f' data-topic="{topic}"' if topic else ""
    return f"""<!doctype html>
<html lang="en"{tattr}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="theme-color" content="#1f3a2e">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%232f6b4f'/%3E%3Cpath d='M9 8h6a3 3 0 0 1 3 3v13a3 3 0 0 0-3-3H9zM23 8h-2a3 3 0 0 0-3 3v13a3 3 0 0 1 3-3h2z' fill='%23fff'/%3E%3C/svg%3E">
<link rel="stylesheet" href="{up}assets/style.css?v={VER}">
{HEAD_JS}
</head>
<body class="{page}">
<a class="skip" href="#main">Skip to content</a>
<header class="bar"><div class="bar-in">
<a class="brand" href="{up}index.html"><span class="logo" aria-hidden="true"></span><span class="brand-name">{SITE_NAME}</span></a>
<nav class="bar-nav"><a href="{up}index.html#browse">Topics</a><a href="{up}index.html#search">Search</a></nav>
<button class="theme" type="button" aria-label="Switch light or dark mode" onclick="alToggleTheme()"><span aria-hidden="true">◐</span></button>
</div>
<form class="bar-search" role="search" action="{up}index.html" onsubmit="{go}">
<svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="M20 20l-4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
<input id="bar-q" name="q" type="search" placeholder="Search the archive…" aria-label="Search the archive" autocomplete="off" enterkeyhint="search">
</form>
</header>
{body}
<footer class="foot"><div class="foot-in"><a href="{up}index.html">{SITE_NAME}</a> · Articles, guides and studies for campus ministry</div></footer>
<script>function alToggleTheme(){{var d=document.documentElement,c=d.dataset.theme||'light',n=c==='dark'?'light':'dark';d.dataset.theme=n;try{{localStorage.setItem('al-theme',n)}}catch(e){{}}}}</script>
{scripts}
</body>
</html>
"""


def reading_minutes(words): return max(1, round(words / 230))


def chip_link(label, key, value, depth):
    from urllib.parse import quote
    return f'<a class="chip" href="{"../" * depth}index.html#{key}={quote(value)}">{esc(label)}</a>'


def article_page(a, related, series_nav):
    depth = 2
    body_html, toc = md_to_html(a["body"], {x.lower() for x in a.get("authors", [])})
    tname = TOPICS[a["topic"]][0]
    meta_bits = [f'{a["words"]:,} words', f'{reading_minutes(a["words"])} min read', a["type"]]
    if a.get("audience"): meta_bits.append("For " + ", ".join(a["audience"]).lower())
    byline = ""
    if a.get("authors"):
        byline = '<p class="byline">By ' + ", ".join(chip_link(x, "author", x, depth).replace('class="chip"', 'class="plain"') for x in a["authors"]) + "</p>"
    series = ""
    if a.get("series"):
        link = chip_link(a["series"], "series", a["series"], depth).replace('class="chip"', 'class="plain"')
        series = f'<p class="series-tag">Part of the series {link}</p>'
    chips = "".join(chip_link(t, "theme", t, depth) for t in a["themes"])
    note = f'<p class="note"><b>Note</b> {esc(a["note"])}</p>' if a.get("note") else ""
    toc = toc_entries(toc, a["title"], a.get("authors", []), a.get("series", ""), a["words"]) if a.get("toc", True) else []
    toc_html = ""
    if len(toc) >= 3:
        toc_html = f'<details class="toc"><summary>On this page <small>{sum(1 for i, e in enumerate(toc) if e[0] == 2 or i == 0)} sections</small></summary>{toc_list(toc)}</details>'
    rel = ""
    if related:
        rel = '<section class="related"><h2>Related reading</h2><div class="cards">' + "".join(card(r, depth) for r in related) + "</div></section>"
    snav = ""
    if series_nav:
        prev, nxt = series_nav
        cells = ""
        cells += (f'<a class="prev" href="../{prev["topic"]}/{prev["slug"]}.html"><small>← Previous in {esc(a["series"])}</small><span>{esc(prev["title"])}</span></a>' if prev else "<span></span>")
        cells += (f'<a class="next" href="../{nxt["topic"]}/{nxt["slug"]}.html"><small>Next in {esc(a["series"])} →</small><span>{esc(nxt["title"])}</span></a>' if nxt else "<span></span>")
        snav = f'<nav class="pn" aria-label="Series navigation">{cells}</nav>'
    src = f'<p class="source">Original file: <code>{esc(a["source"])}</code></p>'
    body = f"""<main id="main" class="article-main">
<div class="hero hero-article"><div class="hero-in">
<nav class="crumbs" aria-label="Breadcrumb"><a href="../../index.html">Library</a><span>›</span><a href="../../index.html#topic={a["topic"]}">{esc(tname)}</a></nav>
<h1>{esc(a["title"])}</h1>
{byline}
<p class="meta">{" · ".join(esc(b) for b in meta_bits)}</p>
</div></div>
<div class="reader">
<article>
{series}
<div class="summary"><b>In brief</b><p>{esc(a["summary"])}</p></div>
<div class="chips">{chips}</div>
{note}
{toc_html}
<div class="body">
{body_html}
</div>
{snav}
{src}
</article>
</div>
{rel}
</main>"""
    scripts = ("<script>var t=document.querySelector('.toc');"
               "if(t&&matchMedia('(min-width:900px)').matches)t.open=true</script>")
    return shell(f'{a["title"]} · {SITE_NAME}', a["summary"][:160], depth, body, topic=a["topic"], scripts=scripts)


WORDS = set()
if os.path.exists("/usr/share/dict/words"):
    WORDS = {w.strip().lower() for w in open("/usr/share/dict/words", encoding="utf-8", errors="ignore")}
SUFFIXES = ("ing", "ed", "es", "s", "ly", "ness", "ment", "ers", "er", "'s", "’s", "n")
LABEL_WORDS = {"discuss", "commentary", "notes", "note", "questions", "question", "answer", "answers", "read", "it is",
               "it is not", "to think about", "launch questions", "explore questions", "application", "leader", "leaders"}


def is_word(w):
    w = w.lower().strip("’'")
    if not WORDS or w in WORDS or len(w) <= 2 and w in {"a", "i", "an", "as", "at", "be", "by", "do", "go", "he", "if", "in", "is", "it", "me", "my", "no", "of", "on", "or", "so", "to", "up", "us", "we"}:
        return True
    for suf in SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            stem = w[: -len(suf)]
            if stem in WORDS or stem + "e" in WORDS or (stem.endswith("i") and stem[:-1] + "y" in WORDS): return True
            if len(stem) > 3 and stem[-1] == stem[-2] and stem[:-1] in WORDS: return True     # planning → plan
    return False


FIRST_NAMES = {"andrea", "bill", "bob", "cas", "dan", "eric", "jeff", "jerry", "jim", "john", "keith", "larry", "libby",
               "lori", "marilyn", "mike", "paul", "phil", "rick", "scott", "steven", "tanya", "tim", "timothy", "tom", "will"}
NAME_PREFIX = re.compile(r"^(?:by\s+|dr\.\s+)?([A-Z][a-z]+)\s+(?:[A-Z]\.?\s+)?([A-Z][a-z]+)\b[.,]?\s*")
SMALL_OK = {"a", "i", "an", "as", "at", "be", "by", "do", "go", "he", "if", "in", "is", "it", "me", "my", "no", "of", "on",
            "or", "so", "to", "up", "us", "we", "vs", "tv", "ii", "iv", "vi", "d", "s", "t"}
LONE_WORDS = {"white", "papers", "next", "five", "you", "what", "great", "map", "think", "contents", "introduction!"}
DROP_PHRASES = re.compile(r"excerpt|table of contents|subhead level|starter kit|teachers? notes|needs to be format|"
                          r"leader[’'í]?s guide|^contents$|^chapter\s+(\d+|[a-z]+(\s[a-z]+)?)$|^part\s+\d+$", re.I)
TITLE_SMALL = set("a an and as at but by for from in into nor of on or per the to vs via with".split())
ACRONYMS = {"mtl", "wsn", "ijm", "usa", "aia", "tv", "dvd", "ad2000", "c456", "e2", "hiv", "aids"}


def title_case(t):
    out = []
    for k, w in enumerate(t.split()):
        core = re.sub(r"[^A-Za-z0-9]", "", w).lower()
        if core in ACRONYMS: out.append(w.upper() if core != "ad2000" else "AD2000"); continue
        lw = w.lower()
        out.append(lw if k and core in TITLE_SMALL else re.sub(r"[a-z]", lambda m: m.group(0).upper(), lw, count=1))
    return " ".join(out)


def tidy_heading(t, authors_first):
    """Repair headings that are fine apart from PDF artefacts. Returns the cleaned text ('' if nothing is left)."""
    t = re.sub(r"(?<=[A-Za-z])í(?=(s|t|ll|re|ve|d|m)\b)", "’", t)             # mojibake apostrophe
    t = re.sub(r"(?<=[A-Za-z)])\s*(>>|››|»)\s*(?=[A-Z])", " · ", t)            # "4 Walks >> Walk Assured"
    t = re.sub(r"^([B-HJ-Z]) (?=[A-Z][a-z])", "", t)                            # stray letter: "Q Chasing the…"
    t = re.sub(r"^([A-Z]) (?=\1[a-z’'])", "", t)                                 # drop-cap: "D Don’t"
    w = t.split()
    if len(w) >= 2 and len(w) % 2 == 0 and [x.lower() for x in w[:len(w)//2]] == [x.lower() for x in w[len(w)//2:]]:
        t = " ".join(w[:len(w)//2])                                              # "Church Church"
    w = t.split()
    if len(w) >= 4 and len(w) % 2 == 0 and all(w.count(x) == 2 for x in w):
        seen_w = []
        for x in w:
            if x not in seen_w: seen_w.append(x)
        t = " ".join(seen_w)                                                     # "Attitude and Attitude and Perspective Perspective"
    t = re.sub(r"\b([A-Za-z]+)- ([a-z]+)\b", lambda m: m.group(1) + m.group(2) if is_word(m.group(1) + m.group(2)) else m.group(0), t)
    m = NAME_PREFIX.match(t)                                                      # "Eric Swanson The Advantage of Teams"
    if m and (m.group(1).lower() in FIRST_NAMES or m.group(1).lower() in authors_first):
        t = t[m.end():]
    t = re.sub(r"^(by|dr\.)\s+\S+\s+\S+\s*", "", t, flags=re.I) if re.match(r"^(by|dr\.)\s", t, re.I) else t
    t = re.sub(r"(?<=[a-z]{3})\d\b", "", t).rstrip("]").strip(" -–—:")
    t = re.sub(r"^(\w+) \1\b", r"\1", t, flags=re.I)                              # "Appendix Appendix C"
    letters = [c for c in t if c.isalpha()]
    weird = any(re.search(r"[a-z][A-Z]|[A-Z]{2}[a-z]+[A-Z]|^[a-z]+[A-Z]|^[A-Z]{2,}[a-z]{2,}", x) for x in t.split())
    caps = sum(1 for x in t.split() if len(x) >= 3 and x.isupper())
    if weird or (letters and caps >= 2 and caps >= 0.5 * len(t.split())):
        t = title_case(t)
    elif re.search(r"[a-z]", t):                                                  # "Justice Week EVENTS"
        t = " ".join(x.capitalize() if len(x) >= 4 and x.isupper() and x.lower() not in ACRONYMS else x for x in t.split())
    t = re.sub(r"(\d)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), t)
    t = re.sub(r"\b(Ii|Iii|Iv|Vi|Vii|Viii|Ix)\b(?=[.:\s])", lambda m: m.group(1).upper(), t)
    t = re.sub(r"^((?:[A-Z]|\d{1,2}|[IVX]+)[.:)]\s+|[^:]{1,40}:\s*)(the|a|an|but)\b", lambda m: m.group(1) + m.group(2).capitalize(), t)
    t = re.sub(r"(?<!the )(?<!U\.)\bUS\b", "Us", t)
    return t[:1].upper() + t[1:] if t else t


def good_heading(t, prior_words, raw):
    """True when t reads like a real section heading rather than PDF debris. raw is the text before tidying."""
    if not (2 < len(t) <= 64) or not re.match(r"[A-Z0-9“\"‘(]", t): return False     # starts mid-sentence
    if re.search(r"[*@#%|=<>›»~_\\]|/{2,}|\.{3}|…", t): return False                 # symbols, chart marks
    if re.search(r"\b(what|the|a|an|and|of|to|so|now|is|in|it) \1\b", t, re.I) or re.search(r",[A-Za-z]", t):
        return False                                                                  # "What What", "So,what"
    if re.search(r"\(con[’'t.]*\)|\bcont(inued|’d|'d)?\b", t, re.I): return False       # "(con't)" repeats
    if DROP_PHRASES.search(t) or t.lower() in LONE_WORDS: return False
    first = re.search(r"(?<![A-Za-z0-9])[A-Za-z]", t)                               # first word that starts with a letter
    if first and first.group(0).islower(): return False                              # "8) going to work"
    if re.search(r"[?.!]\s+[A-Z]{4,}$", raw): return False                           # "…tomb? ENDNOTES"
    if t.count("“") != t.count("”") or t.count('"') % 2: return False                 # quote cut off mid-way
    if re.search(r"\w- \w", t): return False                                         # "At- Tempts at Trans- Form"
    if len(re.findall(r"[.!?](\s|$)", t)) >= 2 and not re.match(r"^\d+\.\s", t): return False   # several sentences
    rw = raw.split()
    if rw and len(rw[0]) >= 3 and rw[0].isupper() and sum(1 for x in rw if x.isalpha() and x.islower()) >= 3:
        return False                                                                  # "AFTER THE FALL, humans became…"
    if re.search(r"(?<![A-Za-z])(page|p\.)\s*\d+|[a-z?.,;:]\s+\d{1,3}$|\d+ \d+$", t, re.I) and not re.match(
            r"(step|part|chapter|week|session|lesson|day|phase|stage|level|appendix|quarter|year|volume|rule|principle|acts|john|luke|mark|matthew|romans)\b", t, re.I):
        return False                                                                  # page numbers
    if re.search(r"[,;]$|\b(the|a|an|and|of|to|in|with|for|that|when|as|be|every|our|your|their|by|from|than|or|but)$", t, re.I): return False
    if re.match(r"(of|and|or|but|to|with|than|as|in)\b", t, re.I): return False       # starts mid-phrase
    if t.endswith(":") and (len(t.split()) <= 3 or t.rstrip(":").lower() in LABEL_WORDS): return False
    if t.rstrip(":").lower() in LABEL_WORDS: return False
    words = re.findall(r"[A-Za-z’']+", t)
    if not words: return False
    if sum(1 for w in words if len(w) <= 2 and w.lower() not in SMALL_OK) >= 2: return False   # "Get Tin G Bib Li Cal"
    if any(len(w) == 1 and w.islower() and w != "a" for w in words[1:]): return False          # "Relationshi s"
    if len(words) >= 5 and not re.search(r"[,:;?!.•—–-]", t) and sum(w.islower() for w in words) >= 0.6 * len(words):
        return False                                                                  # captions run together
    if sum(len(w) <= 2 for w in words) > max(1, len(words) // 2): return False
    if sum(is_word(w) for w in words) < 0.8 * len(words): return False              # OCR noise, split words
    if len(words) > 10: return False
    lw = [w.lower() for w in words]
    if len(lw) >= 2 and prior_words and all(w in prior_words for w in lw) and not re.search(r"\b(the|of|and|to|a|how|what|why)\b|[·:]", t, re.I):
        return False                                                                  # earlier headings glued together
    return True


def toc_entries(toc, title, authors=(), series="", words=10**6):
    """Headings for the 'On this page' box. Anything that doesn't read like a real heading is left out;
    if most of an article's headings are debris, it gets no box at all (returns [])."""
    if words < 400: return []
    authors_first = {a.split()[0].lower() for a in authors if a.split()}
    author_names = {a.lower() for a in authors}
    series_stem = series.lower().rstrip("s")
    out, seen, prior_words, short_distinct = [], {title.lower()}, set(), 0
    for lvl, hid, text in toc:
        raw = re.sub(r"\s+", " ", text.strip().lstrip("-–•* ").strip())
        t = tidy_heading(raw, authors_first)
        low = t.lower().rstrip(":. ")
        if not low or low in seen or low in author_names: continue
        seen.add(low)
        if len(t) <= 64: short_distinct += 1
        if series_stem and len(series_stem) > 4 and low.startswith(series_stem): continue
        if good_heading(t, prior_words, raw):
            out.append((lvl, hid, t.rstrip(":")))
            prior_words.update(w.lower() for w in re.findall(r"[A-Za-z’']+", t))
    # hide the box when most short, distinct candidates were debris (long sentences don't count either way)
    if short_distinct >= 4 and len(out) < 0.5 * short_distinct: return []
    # one lone top-level heading over a pile of sub-headings reads badly; show them all at one level
    if sum(1 for l, _, _ in out if l == 2) < 2: out = [(2, h, t) for _, h, t in out]
    # "4 Walks · Walk Assured", "4 Walks · Walk Forgiven" → a "4 Walks" group with the sessions under it
    grouped, parent = [], None
    for lvl, hid, t in out:
        if " · " in t:
            head, rest = t.split(" · ", 1)
            if head != parent:
                # an earlier bare "4 Walks" overview entry is replaced by this group
                grouped = [g for k, g in enumerate(grouped) if not (g[0] == 2 and g[2] == head and
                           (k + 1 == len(grouped) or grouped[k + 1][0] == 2))]
                grouped.append((2, hid, head)); parent = head
            grouped.append((3, hid, rest))
        else:
            grouped.append((lvl, hid, t)); parent = None if lvl == 2 else parent
    out = grouped
    # very long lists: keep just the main sections when there are enough of them
    if len(out) > 60 and sum(1 for l, _, _ in out if l == 2) >= 5: out = [e for e in out if e[0] == 2]
    return out


def toc_list(toc):
    """Numbered sections, each with its sub-sections nested beneath it."""
    html_, n, open_sub = ["<ol class=\"toc-list\">"], 0, False
    for lvl, hid, t in toc:
        link = f'<a href="#{hid}" title="{esc(t)}">{inline(t)}</a>'
        if lvl == 2 or n == 0:
            if open_sub: html_.append("</ol>"); open_sub = False
            if n: html_.append("</li>")
            n += 1
            html_.append(f'<li><span class="toc-n">{n}</span>{link}')
        else:
            if not open_sub: html_.append('<ol class="toc-sub">'); open_sub = True
            html_.append(f"<li>{link}</li>")
    if open_sub: html_.append("</ol>")
    html_.append("</li></ol>")
    return "".join(html_)


def card(a, depth):
    up = "../" * depth
    return (f'<a class="card" data-topic="{a["topic"]}" href="{up}articles/{a["topic"]}/{a["slug"]}.html">'
            f'<span class="card-topic">{esc(TOPICS[a["topic"]][0])}</span>'
            f'<b>{esc(a["title"])}</b><span class="card-sum">{esc(a["summary"][:150].rsplit(" ", 1)[0])}…</span>'
            f'<span class="card-meta">{reading_minutes(a["words"])} min · {esc(a["type"])}</span></a>')


def related_for(a, all_arts):
    mine = set(a["themes"])
    scored = []
    for b in all_arts:
        if b is a or b["type"] == "Flyer" and a["type"] != "Flyer": continue
        s = 2 * len(mine & set(b["themes"])) + (1 if b["topic"] == a["topic"] else 0) + (1 if b.get("series") and b.get("series") == a.get("series") else 0)
        if a.get("authors") and set(a["authors"]) & set(b.get("authors", [])): s += 1
        if s >= 2: scored.append((-s, -min(b["words"], 4000), b["title"], b))
    scored.sort(key=lambda x: x[:3])
    return [x[3] for x in scored[:3]]


def main():
    arts = []
    for topic in TOPICS:
        d = os.path.join(ART, topic)
        if not os.path.isdir(d): continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".md"): continue
            meta, body = read(os.path.join(d, f))
            meta.update(slug=f[:-3], topic=topic, body=body)
            arts.append(meta)

    global VER
    h = hashlib.sha1()
    for f in sorted(os.listdir(ASSETS)): h.update(open(os.path.join(ASSETS, f), "rb").read())
    for a in arts: h.update(json.dumps(a, sort_keys=True, ensure_ascii=False).encode())
    VER = h.hexdigest()[:10]

    if os.path.isdir(SITE): shutil.rmtree(SITE)
    os.makedirs(os.path.join(SITE, "assets"))
    for f in os.listdir(ASSETS):
        shutil.copy(os.path.join(ASSETS, f), os.path.join(SITE, "assets", f))

    # series order: by source path (files are usually numbered/ordered in their folders)
    series = {}
    for a in arts:
        if a.get("series"): series.setdefault(a["series"], []).append(a)
    for lst in series.values():
        lst.sort(key=lambda x: (x["source"].lower()))

    index, fulltext = [], []
    for i, a in enumerate(arts):
        nav = None
        if a.get("series") and len(series[a["series"]]) > 1:
            lst = series[a["series"]]
            j = lst.index(a)
            nav = (lst[j - 1] if j > 0 else None, lst[j + 1] if j + 1 < len(lst) else None)
        outdir = os.path.join(SITE, "articles", a["topic"])
        os.makedirs(outdir, exist_ok=True)
        with open(os.path.join(outdir, a["slug"] + ".html"), "w", encoding="utf-8") as fh:
            fh.write(article_page(a, related_for(a, arts), nav))
        heads = [m.group(1).strip() for m in re.finditer(r"^#{2,4}\s+(.+)$", a["body"], re.M)]
        index.append({
            "t": a["title"], "p": f'articles/{a["topic"]}/{a["slug"]}.html', "tp": a["topic"],
            "at": a.get("also_topics", []), "ty": a["type"], "th": a["themes"], "au": a.get("audience", []),
            "by": a.get("authors", []), "se": a.get("series", ""), "w": a["words"], "s": a["summary"],
            "h": " · ".join(heads[:25])[:600],
        })
        fulltext.append(plain(a["body"]))

    topics = [{"id": k, "name": v[0], "blurb": TOPIC_BLURB[k], "themes": v[1]} for k, v in TOPICS.items()]
    with open(os.path.join(SITE, "assets", "library.js"), "w", encoding="utf-8") as fh:
        fh.write("window.LIBRARY=" + json.dumps({"topics": topics, "articles": index}, ensure_ascii=False, separators=(",", ":")) + ";\n")
    with open(os.path.join(SITE, "assets", "fulltext.js"), "w", encoding="utf-8") as fh:
        fh.write("window.FULLTEXT=" + json.dumps(fulltext, ensure_ascii=False, separators=(",", ":")) + ";\n")

    # home page: static topic grid (works without JS); app.js adds search and filters
    grid = []
    for t in topics:
        n = sum(1 for a in arts if a["topic"] == t["id"] or t["id"] in a.get("also_topics", []))
        grid.append(f'<a class="topic-card" data-topic="{t["id"]}" href="#topic={t["id"]}"><span class="tc-count">{n}</span>'
                    f'<h3>{esc(t["name"])}</h3><p>{esc(t["blurb"])}</p></a>')
    words = sum(a["words"] for a in arts)
    body = open(os.path.join(ASSETS, "home.html"), encoding="utf-8").read()
    body = body.replace("{{TOPIC_GRID}}", "\n".join(grid)).replace("{{COUNT}}", f"{len(arts):,}") \
               .replace("{{WORDS}}", f"{words / 1e6:.1f} million").replace("{{SITE}}", SITE_NAME)
    os.remove(os.path.join(SITE, "assets", "home.html"))
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(shell(SITE_NAME, f"{len(arts)} articles, guides and studies for campus ministry, searchable by topic, theme, audience, author and series.",
                       0, body, page="home", scripts=f'<script src="assets/library.js?v={VER}"></script>\n<script src="assets/app.js?v={VER}"></script>'))
    print(f"Built {len(arts)} article pages -> {os.path.relpath(SITE, ROOT)}/")


if __name__ == "__main__":
    main()
