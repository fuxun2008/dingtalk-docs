/* ============================================================
   DingTalk Help Center — 内置语言切换器 relabel（Bahasa Melayu）
   - Mintlify 自动加载根目录 .js，全站生效、页面可交互后运行。
   - 背景：Mintlify docs.json 的 language 是封闭 enum，不含 ms（马来语）。
     ms 语言块借用受支持码 uz 注册以过校验（URL 仍是 /ms/，由 pages 路径决定）。
     副作用：内置语言切换器把该块显示为乌兹别克语原生名「O'zbekcha」
     （或用花体撇号的「Oʻzbekcha」变体）。本脚本把这两处文本改回「Bahasa Melayu」。
   - 覆盖两处 DOM：
       button[data-component-part="localization-select-trigger"] > span（收起态）
       div[data-component-part="localization-select-item"] > p（下拉项）
   - Mintlify 是 Next.js SPA：MutationObserver 兜住路由切换 / 下拉重建后的
     DOM 重绘。所有改动幂等（只改文本，反复运行结果一致）。
   - 平台一旦原生支持 ms，把 docs.json 语言码改回 "ms" 并删除本脚本即可。
   ============================================================ */
(function () {
  if (typeof document === "undefined") return;

  var TARGET = "Bahasa Melayu";
  // 匹配乌兹别克语原生名两种撇号变体：O'zbekcha / Oʻzbekcha（大小写不敏感）。
  var UZ_RE = /o.zbek/i;

  function relabelOne(el) {
    if (!el) return;
    var txt = (el.textContent || "").trim();
    if (UZ_RE.test(txt) && txt !== TARGET) {
      el.textContent = TARGET;
    }
  }

  function relabelAll() {
    // 收起态触发按钮里的 span
    document
      .querySelectorAll('button[data-component-part="localization-select-trigger"] span')
      .forEach(relabelOne);
    // 下拉展开后的每个语言项里的 p
    document
      .querySelectorAll('[data-component-part="localization-select-item"] p')
      .forEach(relabelOne);
  }

  var scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    (window.requestAnimationFrame || window.setTimeout)(function () {
      scheduled = false;
      relabelAll();
    }, 0);
  }

  function start() {
    relabelAll();
    // 兜住 SPA 路由切换 + 下拉动态挂载（内容区在打开时才渲染）。
    var obs = new MutationObserver(schedule);
    obs.observe(document.documentElement, { childList: true, subtree: true });
    // patch history，路由切换后立即重跑一次。
    ["pushState", "replaceState"].forEach(function (m) {
      var orig = history[m];
      if (typeof orig === "function") {
        history[m] = function () {
          var r = orig.apply(this, arguments);
          schedule();
          return r;
        };
      }
    });
    window.addEventListener("popstate", schedule);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
