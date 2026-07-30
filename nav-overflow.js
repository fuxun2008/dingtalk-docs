/* ============================================================
   DingTalk Help Center — navbar tab overflow menu（「更多 ▾」）
   - Mintlify 自动加载根目录 .js，全站生效、页面可交互后运行。
   - 顶部产品 tab 行随子产品增多 + 长本地化名（如日语「管理コンソール」）
     会溢出被 max-w-8xl(1440) 容器裁掉。本脚本把放不下的 tab 收进右侧
     「更多 ▾」下拉：宽屏自动多显示、窄屏自动多收纳，任意数量/语言都不溢出。
   - 只作用于桌面（lg+）doc 页的真实 tab 行 `.nav-tabs`；自定义首页/404
     的 #navbar 被隐藏（clientWidth 0）时自动跳过。
   - Mintlify 是 Next.js SPA：patch history + MutationObserver 兜住路由切换
     后的 DOM 重建；ResizeObserver 兜住视口缩放。布局期间断开 MutationObserver
     防止自身改动触发无限回环。所有改动幂等。
   ============================================================ */
(function () {
  if (typeof document === "undefined") return;

  var MORE_LABEL = { en: "More", zh: "更多", ja: "その他", id: "Lainnya" };

  function detectLang() {
    var p = location.pathname;
    if (p.indexOf("/zh/") === 0 || p === "/zh") return "zh";
    if (p.indexOf("/ja/") === 0 || p === "/ja") return "ja";
    if (p.indexOf("/id/") === 0 || p === "/id") return "id";
    return "en";
  }

  var moreEl = null; // the persistent「更多」element (re-appended if Mintlify wipes it)

  // Build the「更多 ▾」button (+ empty panel) once; reused across re-layouts.
  function buildMore() {
    var btn = document.createElement("div");
    btn.className = "nav-tabs-item dt-more-tab";
    btn.setAttribute("role", "button");
    btn.setAttribute("tabindex", "0");
    btn.setAttribute("aria-haspopup", "true");
    btn.setAttribute("aria-expanded", "false");

    var label = document.createElement("span");
    label.className = "dt-more-label";
    btn.appendChild(label);

    // chevron (inherits currentColor)
    var caret = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    caret.setAttribute("class", "dt-more-caret");
    caret.setAttribute("viewBox", "0 0 24 24");
    caret.setAttribute("fill", "none");
    caret.setAttribute("stroke", "currentColor");
    caret.setAttribute("stroke-width", "2.2");
    caret.setAttribute("stroke-linecap", "round");
    caret.setAttribute("stroke-linejoin", "round");
    var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", "M6 9l6 6 6-6");
    caret.appendChild(path);
    btn.appendChild(caret);

    var panel = document.createElement("div");
    panel.className = "dt-more-panel";
    btn.appendChild(panel);

    // Toggle on click (touch / keyboard); hover is handled by CSS.
    btn.addEventListener("click", function (e) {
      if (e.target.closest(".dt-more-item")) return; // link click → navigate
      var open = btn.getAttribute("aria-expanded") === "true";
      btn.setAttribute("aria-expanded", open ? "false" : "true");
    });
    btn.addEventListener("keydown", function (e) {
      if (e.key === "Escape") btn.setAttribute("aria-expanded", "false");
    });
    // Close when clicking outside.
    document.addEventListener("click", function (e) {
      if (!btn.contains(e.target)) btn.setAttribute("aria-expanded", "false");
    });
    return btn;
  }

  // Text label of a Mintlify tab (icon <img> alt is empty, underline <div> empty).
  function tabLabel(a) {
    return (a.textContent || "").trim();
  }
  function isActive(a) {
    // Mintlify marks the active product tab with aria-current="location"
    // (aria-current="page" is used for the active sidebar page).
    return a.getAttribute("aria-current") != null;
  }

  // Rebuild the dropdown panel from the list of hidden tabs.
  function fillPanel(panel, hidden) {
    panel.textContent = "";
    hidden.forEach(function (a) {
      var item = document.createElement("a");
      item.className = "dt-more-item" + (isActive(a) ? " dt-more-item-active" : "");
      item.setAttribute("href", a.getAttribute("href") || "#");
      var img = a.querySelector("img");
      if (img) item.appendChild(img.cloneNode(true));
      item.appendChild(document.createTextNode(tabLabel(a)));
      panel.appendChild(item);
    });
  }

  // Core: hide tabs that don't fit into「更多」, show the rest.
  function layout() {
    var tabs = document.querySelector(".nav-tabs");
    if (!tabs) return;
    var wrap = tabs.parentElement;
    if (!wrap) return;

    // Compute available width FIRST and bail before mutating: at initial mount
    // the wrapper can be unsized (0) or hidden (<lg / custom home). Bailing here
    // (instead of after resetting tabs to visible) means we never flip the row
    // into the overflowing state during those transient/hidden moments — the
    // ResizeObserver re-invokes us the moment the wrapper gets a real width.
    var cs = getComputedStyle(wrap);
    var avail = wrap.clientWidth -
      parseFloat(cs.paddingLeft || 0) - parseFloat(cs.paddingRight || 0);
    if (avail <= 0) return;

    // Real layout is happening (wrapper is sized) → reveal the row: restores
    // overflow:visible so the「更多」dropdown can escape, and ends the CSS
    // pre-hide (single-line clip) that suppressed the load-time flash.
    document.documentElement.classList.add("dt-nav-ready");

    // Ensure「更多」exists as the last child of .nav-tabs.
    if (!moreEl) moreEl = buildMore();
    moreEl.querySelector(".dt-more-label").textContent =
      MORE_LABEL[detectLang()] || MORE_LABEL.en;
    if (moreEl.parentNode !== tabs) tabs.appendChild(moreEl);

    var items = Array.prototype.filter.call(tabs.children, function (el) {
      return el.classList &&
        el.classList.contains("nav-tabs-item") &&
        !el.classList.contains("dt-more-tab");
    });

    // Reset to natural state to measure.
    items.forEach(function (a) { a.style.display = ""; });
    moreEl.style.display = "none";

    var gap = parseFloat(getComputedStyle(tabs).columnGap) || 0;
    var widths = items.map(function (a) { return a.getBoundingClientRect().width; });
    var total = widths.reduce(function (s, w, i) { return s + w + (i > 0 ? gap : 0); }, 0);

    if (total <= avail) {
      moreEl.classList.remove("dt-more-active");
      fillPanel(moreEl.querySelector(".dt-more-panel"), []);
      return; // everything fits
    }

    // Overflow: reserve room for「更多」; always keep the active tab visible
    // (the current section should never hide inside the menu), then greedily
    // keep the remaining tabs that fit — DOM order preserved.
    moreEl.style.display = "";
    var moreW = moreEl.getBoundingClientRect().width;
    var budget = avail - moreW - gap;

    var activeIdx = -1;
    items.forEach(function (a, i) { if (isActive(a)) activeIdx = i; });
    var used = 0;
    if (activeIdx >= 0) used = widths[activeIdx] + gap; // pre-reserve active

    var hidden = [];
    items.forEach(function (a, i) {
      if (i === activeIdx) { a.style.display = ""; return; } // always show active
      var add = widths[i] + (used > 0 ? gap : 0);
      if (used + add <= budget) {
        used += add;
        a.style.display = "";
      } else {
        a.style.display = "none";
        hidden.push(a);
      }
    });

    if (!hidden.length) {
      moreEl.style.display = "none";
      moreEl.classList.remove("dt-more-active");
      fillPanel(moreEl.querySelector(".dt-more-panel"), []);
      return;
    }

    fillPanel(moreEl.querySelector(".dt-more-panel"), hidden);
    // Highlight「更多」if the current page's tab is inside it.
    moreEl.classList.toggle("dt-more-active", hidden.some(isActive));
  }

  var obs = null, ro = null, roTarget = null, running = false;

  function runLayout() {
    if (running) return;                 // reentrancy guard (our writes must not recurse)
    running = true;
    if (obs) obs.disconnect();
    try { layout(); } catch (_) {}
    if (obs) obs.observe(document.body, { childList: true, subtree: true });
    running = false;
  }

  // Attach a ResizeObserver to the tab-row wrapper the instant it exists. The RO
  // is the primary driver: its callback is delivered after layout and BEFORE
  // paint, so when the wrapper first gets a real width (or the viewport / web
  // font changes it), we collapse the overflow in the same frame — the full row
  // never paints. (Previously the RO attached via a 500ms setInterval, which was
  // exactly the ~365ms flash seen on load.)
  function ensureRO() {
    if (typeof ResizeObserver === "undefined") return;
    var tabs = document.querySelector(".nav-tabs");
    var wrap = tabs && tabs.parentElement;
    if (!wrap || wrap === roTarget) return;
    if (!ro) ro = new ResizeObserver(function () { runLayout(); });
    if (roTarget) { try { ro.unobserve(roTarget); } catch (_) {} }
    ro.observe(wrap);
    roTarget = wrap;
  }

  // Cheap structural signature — counts real tabs + notes the active one + lang.
  // Reads no geometry, so it never forces a reflow; used to skip the ~99% of
  // Mintlify mutations that don't touch the tab set.
  var lastSig = "";
  function sig() {
    var tabs = document.querySelector(".nav-tabs");
    if (!tabs) return "none";
    var n = 0, active = "";
    for (var i = 0; i < tabs.children.length; i++) {
      var el = tabs.children[i];
      if (!el.classList || !el.classList.contains("nav-tabs-item")) continue;
      if (el.classList.contains("dt-more-tab")) continue;
      n++;
      if (el.getAttribute("aria-current") != null) active = el.getAttribute("href") || "";
    }
    return n + "|" + active + "|" + detectLang();
  }

  // Runs SYNCHRONOUSLY inside the mutation callback (a microtask before paint):
  // collapsing in the same tick that mounts/swaps the tabs means the overflowing
  // row is never painted — no expand-then-shrink flash on load or SPA route
  // change. Also (re)attaches the RO to the current wrapper. Guarded by sig() so
  // most Mintlify mutations are a cheap no-op.
  function onMutation() {
    ensureRO();
    var s = sig();
    if (s === lastSig) return;
    lastSig = s;
    runLayout();
  }

  // SPA route changes: patch history so a nav re-triggers layout even if the DOM
  // diff is attribute-only (aria-current) rather than a childList swap.
  ["pushState", "replaceState"].forEach(function (m) {
    var orig = history[m];
    if (typeof orig !== "function") return;
    history[m] = function () {
      var r = orig.apply(this, arguments);
      runLayout();
      lastSig = sig();
      return r;
    };
  });
  window.addEventListener("popstate", function () { runLayout(); lastSig = sig(); });
  window.addEventListener("load", function () { ensureRO(); runLayout(); lastSig = sig(); });

  // Re-collapse once web fonts finish loading (CJK glyph widths shift on swap).
  if (document.fonts && document.fonts.ready && typeof document.fonts.ready.then === "function") {
    document.fonts.ready.then(function () { runLayout(); });
  }

  obs = new MutationObserver(onMutation);
  obs.observe(document.body, { childList: true, subtree: true });

  ensureRO();
  runLayout();
  lastSig = sig();
})();
