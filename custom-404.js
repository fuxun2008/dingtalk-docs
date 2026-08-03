/* ============================================================
   DingTalk Help Center — 404 enhancements
   - Loaded site-wide by Mintlify (auto-includes any root .js;
     runs on every page after it is interactive).
   - Scoped to the 404 page ONLY (never the .dt-home landing pages,
     which are also custom mode, nor normal doc pages), re-evaluated
     on SPA route changes so nothing leaks across pages:
       1. Tag <html> with `dt-404` so style.css can re-show the real
          #navbar (top bar + product tabs), which custom mode hides,
          and cap the over-tall gradient that made the short 404 scroll.
       2. Expand the framing sentence in #error-description (locale-aware).
          The recommended links themselves are Mintlify's own native
          suggestions, left untouched.
       3. Localize the chrome on a zh/ja/id 404. Mintlify renders the 404
          in the DEFAULT (English) locale regardless of the /zh//ja//id/ URL
          prefix, so the navbar tabs, the language selector, the product
          menu and the "Page Not Found" title all come out English on a
          localized URL. Rewrite those labels to the current locale, and
          route navbar-tab clicks to the /zh//ja//id/-prefixed page so a
          localized tab never lands on an English doc. (Recommendation
          links stay Mintlify-native English by design.)
   ============================================================ */
(function () {
  if (typeof document === "undefined") return;

  var CLS = "dt-404";

  // Localized framing sentence for the description block.
  var SENTENCE = {
    en: "We couldn't find the page. Maybe you were looking for one of these pages below?",
    zh: "找不到该页面。也许您想找的是以下页面之一？",
    ja: "ページが見つかりませんでした。お探しのページは以下のいずれかではありませんか？",
    id: "Kami tidak dapat menemukan halaman tersebut. Mungkin Anda mencari salah satu halaman di bawah ini?",
  };

  // Localized "Page Not Found" title.
  var HEADING = { zh: "页面未找到", ja: "ページが見つかりません", id: "Halaman tidak ditemukan" };

  // Navbar label overrides, keyed by the English text Mintlify renders.
  // Covers the 11 Help Docs product tabs + the 3 Developer Docs tabs +
  // both product-menu names + the language selector's current value +
  // the Download CTA. Keys must match the EN labels docs.json renders
  // (Mintlify draws the 404 chrome in the default en locale). Order-
  // independent (matched by text).
  var NAV_LABELS = {
    Chats: { zh: "消息", ja: "メッセージ", id: "Pesan" },
    Calendar: { zh: "日历", ja: "カレンダー", id: "Kalender" },
    Meetings: { zh: "会议", ja: "会議", id: "Rapat" },
    Contacts: { zh: "通讯录", ja: "連絡先", id: "Kontak" },
    Mail: { zh: "邮箱", ja: "メール", id: "Email" },
    Docs: { zh: "文档", ja: "ドキュメント", id: "Dokumen" },
    Drive: { zh: "钉盘", ja: "ドライブ", id: "Drive" },
    "AI Table": { zh: "AI 表格", ja: "AI テーブル", id: "AI Table" },
    "AI Minutes": { zh: "AI 听记", ja: "AI 議事録", id: "AI Minutes" },
    Attendance: { zh: "考勤", ja: "勤怠", id: "Absensi" },
    Approval: { zh: "审批", ja: "承認", id: "Persetujuan" },
    YiDA: { zh: "宜搭", ja: "YiDA", id: "YiDA" },
    "Admin Console": { zh: "管理控制台", ja: "管理コンソール", id: "Konsol Admin" },
    "Developer Guide": { zh: "开发指南", ja: "開発ガイド", id: "Panduan pengembang" },
    "Server API": { zh: "服务端 API", ja: "サーバー API", id: "Server API" },
    "YiDA API": { zh: "宜搭 API", ja: "YiDA API", id: "YiDA API" },
    "Help Docs": { zh: "帮助文档", ja: "ヘルプドキュメント", id: "Pusat Bantuan" },
    "Developer Docs": { zh: "开发文档", ja: "開発ドキュメント", id: "Platform Terbuka" },
    English: { zh: "中文", ja: "日本語", id: "Bahasa Indonesia" },
    Download: { zh: "下载", ja: "ダウンロード", id: "Unduh" },
  };

  // First path segment of every product tab — used to spot a navbar-tab
  // click that must be re-pointed at the localized page.
  var TAB_ROOTS = {
    im: 1, calendar: 1, meetings: 1, contacts: 1, mail: 1,
    docs: 1, drive: 1, aitable: 1, "ai-minutes": 1,
    attendance: 1, approval: 1, yida: 1,
    oa: 1, open: 1,
  };

  function detectLang() {
    var p = location.pathname;
    if (p.indexOf("/zh/") === 0 || p === "/zh") return "zh";
    if (p.indexOf("/ja/") === 0 || p === "/ja") return "ja";
    if (p.indexOf("/id/") === 0 || p === "/id") return "id";
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

  // Rewrite the English navbar labels + the title to `lang`. English 404
  // is left exactly as Mintlify renders it. Matched by text so it's
  // independent of DOM nesting/order; idempotent once translated.
  function localizeChrome(lang) {
    if (lang === "en") return;

    var nav = document.getElementById("navbar");
    if (nav) {
      var walker = document.createTreeWalker(nav, NodeFilter.SHOW_TEXT, {
        acceptNode: function (n) {
          var t = n.nodeValue && n.nodeValue.trim();
          return t && NAV_LABELS[t] && NAV_LABELS[t][lang]
            ? NodeFilter.FILTER_ACCEPT
            : NodeFilter.FILTER_REJECT;
        },
      });
      var pending = [], n;
      while ((n = walker.nextNode())) pending.push(n);
      pending.forEach(function (node) {
        node.nodeValue = NAV_LABELS[node.nodeValue.trim()][lang];
      });
    }

    var title = document.getElementById("error-title");
    if (title && HEADING[lang] && title.textContent.trim() !== HEADING[lang]) {
      title.textContent = HEADING[lang];
    }
  }

  // Capture-phase click router: on a localized 404, a navbar product-tab
  // link points at the English slug (/im/...); send it to the localized
  // page instead so the Chinese/Japanese label and destination agree.
  // Scoped hard to #navbar tabs, so recommendation links and normal
  // pages keep Mintlify's native behaviour.
  function onTabClick(e) {
    if (!document.documentElement.classList.contains(CLS)) return;
    var lang = detectLang();
    if (lang === "en") return;
    var a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
    if (!a || !a.closest("#navbar")) return;
    var url;
    try {
      url = new URL(a.getAttribute("href"), location.origin);
    } catch (_) {
      return;
    }
    if (url.origin !== location.origin) return;
    var segs = url.pathname.split("/").filter(Boolean);
    if (!segs.length || !TAB_ROOTS[segs[0]]) return; // not a product tab (or already prefixed)
    e.preventDefault();
    e.stopPropagation();
    location.assign("/" + lang + url.pathname + url.search + url.hash);
  }

  function sync() {
    var on = is404();
    var has = document.documentElement.classList.contains(CLS);
    if (on) {
      if (!has) document.documentElement.classList.add(CLS);
      var lang = detectLang();
      enhanceDescription(lang);
      localizeChrome(lang);
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
  document.addEventListener("click", onTabClick, true);

  var obs = new MutationObserver(schedule);
  obs.observe(document.body, { childList: true, subtree: true });

  sync();
})();
