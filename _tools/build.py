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
        elif all(UL.match(l) for l in lines):
            out.append("<ul>" + "".join(f"<li>{inline(UL.sub('', l))}</li>" for l in lines) + "</ul>")
        elif all(OL.match(l) for l in lines):
            start = int(OL.match(lines[0]).group(1))
            st = f' start="{start}"' if start != 1 else ""
            out.append(f"<ol{st}>" + "".join(f"<li>{inline(OL.sub('', l))}</li>" for l in lines) + "</ol>")
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
    toc = toc_entries(toc, a["title"])
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


def toc_entries(toc, title):
    """Keep headings that read like headings: drop the article title repeated, chart debris
    ("Aug. Sept. Oct. * @ #"), whole sentences, and repeats."""
    out, seen = [], {title.lower()}
    for lvl, hid, text in toc:
        t = text.strip().lstrip("-–•* ").strip()
        low = t.lower()
        words = t.split()
        if not t or low in seen or len(t) > 70 or len(words) > 10: continue
        if re.search(r"[*@#%|=<>]", t) or sum(c.isalpha() for c in t) < 0.7 * len(t.replace(" ", "")): continue
        if len(words) >= 4 and len({w.lower() for w in words}) < 0.75 * len(words): continue
        seen.add(low)
        out.append((lvl, hid, t))
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
