"""Re-extract article text from the source PDFs in reading order (columns read one at a time).

Pipeline for each PDF-based article:
  layout_extract (Swift, PDFKit)  →  text fragments with positions and font sizes   (_tools/cache/layout/*.json)
  this script: fragments → lines → XY-cut into columns/bands → rows in reading order, blank rows at paragraph gaps
  → md.py from the Asset Index build (heading detection, header/footer removal, line joining) → Markdown body
  → quality gate: the new body replaces the current one only if it reads better and loses no text.

Run:  python3 _tools/reextract.py            (extract where needed, compare, write winners, print a report)
      python3 _tools/reextract.py --dry      (compare only)
      python3 _tools/reextract.py --only slug1,slug2 --show   (print the new text for some articles)
Afterwards run clean_articles.py and build.py.
"""
import json, os, re, statistics, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(ROOT, "articles")
CACHE = os.path.join(ROOT, "_tools", "cache")
LAYOUT = os.path.join(CACHE, "layout")
ASSETS = os.path.join(ROOT, "..", "Resource App", "Assets", "CruPress Green Archive")
MDPY = os.path.join(ROOT, "..", "Resource App", "Asset Index", "_build")
sys.path.insert(0, MDPY)
import md as MD  # noqa: E402  (the converter used for the original import)

ARGS = sys.argv[1:]
DRY, SHOW = "--dry" in ARGS, "--show" in ARGS
ONLY = set(ARGS[ARGS.index("--only") + 1].split(",")) if "--only" in ARGS else None


# ---------- fragments and lines ----------
def to_lines(segs):
    """Group positioned runs into visual lines, then split each line wherever there is a column-sized gap."""
    frags = [dict(t=s[0], x0=s[1], top=s[2], x1=s[3], bot=s[4], size=s[5] or 9, bold=bool(s[6])) for s in segs if s[0].strip()]
    if not frags: return []
    frags.sort(key=lambda f: ((f["top"] + f["bot"]) / 2, f["x0"]))
    rows, cur = [], [frags[0]]
    for f in frags[1:]:
        mid, cmid = (f["top"] + f["bot"]) / 2, statistics.median((g["top"] + g["bot"]) / 2 for g in cur)
        h = max(2, min(f["bot"] - f["top"], statistics.median(g["bot"] - g["top"] for g in cur)))
        if abs(mid - cmid) <= h * 0.55: cur.append(f)
        else: rows.append(cur); cur = [f]
    rows.append(cur)
    lines = []
    for row in rows:
        row.sort(key=lambda f: f["x0"])
        piece = dict(row[0])
        for f in row[1:]:
            gap, em = f["x0"] - piece["x1"], max(piece["size"], f["size"])
            if gap > em * 0.5:                       # a real gap (column gutter, tab stop): keep separate
                lines.append(piece); piece = dict(f); continue
            sep = "" if gap < em * 0.12 or piece["t"].endswith(" ") or f["t"].startswith(" ") else " "
            piece["t"] = piece["t"].rstrip() + sep + f["t"].lstrip() if sep else piece["t"] + f["t"]
            piece["x1"] = max(piece["x1"], f["x1"]); piece["top"] = min(piece["top"], f["top"])
            piece["bot"] = max(piece["bot"], f["bot"]); piece["size"] = max(piece["size"], f["size"])
            piece["bold"] = piece["bold"] and f["bold"]
        lines.append(piece)
    return lines


# ---------- XY-cut reading order ----------
def gaps(intervals, lo, hi, min_gap):
    iv = sorted(intervals)
    out, reach = [], lo
    for a, b in iv:
        if a - reach >= min_gap and reach > lo: out.append((reach, a))
        reach = max(reach, b)
    return out


def xy_cut(lines, depth=0):
    """Order lines into reading order. Look for a column gutter using body-size lines only; lines that run
    across the gutter (titles, full-width boxes) become separators, with the columns between them read
    left then right. Without a gutter, split into stacked bands at horizontal gaps. Returns leaf groups."""
    if len(lines) <= 1 or depth > 40: return [sorted(lines, key=lambda l: (l["top"], l["x0"]))]
    em = statistics.median(l["size"] for l in lines)
    normal = [l for l in lines if l["size"] <= em * 1.25] or lines
    x_lo, x_hi = min(l["x0"] for l in lines), max(l["x1"] for l in lines)
    best = None
    for a, b in gaps([(l["x0"], l["x1"]) for l in normal], x_lo, x_hi, max(6, em * 0.9)):
        left = [l for l in normal if l["x1"] <= a + 0.5]
        right = [l for l in normal if l["x0"] >= b - 0.5]
        lc, rc = sum(len(l["t"]) for l in left), sum(len(l["t"]) for l in right)
        if len(left) >= 2 and len(right) >= 2 and min(lc, rc) >= 40:
            if best is None or (b - a) > best[1] - best[0]: best = (a, b)
    if best:
        a, b = best
        mid = (a + b) / 2
        side = lambda l: "L" if l["x1"] <= b and (l["x0"] + l["x1"]) / 2 < mid else ("R" if l["x0"] >= a and (l["x0"] + l["x1"]) / 2 >= mid else "S")
        span = sorted([l for l in lines if side(l) == "S"], key=lambda l: l["top"])
        cols = [l for l in lines if side(l) != "S"]
        if not span:
            return xy_cut([l for l in cols if side(l) == "L"], depth + 1) + xy_cut([l for l in cols if side(l) == "R"], depth + 1)
        out, rest = [], cols
        for sp in span:
            above = [l for l in rest if (l["top"] + l["bot"]) / 2 < sp["top"]]
            rest = [l for l in rest if l not in above]
            if above: out += xy_cut(above, depth + 1)
            out.append([sp])
        if rest: out += xy_cut(rest, depth + 1)
        return out
    y_lo, y_hi = min(l["top"] for l in lines), max(l["bot"] for l in lines)
    heights = [l["bot"] - l["top"] for l in lines]
    lh = statistics.median(heights) if heights else em
    cuts = gaps([(l["top"], l["bot"]) for l in lines], y_lo, y_hi, max(3, lh * 0.9))
    if cuts:
        bands, edges = [], [y_lo - 1] + [(a + b) / 2 for a, b in cuts] + [y_hi + 1]
        for k in range(len(edges) - 1):
            band = [l for l in lines if edges[k] <= (l["top"] + l["bot"]) / 2 < edges[k + 1]]
            if band: bands.append(band)
        if len(bands) > 1:
            out = []
            for band in bands: out += xy_cut(band, depth + 1)
            return out
    return [sorted(lines, key=lambda l: (round(l["top"] / max(1, lh * 0.5)), l["x0"]))]


def page_rows(page):
    lines = to_lines(page["segs"])
    # sideways text in the margin (running titles printed vertically)
    lines = [l for l in lines if not ((l["bot"] - l["top"]) > max(3 * l["size"], 2.5 * (l["x1"] - l["x0"])))]
    if not lines: return []
    rows = []
    for group in xy_cut(lines):
        # new column or block: break the paragraph unless the sentence plainly runs on into it
        if rows and rows[-1][0]:
            runs_on = not re.search(r"[.!?:;\"”’)]$", rows[-1][0].strip()) and re.match(r"[a-z(]", group[0]["t"].strip())
            if not runs_on: rows.append(["", 0, False])
        prev = None
        for l in group:
            if prev is not None:
                lh = max(prev["bot"] - prev["top"], 1)
                if l["top"] - prev["bot"] > lh * 0.6: rows.append(["", 0, False])   # visible gap → new paragraph
            row = [l["t"], l["size"], l["bold"]]
            if page.get("ocr"): row.append(True)
            rows.append(row); prev = l
    return rows


# ---------- quality ----------
def body_text(md):
    return re.sub(r"\s+", " ", re.sub(r"^#+\s|^[-*]\s|^\d+[.)]\s", "", md, flags=re.M)).strip()


def score(md):
    """Lower is better: count reading-order symptoms."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", md) if p.strip()]
    broken = 0
    for a, b in zip(paras, paras[1:]):
        if a.startswith("#") or b.startswith("#"): continue
        if re.search(r"[a-z,;]$", a) and re.match(r"[a-z]", b): broken += 1             # sentence split across blocks
    nums = [int(m.group(1)) for m in re.finditer(r"^(\d{1,2})[.)]\s", md, re.M)]
    backwards = sum(1 for a, b in zip(nums, nums[1:]) if b < a and b != 1)
    midword = len(re.findall(r"\b[a-z]{1,3} [a-z]{1,2}\b(?= )", md)) * 0                 # (reserved)
    stray = len(re.findall(r"(?<=[a-z])[.!?] [a-z]", md))                                  # "…the race. f" style joins
    return broken * 3 + backwards * 4 + stray, dict(broken=broken, backwards=backwards, stray=stray)


TOKEN = re.compile(r"[a-z0-9’']+|[.,;:!?]")


def stream(md):
    """Running text as tokens: headings and list markers dropped, paragraphs joined."""
    text = "\n".join(l for l in md.split("\n") if not l.startswith("#"))
    text = re.sub(r"^\s*([-*]|\d{1,3}[.)])\s+", "", text, flags=re.M)
    return TOKEN.findall(text.lower().replace("'", "’"))


class Bigrams:
    """Word-pair model of the whole archive; used to tell fluent text from text spliced out of order."""
    def __init__(self, texts):
        from collections import Counter
        self.uni, self.bi = Counter(), Counter()
        for t in texts:
            toks = stream(t)
            self.uni.update(toks); self.bi.update(zip(toks, toks[1:]))
        self.n = sum(self.uni.values()); self.v = len(self.uni)

    def fluency(self, md, exclude=""):
        """Average log-probability per word pair; `exclude` (the article's current text) is taken out of the
        counts first so neither version gets credit for matching itself."""
        import math
        from collections import Counter
        ex = stream(exclude)
        eu, eb = Counter(ex), Counter(zip(ex, ex[1:]))
        toks = stream(md)
        if len(toks) < 2: return 0.0
        n = self.n - len(ex)
        tot = 0.0
        for a, b in zip(toks, toks[1:]):
            ub = max(0, self.uni[b] - eu[b]); ua = max(0, self.uni[a] - eu[a]); bab = max(0, self.bi[(a, b)] - eb[(a, b)])
            pb = (ub + 1) / (n + self.v)
            tot += math.log((bab + 2 * pb) / (ua + 2))
        return tot / (len(toks) - 1)


def words(md):
    return re.findall(r"[A-Za-z’']{3,}", md.lower())


def coverage(new, old):
    """Share of the old article's distinct words that also appear in the new text."""
    ow, nw = set(words(old)), set(words(new))
    return len(ow & nw) / max(1, len(ow))


def strip_title(md, title):
    lines = md.strip().split("\n")
    while lines and (lines[0].startswith("# ") or not lines[0].strip()):
        if lines[0].startswith("# ") and not re.sub(r"\W", "", lines[0][2:].lower()) in re.sub(r"\W", "", title.lower()) + "xx":
            break
        lines.pop(0)
    return "\n".join(lines).strip() + "\n"


# ---------- main ----------
def main():
    jobs = []
    for topic in sorted(os.listdir(ART)):
        d = os.path.join(ART, topic)
        if not os.path.isdir(d): continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".md") or (ONLY and f[:-3] not in ONLY): continue
            text = open(os.path.join(d, f), encoding="utf-8").read()
            m = re.match(r"---\n(.*?)\n---\n", text, re.S)
            meta = {k: json.loads(v) for k, _, v in (l.partition(": ") for l in m.group(1).split("\n"))}
            if not meta["source"].lower().endswith(".pdf"): continue
            jobs.append((topic, f, meta, text[:m.end()], text[m.end():]))
    os.makedirs(LAYOUT, exist_ok=True)
    todo = [j for j in jobs if not os.path.exists(os.path.join(LAYOUT, f"{j[0]}__{j[1][:-3]}.json"))]
    if todo:
        tool = os.path.join(CACHE, "layout_extract")
        if not os.path.exists(tool):
            subprocess.run(["swiftc", "-O", os.path.join(ROOT, "_tools", "layout_extract.swift"), "-o", tool], check=True)
        lst = os.path.join(CACHE, "layout_jobs.txt")
        with open(lst, "w") as fh:
            fh.write("\n".join(f"{os.path.join(ASSETS, j[2]['source'])}\t{j[0]}__{j[1][:-3]}" for j in todo))
        subprocess.run([tool, lst, LAYOUT], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    import clean_articles as CLEAN
    sys.argv = [sys.argv[0], "--dry"]                                    # clean_articles only reads its flag at import
    fresh = {}
    for topic, f, meta, head, old in jobs:
        p = os.path.join(LAYOUT, f"{topic}__{f[:-3]}.json")
        if not os.path.exists(p): continue
        data = json.load(open(p))
        rec = {"pages": [page_rows(pg) for pg in data["pages"]], "ocrPages": sum(1 for pg in data["pages"] if pg.get("ocr"))}
        md, _ = MD.convert_pdf(rec)
        if md: fresh[f] = CLEAN.clean_body(strip_title(md, meta["title"]), meta)

    # fluency model from both versions of every article; each article is scored with both of its own versions left out
    all_md = [j[4] for j in jobs] + list(fresh.values())
    all_md += [open(os.path.join(ART, t, x), encoding="utf-8").read().split("\n---\n", 1)[1]
               for t in os.listdir(ART) if os.path.isdir(os.path.join(ART, t))
               for x in os.listdir(os.path.join(ART, t)) if x.endswith(".md") and x not in {j[1] for j in jobs}]
    model = Bigrams(all_md)
    report, wins = [], 0
    for topic, f, meta, head, old in jobs:
        new = fresh.get(f)
        if not new: report.append((f, "no extraction", 0)); continue
        both = old + "\n\n" + new
        fo, fn = model.fluency(old, both), model.fluency(new, both)
        cov = coverage(new, old)
        ratio = len(words(new)) / max(1, len(words(old)))
        bo, bn = score(old)[1]["backwards"], score(new)[1]["backwards"]
        # better: reads more naturally, or puts numbered points back in order without reading noticeably worse
        better = (fn > fo + 0.002 or (bn < bo and fn > fo - 0.03)) and bn <= bo and cov >= 0.97 and 0.9 <= ratio <= 1.2
        if SHOW: print(f"\n===== {f}  fluency old {fo:.4f} new {fn:.4f}  cov {cov:.3f} ratio {ratio:.2f}  {'NEW' if better else 'keep'}\n{new[:6000]}")
        report.append((f, f"fluency old {fo:.4f} new {fn:.4f} ({fn - fo:+.4f})  cov {cov:.3f}  words {ratio:.2f}  {'→ NEW' if better else ''}", fn - fo))
        if better:
            wins += 1
            if not DRY:
                n_words = len(re.findall(r"[A-Za-z0-9’']+", new))
                head2 = re.sub(r"^words: \d+$", "words: %d" % n_words, head, flags=re.M)
                open(os.path.join(ART, topic, f), "w", encoding="utf-8").write(head2 + "\n" + new)
    if not SHOW:
        for f, r, _ in sorted(report, key=lambda x: x[2]): print(f"{f[:58]:58} {r}")
    print(f"\n{wins} of {len(jobs)} PDF articles {'would be' if DRY else 'were'} replaced with the re-extracted text")


if __name__ == "__main__":
    main()
