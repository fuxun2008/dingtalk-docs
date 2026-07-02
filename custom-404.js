/* ============================================================
   DingTalk Help Center — 404 enhancements
   - Loaded site-wide by Mintlify (auto-includes any root .js;
     runs on every page after it is interactive).
   - Two jobs, both scoped to the 404 page ONLY (never the .dt-home
     landing pages, which are also custom mode, nor normal doc pages),
     re-evaluated on SPA route changes so nothing leaks across pages:
       1. Tag <html> with `dt-404` so style.css can re-show the real
          #navbar (top bar + product tabs), which custom mode hides,
          and cap the over-tall gradient that made the short 404 scroll.
       2. Expand the framing sentence in #error-description to invite
          the reader to the suggestions below. We only swap that one
          sentence text node — the recommended links themselves are
          Mintlify's own native suggestions, left untouched (we no
          longer inject our own list, which duplicated them).
   ============================================================ */
(function () {
  if (typeof document === "undefined") return;

  var CLS = "dt-404";

  // Localized framing sentence for the description block.
  var SENTENCE = {
    en: "We couldn't find the page. Maybe you were looking for one of these pages below?",
    zh: "找不到该页面。也许您想找的是以下页面之一？",
    ja: "ページが見つかりませんでした。お探しのページは以下のいずれかではありませんか？",
  };

  function detectLang() {
    var p = location.pathname;
    if (p.indexOf("/zh/") === 0 || p === "/zh") return "zh";
    if (p.indexOf("/ja/") === 0 || p === "/ja") return "ja";
    return "en";
  }

  // The 404 page always shows a big language-independent "404" number
  // inside <main>; landing pages carry .dt-home; doc pages are not in
  // custom mode. Require all three signals to avoid false positives.
  function is404() {
    if (document.querySelector(".dt-home")) return false;
    if (document.documentElement.getAttribute("data-page-mode") !== "custom") return false;
    var main = document.querySelector("main");
    if (!main) return false;
    var nodes = main.querySelectorAll("*");
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (el.children.length === 0 && el.textContent.trim() === "404") return true;
    }
    return false;
  }

  // Swap ONLY the framing sentence — the first text node in
  // #error-description that isn't inside a suggestion link — so
  // Mintlify's native recommended links stay intact and nothing
  // flickers. Idempotent: skips once our sentence is in place.
  function enhanceDescription(lang) {
    var desc = document.getElementById("error-description");
    if (!desc) return;
    var sentence = SENTENCE[lang] || SENTENCE.en;

    var walker = document.createTreeWalker(desc, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        if (!n.nodeValue || !n.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
        if (n.parentElement && n.parentElement.closest("a")) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    var node = walker.nextNode();
    if (!node) return;
    if (node.nodeValue.trim() === sentence) return;
    node.nodeValue = sentence;
  }

  function sync() {
    var on = is404();
    var has = document.documentElement.classList.contains(CLS);
    if (on) {
      if (!has) document.documentElement.classList.add(CLS);
      enhanceDescription(detectLang());
    } else if (has) {
      document.documentElement.classList.remove(CLS);
    }
  }

  // Re-check on client-side navigation (Mintlify is a Next.js SPA):
  // patch the history API and debounce a MutationObserver that catches
  // the async content swap.
  function schedule() {
    if (schedule._t) return;
    schedule._t = setTimeout(function () {
      schedule._t = null;
      sync();
    }, 60);
  }

  ["pushState", "replaceState"].forEach(function (m) {
    var orig = history[m];
    if (typeof orig !== "function") return;
    history[m] = function () {
      var r = orig.apply(this, arguments);
      schedule();
      return r;
    };
  });
  window.addEventListener("popstate", schedule);

  var obs = new MutationObserver(schedule);
  obs.observe(document.body, { childList: true, subtree: true });

  sync();
})();
