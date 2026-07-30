/* ============================================================
   DingTalk Help Center — Embed / share mode
   - Loaded site-wide by Mintlify (auto-includes any root .js;
     runs on every page after it is interactive).
   - Turns any page into a frameless share view when the URL carries
     `?embed` (or `?share`). Tags <html> with `dt-embed` so custom.css
     can hide the whole chrome (navbar, sidebar, table of contents,
     footer), leaving just the article — meant for sharing a single
     doc to a customer via a clean link.
   - Re-evaluated on SPA route changes (Mintlify is a Next.js SPA) and
     the flag is carried onto same-origin link clicks, so browsing
     inside a shared page stays frameless.
   - JS only tags <html>; the actual hiding lives in custom.css.
   ============================================================ */
(function () {
  if (typeof document === "undefined") return;

  var CLS = "dt-embed";
  var PARAMS = ["embed", "share"]; // any of these present → embed mode

  // Embed mode is on when the current URL carries one of PARAMS.
  function wantsEmbed() {
    var q = new URLSearchParams(location.search);
    for (var i = 0; i < PARAMS.length; i++) {
      if (q.has(PARAMS[i])) return true;
    }
    return false;
  }

  function sync() {
    var on = wantsEmbed();
    var has = document.documentElement.classList.contains(CLS);
    if (on && !has) document.documentElement.classList.add(CLS);
    else if (!on && has) document.documentElement.classList.remove(CLS);
  }

  // Carry the embed flag onto same-origin navigations so a shared page
  // stays frameless as the reader clicks around. Mintlify is a Next.js
  // SPA whose <Link> targets are fixed at render time from React props,
  // so rewriting the DOM href does NOT change where the router goes.
  // Instead cancel the SPA navigation and do a full location.assign to
  // the param-preserving URL (same reliable pattern as custom-404.js).
  // Scoped to same-origin path links; skips hashes, external hosts,
  // modified clicks, and non-http protocols.
  function onClick(e) {
    if (!document.documentElement.classList.contains(CLS)) return;
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
    if (!a) return;
    if (a.target && a.target !== "_self") return; // let new-tab links open normally
    var raw = a.getAttribute("href");
    if (!raw || raw.charAt(0) === "#") return;
    var url;
    try {
      url = new URL(raw, location.href);
    } catch (_) {
      return;
    }
    if (url.origin !== location.origin) return;
    if (url.protocol !== "http:" && url.protocol !== "https:") return;
    // Already carries an embed param? let the SPA handle it normally.
    if (PARAMS.some(function (p) { return url.searchParams.has(p); })) return;
    url.searchParams.set(PARAMS[0], "1");
    e.preventDefault();
    e.stopPropagation();
    location.assign(url.pathname + "?" + url.searchParams.toString() + url.hash);
  }

  // Re-check on client-side navigation: patch the history API and
  // debounce a MutationObserver that catches the async content swap.
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
  document.addEventListener("click", onClick, true);

  var obs = new MutationObserver(schedule);
  obs.observe(document.documentElement, { childList: true, subtree: true });

  sync();
})();
