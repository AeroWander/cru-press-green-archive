/* Cru Press Green Archive — search, filters and browse on the home page.
   Data: window.LIBRARY (assets/library.js); full text is loaded on demand from assets/fulltext.js.
   State lives in the URL hash (#q=…&topic=…) so searches can be bookmarked and shared. */
(function () {
  var L = window.LIBRARY, A = L.articles, T = {};
  L.topics.forEach(function (t) { T[t.id] = t; });
  var $ = function (id) { return document.getElementById(id); };
  var PAGE = 30, shown = PAGE, fullText = null, loadingFT = false;

  var el = {
    q: $("q"), clearQ: $("clear-q"), ft: $("ft"), ftStatus: $("ft-status"),
    topic: $("f-topic"), theme: $("f-theme"), aud: $("f-aud"), author: $("f-author"),
    series: $("f-series"), len: $("f-len"), type: $("f-type"), sort: $("f-sort"),
    filters: $("filters"), filterCount: $("filter-count"),
    section: $("results-section"), browse: $("browse"), title: $("res-title"), count: $("res-count"),
    active: $("active"), intro: $("topic-intro"), list: $("results"), more: $("more"), clearAll: $("clear-all")
  };
  var FILTERS = { topic: el.topic, theme: el.theme, aud: el.aud, author: el.author, series: el.series, len: el.len, type: el.type };
  var LABELS = { topic: "Topic", theme: "Theme", aud: "For", author: "Author", series: "Series", len: "Length", type: "Type" };

  // ---------- text helpers ----------
  function norm(s) {
    return (s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[\u2018\u2019]/g, "'").replace(/[\u201c\u201d]/g, '"').toLowerCase();
  }
  function escHtml(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function escRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
  function minutes(w) { return Math.max(1, Math.round(w / 230)); }

  // pre-normalised search fields
  A.forEach(function (a, i) {
    a.i = i;
    a.nt = norm(a.t); a.ns = norm(a.s); a.nh = norm(a.h);
    a.nm = norm([a.th.join(" "), a.by.join(" "), a.se, a.au.join(" "), T[a.tp].name, a.ty].join(" | "));
  });

  // Query language: words (all must match), "exact phrase", -exclude. Plural/singular tolerant.
  function parseQuery(q) {
    var terms = [], not = [], m, re = /(-?)"([^"]+)"|(-?)(\S+)/g;
    q = norm(q);
    while ((m = re.exec(q))) {
      var neg = m[1] || m[3], t = (m[2] || m[4] || "").replace(/^[^\w']+|[^\w']+$/g, "");
      if (!t || (t.length < 2 && !m[2])) continue;
      if (!m[2] && t.length > 3 && /s$/.test(t) && !/ss$/.test(t)) t = t.replace(/(ies|es|s)$/, function (x) { return x === "ies" ? "y" : x === "es" && /(ch|sh|x|z)es$/.test(t) ? "" : x === "es" ? "e" : ""; });
      (neg ? not : terms).push(t);
    }
    return { terms: terms, not: not };
  }
  function has(field, t) { return field.indexOf(t) !== -1; }
  function wordStart(field, t) { return new RegExp("(^|[^a-z0-9])" + escRe(t)).test(field); }

  function scoreArticle(a, Q, ft) {
    var score = 0, body = ft && fullText ? fullText.norm[a.i] : null;
    for (var n = 0; n < Q.not.length; n++) {
      var x = Q.not[n];
      if (has(a.nt, x) || has(a.ns, x) || has(a.nm, x) || (body && has(body, x))) return -1;
    }
    for (var k = 0; k < Q.terms.length; k++) {
      var t = Q.terms[k], s = 0;
      if (has(a.nt, t)) s += (wordStart(a.nt, t) ? 14 : 7) + 6 * t.length / a.nt.length;
      if (has(a.nm, t)) s += 6;
      if (has(a.ns, t)) s += wordStart(a.ns, t) ? 4 : 2;
      if (has(a.nh, t)) s += 3;
      if (body) {
        var c = 0, p = body.indexOf(t);
        while (p !== -1 && c < 50) { c++; p = body.indexOf(t, p + t.length); }
        if (c) s += 1 + Math.min(4, Math.log2(1 + c) * 1.2);
      }
      if (!s) return -1;
      score += s;
    }
    if (Q.terms.length > 1 && has(a.nt, Q.terms.join(" "))) score += 10;
    return score;
  }

  // ---------- state <-> URL ----------
  function readHash() {
    var p = new URLSearchParams(location.hash.slice(1)), st = {};
    ["q", "topic", "theme", "aud", "author", "series", "len", "type", "sort", "ft"].forEach(function (k) { st[k] = p.get(k) || ""; });
    return st;
  }
  function currentState() {
    var st = { q: el.q.value.trim(), sort: el.sort.value === "rel" ? "" : el.sort.value, ft: el.ft.checked ? "1" : "" };
    for (var k in FILTERS) st[k] = FILTERS[k].value;
    return st;
  }
  function writeHash(st, push) {
    var p = new URLSearchParams();
    for (var k in st) if (st[k]) p.set(k, st[k]);
    var h = p.toString(), url = location.pathname + location.search + (h ? "#" + h : "");
    if (url !== location.pathname + location.search + location.hash) history[push ? "pushState" : "replaceState"](null, "", url);
  }
  function applyState(st) {
    el.q.value = st.q;
    for (var k in FILTERS) {
      var sel = FILTERS[k];
      if (st[k] && !Array.prototype.some.call(sel.options, function (o) { return o.value === st[k]; })) {
        var o = document.createElement("option"); o.value = o.textContent = st[k]; sel.appendChild(o);
      }
      sel.value = st[k];
    }
    el.sort.value = st.sort || "rel";
    el.ft.checked = st.ft === "1";
  }

  // ---------- filter options ----------
  function counts(key) {
    var c = {};
    A.forEach(function (a) { [].concat(a[key] || []).forEach(function (v) { if (v) c[v] = (c[v] || 0) + 1; }); });
    return c;
  }
  function fillSelect(sel, items) {
    items.forEach(function (it) {
      var o = document.createElement("option"); o.value = it[0]; o.textContent = it[1]; sel.appendChild(o);
    });
  }
  function buildOptions() {
    fillSelect(el.topic, L.topics.map(function (t) { return [t.id, t.name]; }));
    var thc = counts("th");
    L.topics.forEach(function (t) {
      if (!t.themes.length) return;
      var g = document.createElement("optgroup"); g.label = t.name;
      t.themes.forEach(function (th) {
        var o = document.createElement("option"); o.value = th; o.textContent = th + " (" + (thc[th] || 0) + ")"; g.appendChild(o);
      });
      el.theme.appendChild(g);
    });
    var ac = counts("au");
    fillSelect(el.aud, Object.keys(ac).sort().map(function (k) { return [k, k + " (" + ac[k] + ")"]; }));
    var byc = counts("by"), authors = Object.keys(byc).sort(function (x, y) { return byc[y] - byc[x] || x.localeCompare(y); });
    fillSelect(el.author, authors.map(function (k) { return [k, k + " (" + byc[k] + ")"]; }));
    var sc = counts("se"), series = Object.keys(sc).sort();
    fillSelect(el.series, series.map(function (k) { return [k, k + " (" + sc[k] + ")"]; }));

    // browse lists
    var sl = $("series-list");
    series.filter(function (k) { return sc[k] > 1; }).sort(function (x, y) { return sc[y] - sc[x]; }).forEach(function (k) {
      sl.appendChild(pill(k, sc[k], { series: k }));
    });
    var al = $("author-list");
    authors.filter(function (k) { return byc[k] >= 3; }).forEach(function (k) { al.appendChild(pill(k, byc[k], { author: k })); });
  }
  function pill(label, n, st) {
    var b = document.createElement("button");
    b.type = "button"; b.innerHTML = escHtml(label) + "<small>" + n + "</small>";
    b.addEventListener("click", function () { go(st); });
    return b;
  }
  function go(partial) {
    var st = { q: "", topic: "", theme: "", aud: "", author: "", series: "", len: "", type: "", sort: "", ft: el.ft.checked ? "1" : "" };
    for (var k in partial) st[k] = partial[k];
    applyState(st); writeHash(currentState(), true); run(true);
  }

  // ---------- filtering ----------
  function passes(a, st) {
    if (st.topic && a.tp !== st.topic && a.at.indexOf(st.topic) === -1) return false;
    if (st.theme && a.th.indexOf(st.theme) === -1) return false;
    if (st.aud && a.au.indexOf(st.aud) === -1) return false;
    if (st.author && a.by.indexOf(st.author) === -1) return false;
    if (st.series && a.se !== st.series) return false;
    if (st.type && a.ty !== st.type) return false;
    if (st.len) {
      var m = minutes(a.w);
      if (st.len === "short" && m >= 5) return false;
      if (st.len === "medium" && (m < 5 || m >= 15)) return false;
      if (st.len === "long" && m < 15) return false;
    }
    return true;
  }

  // ---------- rendering ----------
  function highlight(text, terms) {
    var h = escHtml(text);
    if (!terms.length) return h;
    var re = new RegExp("(" + terms.map(function (t) { return escRe(escHtml(t)); }).sort(function (x, y) { return y.length - x.length; }).join("|") + ")", "gi");
    // match against an accent-folded copy so "cafe" finds "café"
    var folded = norm(h), out = "", last = 0, m;
    while ((m = re.exec(folded))) {
      if (!m[0].length) { re.lastIndex++; continue; }
      out += h.slice(last, m.index) + "<mark>" + h.slice(m.index, m.index + m[0].length) + "</mark>";
      last = m.index + m[0].length;
    }
    return out + h.slice(last);
  }
  function snippet(a, terms) {
    if (!fullText || !terms.length) return "";
    var raw = fullText.raw[a.i], body = fullText.norm[a.i], best = -1;
    for (var i = 0; i < terms.length; i++) {
      var p = body.indexOf(terms[i]);
      if (p !== -1 && (best === -1 || p < best)) best = p;
    }
    if (best === -1 || (has(a.ns, terms[0]) && best > 4000 && terms.length === 1)) return "";
    var start = Math.max(0, best - 90), end = Math.min(raw.length, best + 170);
    while (start > 0 && start > best - 130 && raw[start - 1] !== " ") start--;
    while (end < raw.length && end < best + 210 && raw[end] !== " ") end++;
    return (start > 0 ? "…" : "") + highlight(raw.slice(start, end).trim(), terms) + (end < raw.length ? "…" : "");
  }
  function resultHtml(a, terms) {
    var t = T[a.tp], by = a.by.length ? '<div class="r-by">By ' + highlight(a.by.join(", "), terms) + "</div>" : "";
    var snip = snippet(a, terms);
    var meta = [minutes(a.w) + " min read", a.w.toLocaleString() + " words"];
    if (a.se) meta.push("Series: " + escHtml(a.se));
    if (a.au.length) meta.push("For " + escHtml(a.au.join(", ").toLowerCase()));
    return '<li class="result" data-topic="' + a.tp + '"><a class="r-link" href="' + a.p + '">' +
      '<div class="r-top"><span class="r-topic">' + escHtml(t.name) + "</span>" + (a.ty !== "Article" ? '<span class="r-type">' + escHtml(a.ty) + "</span>" : "") + "</div>" +
      '<span class="r-title">' + highlight(a.t, terms) + "</span>" + by +
      '<p class="r-sum">' + highlight(a.s, terms) + "</p>" +
      (snip ? '<p class="r-snip"><b>In the text</b>' + snip + "</p>" : "") +
      '<div class="r-meta">' + meta.map(function (m) { return "<span>" + m + "</span>"; }).join("") + "</div></a></li>";
  }

  function run(scrollToResults) {
    var st = currentState(), Q = parseQuery(st.q);
    var active = Q.terms.length || Q.not.length;
    var nFilters = 0;
    for (var k in FILTERS) { var on = !!FILTERS[k].value; FILTERS[k].classList.toggle("on", on); if (on) nFilters++; }
    el.filterCount.hidden = !nFilters; el.filterCount.textContent = nFilters;
    el.clearQ.hidden = !st.q;

    document.body.classList.toggle("searching", !!(active || nFilters));
    if (!active && !nFilters) {
      el.section.hidden = true; el.browse.hidden = false;
      document.title = "Cru Press Green Archive";
      return;
    }
    el.section.hidden = false; el.browse.hidden = true;

    if (st.ft && !fullText) loadFullText();
    var res = [];
    A.forEach(function (a) {
      if (!passes(a, st)) return;
      var s = active ? scoreArticle(a, Q, st.ft) : 0;
      if (s >= 0) res.push({ a: a, s: s });
    });
    var sort = st.sort || (active ? "rel" : "az");
    res.sort(function (x, y) {
      if (sort === "rel" && y.s !== x.s) return y.s - x.s;
      if (sort === "short") return x.a.w - y.a.w;
      if (sort === "long") return y.a.w - x.a.w;
      return x.a.t.localeCompare(y.a.t);
    });

    // heading + counts
    var heading = st.q ? "Results for " + (/"/.test(st.q) ? st.q : "“" + st.q + "”") : st.topic && nFilters === 1 ? T[st.topic].name : st.series && nFilters === 1 ? st.series : st.author && nFilters === 1 ? "By " + st.author : st.theme && nFilters === 1 ? st.theme : "Filtered articles";
    el.title.textContent = heading;
    el.title.hidden = !!st.topic && heading === T[st.topic].name;  // the topic panel below already names it
    document.title = heading + " · Cru Press Green Archive";
    el.count.textContent = res.length === 1 ? "1 article" : res.length.toLocaleString() + " articles" + (st.ft && !fullText ? " · loading article text…" : "");

    // topic intro with theme shortcuts
    if (st.topic) {
      var t = T[st.topic];
      el.intro.hidden = false; el.intro.dataset.topic = t.id;
      el.intro.innerHTML = "<h3>" + escHtml(t.name) + "</h3><p>" + escHtml(t.blurb) + "</p>" +
        (t.themes.length ? '<div class="theme-pills">' + t.themes.map(function (th) {
          return '<button type="button" data-theme="' + escHtml(th) + '" class="' + (st.theme === th ? "on" : "") + '">' + escHtml(th) + "</button>";
        }).join("") + "</div>" : "");
    } else el.intro.hidden = true;

    // active filter chips
    var chips = [];
    if (st.q) chips.push(["q", "Search", st.q]);
    for (var f in FILTERS) if (st[f]) {
      var sel = FILTERS[f], txt = sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].textContent.replace(/\s\(\d+\)$/, "") : st[f];
      chips.push([f, LABELS[f], txt]);
    }
    el.active.innerHTML = chips.map(function (c) {
      return '<button type="button" data-clear="' + c[0] + '" aria-label="Remove ' + escHtml(c[1] + ": " + c[2]) + '"><small>' + escHtml(c[1]) + "</small>" + escHtml(c[2]) + "<span>×</span></button>";
    }).join("");

    var terms = Q.terms;
    if (!res.length) {
      el.list.innerHTML = '<li class="empty">No articles match. Try fewer words, remove a filter' + (st.ft ? "" : ", or turn on <b>Also search inside article text</b>") + ".</li>";
    } else {
      el.list.innerHTML = res.slice(0, shown).map(function (r) { return resultHtml(r.a, terms); }).join("");
    }
    el.more.hidden = res.length <= shown;
    el.more.textContent = "Show more (" + (res.length - shown) + " left)";
    if (scrollToResults) scrollToEl(el.section);
  }

  function scrollToEl(node) {
    requestAnimationFrame(function () { window.scrollTo(0, Math.max(0, node.getBoundingClientRect().top + window.scrollY - 64)); });
  }

  function loadFullText() {
    if (loadingFT) return;
    loadingFT = true;
    el.ftStatus.textContent = "Loading article text…";
    var s = document.createElement("script");
    s.src = "assets/fulltext.js" + ((document.querySelector('script[src*="app.js?v="]') || {}).src || "").replace(/^[^?]*/, "");
    s.onload = function () {
      fullText = { raw: window.FULLTEXT, norm: window.FULLTEXT.map(norm) };
      el.ftStatus.textContent = "Searching inside all " + A.length + " articles";
      run(false);
    };
    s.onerror = function () { el.ftStatus.textContent = "Couldn't load article text"; loadingFT = false; };
    document.head.appendChild(s);
  }

  // ---------- events ----------
  var timer;
  el.q.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(function () { shown = PAGE; writeHash(currentState(), false); run(false); }, 140);
  });
  el.q.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); el.q.blur(); if (!el.section.hidden) scrollToEl(el.section); }
    if (e.key === "Escape") { el.q.value = ""; writeHash(currentState(), false); run(false); }
  });
  el.clearQ.addEventListener("click", function () { el.q.value = ""; el.q.focus(); shown = PAGE; writeHash(currentState(), false); run(false); });
  el.ft.addEventListener("change", function () {
    if (el.ft.checked && !fullText) loadFullText();
    if (!el.ft.checked) el.ftStatus.textContent = "";
    writeHash(currentState(), false); run(false);
  });
  Object.keys(FILTERS).concat(["sort"]).forEach(function (k) {
    (FILTERS[k] || el.sort).addEventListener("change", function () {
      if (k === "topic" && el.theme.value) {
        var th = el.theme.value, t = T[el.topic.value];
        if (t && t.themes.indexOf(th) === -1) el.theme.value = "";
      }
      shown = PAGE; writeHash(currentState(), true); run(false);
    });
  });
  el.more.addEventListener("click", function () { shown += PAGE; run(false); });
  el.clearAll.addEventListener("click", function () { go({}); el.q.focus(); });
  el.active.addEventListener("click", function (e) {
    var b = e.target.closest("[data-clear]"); if (!b) return;
    var k = b.dataset.clear;
    if (k === "q") el.q.value = ""; else FILTERS[k].value = "";
    shown = PAGE; writeHash(currentState(), true); run(false);
  });
  el.intro.addEventListener("click", function (e) {
    var b = e.target.closest("[data-theme]"); if (!b) return;
    el.theme.value = el.theme.value === b.dataset.theme ? "" : b.dataset.theme;
    shown = PAGE; writeHash(currentState(), true); run(false);
  });
  document.querySelectorAll("[data-try]").forEach(function (b) {
    b.addEventListener("click", function () { el.q.value = b.dataset.try; shown = PAGE; writeHash(currentState(), true); run(true); });
  });
  document.querySelectorAll(".topic-card").forEach(function (c) {
    c.addEventListener("click", function (e) { e.preventDefault(); go({ topic: c.dataset.topic }); });
  });
  window.addEventListener("hashchange", function () {
    var h = location.hash.slice(1);
    if (h === "browse" || h === "search") {
      go({});
      if (h === "search") { el.q.focus(); } else scrollToEl(el.browse);
      return;
    }
    applyState(readHash()); shown = PAGE; run(false);
  });
  window.addEventListener("popstate", function () { applyState(readHash()); run(false); });

  // desktop: filters open by default; phones: collapsed
  if (window.matchMedia("(min-width: 900px)").matches) el.filters.open = true;

  buildOptions();
  var h0 = location.hash.slice(1);
  if (h0 === "search") { setTimeout(function () { el.q.focus(); }, 50); }
  else if (h0 && h0 !== "browse") { applyState(readHash()); if (el.ft.checked) loadFullText(); run(true); }
  if (h0 === "browse") scrollToEl(el.browse);
})();
