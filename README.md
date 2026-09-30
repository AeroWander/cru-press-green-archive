# Cru Press Green Archive

A mobile-friendly website for the article collection: 638 articles, guides and studies, organised by topic and fully searchable. It is plain static HTML, so any web host can serve it.

## Folders

| Folder | What it is |
|---|---|
| `articles/<topic>/<slug>.md` | **The articles.** One Markdown file each, filed by topic, with front matter (title, themes, audience, authors, series, summary…). This is the copy to edit. |
| `site/` | **The website** built from `articles/`. Upload this folder to publish. Don't edit it by hand; it is rebuilt each time. |
| `_tools/build.py` | Builds `site/` from `articles/`. |
| `_tools/reextract.py`, `_tools/layout_extract.swift` | Re-reads the source PDFs column by column and keeps whichever version of each article reads better. Already run; needs the PDFs in `Resource App/Assets`. |
| `_tools/clean_articles.py` | Tidies article text left messy by the PDF conversion (footers, broken lists, fake headings). Already run; safe to run again after adding articles. |
| `_tools/assets/` | Site design and behaviour: `style.css`, `app.js` (search), `home.html` (home page layout). |
| `_tools/import_articles.py` | One-time import from `Resource App/Asset Text/`. It already ran. Running it again **wipes `articles/`**. |

## Topics

| Folder | Topic | Archive themes it covers |
|---|---|---|
| `evangelism` | Evangelism & Outreach | personal evangelism, evangelism tools, outreach events, apologetics |
| `discipleship` | Discipleship & Spiritual Growth | follow-up, spiritual disciplines, prayer, Holy Spirit, multiplication, gospel-centred living |
| `bible-and-theology` | Bible & Theology | Bible study, knowing God & doctrine, assurance & grace, revival |
| `small-groups` | Small Groups & Community | small groups, weekly meetings, community, conferences & retreats |
| `leadership` | Leadership & Movement Building | launching ministries, vision & planning, team leadership, movement growth, character, evaluation, fundraising |
| `life-and-character` | Life, Identity & Character | identity, sexual purity, dating & marriage, suffering, conflict, calling, life after college |
| `mission-and-justice` | Mission, Justice & Culture | missions, justice & compassion, ethnic ministry, summer projects |
| `flyers-and-promo` | Flyers, Posters & Promo | poster and flyer copy |

Each article is filed under the topic of its first theme and also appears under the topics of its other themes.

## Import changes

- 702 source files became 638 articles. Duplicate copies of the same text (for example, the same Transferable Concept filed in two folders) were merged. The other locations are listed in `also_filed`.
- Files were renamed from their titles (`How To Pray With Confidence.pdf` → `discipleship/how-to-pray-with-confidence.md`). The original path is kept in `source`.
- Generic titles were fixed ("Postcards from Corinth • Chapter Excerpt", "Instructions", "power power").

## Search on the site

- **Keywords** match titles, summaries, section headings, themes, authors, series and audience. Every word must match. Plurals are handled ("groups" finds "group").
- `"exact phrase"` in quotes, and `-word` to exclude.
- **Also search inside article text** searches the full text of every article and shows the matching passage. It downloads about 3.5 MB (compressed) the first time it is switched on.
- **Filters:** topic, theme, audience, author, series, length (quick / medium / long) and type (articles / handouts / flyers).
- **Sorting:** best match, A–Z, shortest or longest.
- Every search is saved in the address bar, so a link like `index.html#theme=Prayer` or `#author=Rick%20James` can be bookmarked or shared. Themes, authors and series on article pages link back to these filtered lists.

## Editing and rebuilding

1. Edit or add a file in `articles/<topic>/`. Copy the front matter from an existing article. `title`, `topic`, `type`, `themes`, `audience`, `words` and `summary` are required.
2. To move an article to another topic, move its file into that topic's folder.
3. The "On this page" box is built from each article's headings. Headings that look like conversion debris are left out automatically. If an article's box still looks wrong, add `toc: false` to its front matter to hide it.
4. Rebuild:

```bash
python3 _tools/build.py
```

Only Python 3 is needed. There are no packages to install.

## Previewing

```bash
python3 -m http.server 8793 -d site
```

Then open http://localhost:8793. Opening `site/index.html` directly also works.

## Publishing

Live site: **https://aerowander.github.io/cru-press-green-archive/**
Repository: https://github.com/AeroWander/cru-press-green-archive (public)

After editing articles, rebuild and publish in one step:

```bash
_tools/publish.sh
```

The script builds `site/` and pushes it to the repo's `gh-pages` branch, which GitHub Pages serves. The site updates a minute or two later. To save your article edits in the repo too, commit and push `main` as usual.
