/* Article pages: keep "On this page" usable while reading.
   - --stick-top follows the real header height (taller on phones, where the header has a search row)
   - the bar shows the section being read; the matching entry is highlighted (bar and wide-screen sidebar)
   - choosing a section, tapping outside, or Escape closes the drop-down */
(function () {
  var root = document.documentElement, bar = document.querySelector(".bar");
  var toc = document.querySelector("details.toc");
  var links = [].slice.call(document.querySelectorAll(".toc a, .toc-side a"));
  function stickTop() { return bar ? bar.getBoundingClientRect().height : 0; }
  function setTop() { root.style.setProperty("--stick-top", stickTop() + "px"); }
  setTop();
  window.addEventListener("resize", setTop);
  if (!links.length) return;

  var current = toc && toc.querySelector(".toc-current");
  var heads = [], names = {};
  links.forEach(function (a) {
    var id = decodeURIComponent(a.getAttribute("href").slice(1)), h = document.getElementById(id);
    if (h && heads.indexOf(h) === -1) { heads.push(h); names[id] = a.textContent; }
  });
  heads.sort(function (a, b) { return a.compareDocumentPosition(b) & 4 ? -1 : 1; });

  var ticking = false;
  function update() {
    ticking = false;
    var line = stickTop() + (toc ? toc.offsetHeight : 0) + 24, active = null;
    for (var i = 0; i < heads.length; i++) {
      if (heads[i].getBoundingClientRect().top - line <= 0) active = heads[i]; else break;
    }
    links.forEach(function (a) { a.classList.toggle("on", !!active && a.getAttribute("href") === "#" + active.id); });
    if (toc) {
      var stuck = window.scrollY > 0 && toc.getBoundingClientRect().top <= stickTop() + 1;
      toc.classList.toggle("stuck", stuck);
      if (current) current.textContent = active ? names[active.id] : "";
      toc.classList.toggle("has-current", !!active);
    }
  }
  window.addEventListener("scroll", function () { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
  window.addEventListener("resize", update);
  update();

  if (!toc) return;
  toc.addEventListener("click", function (e) { if (e.target.closest("a")) toc.open = false; });
  document.addEventListener("click", function (e) { if (toc.open && !toc.contains(e.target)) toc.open = false; });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && toc.open) { toc.open = false; toc.querySelector("summary").focus(); } });
})();
