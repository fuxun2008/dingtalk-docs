/* ============================================================
   DingTalk Help Center — 404 enhancements
   - Loaded site-wide by Mintlify (auto-includes any root .js;
     runs on every page after it is interactive).
   - Two jobs, both scoped to the 404 page ONLY (never the .dt-home
     landing pages, which are also custom mode, nor normal doc pages),
     re-evaluated on SPA route changes so nothing leaks across pages:
       1. Tag <html> with `dt-404` so style.css can re-show the real
          #navbar (top bar + product tabs), which custom mode hides.
       2. Rewrite the #error-description block with a fixed message +
          3 random recommended docs (relative, locale-aware paths).
   - The over-tall gradient decoration that made the short 404 scroll
     is capped in style.css (html.dt-404 rule), not here.
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

  // Recommendation pool — pages that exist and are translated in all
  // three languages. `path` is the locale-less slug; the current locale
  // prefix is prepended at render time. Labels are per-language.
  var POOL = [
    { path: "aitable/getting-started/quick-start",
      t: { en: "AI Table Quick Start", zh: "AI 表格快速上手", ja: "AI テーブル クイックスタート" } },
    { path: "aitable/getting-started/import-excel",
      t: { en: "Import Excel into AI Table", zh: "将 Excel 导入 AI 表格", ja: "Excel を AI テーブルへインポート" } },
    { path: "aitable/getting-started/keyboard-shortcuts",
      t: { en: "Keyboard shortcuts", zh: "使用快捷键", ja: "ショートカットキーの利用" } },
    { path: "docs/getting-started/intro-docs",
      t: { en: "DingTalk Docs", zh: "钉钉文档", ja: "DingTalk ドキュメント" } },
    { path: "docs/getting-started/intro-sheets",
      t: { en: "DingTalk Sheets", zh: "钉钉表格", ja: "スプレッドシート" } },
    { path: "docs/getting-started/intro-mind",
      t: { en: "DingTalk Mind", zh: "钉钉脑图", ja: "DingTalk Mind" } },
    { path: "docs/getting-started/intro-whiteboard",
      t: { en: "DingTalk Whiteboard", zh: "钉钉白板", ja: "DingTalk Whiteboard" } },
    { path: "docs/getting-started/intro-knowledge-base",
      t: { en: "Knowledge Base", zh: "知识库", ja: "ナレッジベース" } },
    { path: "docs/getting-started/intro-ai-table",
      t: { en: "AI Table", zh: "钉钉 AI 表格", ja: "AI テーブル" } },
  ];

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

  function pickThree() {
    var a = POOL.slice();
    for (var i = a.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var tmp = a[i]; a[i] = a[j]; a[j] = tmp;
    }
    return a.slice(0, 3);
  }

  // Replace Mintlify's #error-description (short in dev, sentence +
  // its own suggested links in prod) with our sentence + 3 recs, so
  // the result is identical everywhere and never duplicated.
  function enhanceDescription(lang) {
    var desc = document.getElementById("error-description");
    if (!desc || desc.querySelector(".dt-404-links")) return;

    desc.textContent = "";

    var p = document.createElement("p");
    p.className = "dt-404-desc";
    p.textContent = SENTENCE[lang] || SENTENCE.en;
    desc.appendChild(p);

    var prefix = lang === "en" ? "/" : "/" + lang + "/";
    var list = document.createElement("div");
    list.className = "dt-404-links";
    pickThree().forEach(function (item) {
      var a = document.createElement("a");
      a.className = "dt-404-link";
      a.href = prefix + item.path;
      a.textContent = item.t[lang] || item.t.en;
      list.appendChild(a);
    });
    desc.appendChild(list);
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
