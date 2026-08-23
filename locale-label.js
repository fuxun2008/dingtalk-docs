/* ============================================================
   DingTalk Help Center — 借码 uz 的马来语（Bahasa Melayu）chrome 汉化补丁
   - Mintlify 自动加载根目录 .js，全站生效、页面可交互后运行。
   - 背景：Mintlify docs.json 的 language 是封闭 enum，不含 ms（马来语）。
     ms 语言块借用受支持码 uz 注册以过校验（URL 仍是 /ms/，由 pages 路径决定）。
     副作用：Mintlify 内置 chrome（语言切换器、搜索、「本页目录」、复制页面、
     AI 助手面板、跳过链接、上一页/下一页等）会渲染成乌兹别克语内置译文。
     本脚本把这些内置字符串就地改回马来语。
   - 三类覆盖：
       1) 语言切换器原生名 O'zbekcha / Oʻzbekcha → Bahasa Melayu
       2) 精确匹配的 chrome 文本节点（TEXT_MAP）
       3) aria-label / placeholder / title 属性（ATTR_MAP + 分页前缀 Keyingi/Oldingi）
   - Mintlify 是 Next.js SPA：MutationObserver 兜住路由切换 / 下拉重建后的
     DOM 重绘。所有改动幂等（只改文本，反复运行结果一致）。
   - 文档正文本身已是马来语译文，本脚本不碰正文，只改平台内置 chrome。
   - 平台一旦原生支持 ms，把 docs.json 语言码改回 "ms" 并删除本脚本即可。
   ============================================================ */
(function () {
  if (typeof document === "undefined") return;

  var SWITCHER_TARGET = "Bahasa Melayu";
  // 匹配乌兹别克语原生名两种撇号变体：O'zbekcha / Oʻzbekcha（大小写不敏感）。
  var UZ_NATIVE_RE = /o.zbek/i;

  // 精确匹配的内置文本节点：乌兹别克语 → 马来语。
  var TEXT_MAP = {
    "Yordamchidan so'rash": "Tanya Pembantu AI",
    "Yordamchidan soʻrash": "Tanya Pembantu AI",
    "Yordamchi": "Pembantu AI",
    "Qidirish...": "Cari...",
    "Qidirish…": "Cari…",
    "Ushbu sahifada": "Pada halaman ini",
    "Sahifani nusxalash": "Salin halaman",
    "Asosiy tarkibga o'tish": "Pergi ke kandungan utama",
    "Asosiy tarkibga oʻtish": "Pergi ke kandungan utama",
    "Javoblar AI yordamida yaratilgan va xatolarga yo'l qo'yilishi mumkin.":
      "Jawapan dijana oleh AI dan mungkin mengandungi kesilapan.",
    "Javoblar AI yordamida yaratilgan va xatolarga yoʻl qoʻyilishi mumkin.":
      "Jawapan dijana oleh AI dan mungkin mengandungi kesilapan."
  };

  // 精确匹配的属性值：aria-label / placeholder / title。
  var ATTR_MAP = {
    "Sahifani nusxalash": "Salin halaman",
    "Qidiruvni ochish": "Buka carian",
    "Sarlavhaga o'tish": "Pergi ke tajuk",
    "Sarlavhaga oʻtish": "Pergi ke tajuk",
    "Savol bering...": "Tanya soalan...",
    "Savol bering…": "Tanya soalan…",
    "Xabar yuborish": "Hantar mesej",
    "Boshqa harakatlar": "Tindakan lain",
    "Yordamchi panelini kattalashtirish": "Besarkan panel pembantu",
    "Yordamchi panelini o'zgartirish": "Ubah panel pembantu",
    "Yordamchi panelini oʻzgartirish": "Ubah panel pembantu",
    "Yordamchi panelini yopish": "Tutup panel pembantu"
  };
  var ATTR_KEYS = ["aria-label", "placeholder", "title"];
  // 分页前缀（内置 aria-label 形如「Keyingi: <页名>」/「Oldingi: <页名>」，页名部分是马来语）。
  var PREFIX_MAP = { "Keyingi:": "Seterusnya:", "Oldingi:": "Sebelumnya:" };

  function mapText(txt) {
    if (UZ_NATIVE_RE.test(txt)) return SWITCHER_TARGET;
    if (Object.prototype.hasOwnProperty.call(TEXT_MAP, txt)) return TEXT_MAP[txt];
    return null;
  }

  function mapAttr(val) {
    if (Object.prototype.hasOwnProperty.call(ATTR_MAP, val)) return ATTR_MAP[val];
    for (var p in PREFIX_MAP) {
      if (Object.prototype.hasOwnProperty.call(PREFIX_MAP, p) && val.indexOf(p) === 0) {
        return PREFIX_MAP[p] + val.slice(p.length);
      }
    }
    return null;
  }

  function relabelAll() {
    // 1) 文本节点：走 TreeWalker，只改叶子文本，避开正文（正文不会命中 UZ 映射）。
    var walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT, null);
    var node;
    while ((node = walker.nextNode())) {
      var raw = node.textContent;
      if (!raw) continue;
      var trimmed = raw.trim();
      if (!trimmed) continue;
      var next = mapText(trimmed);
      if (next !== null && next !== trimmed) {
        node.textContent = raw.replace(trimmed, next);
      }
    }
    // 2) 属性：aria-label / placeholder / title。
    var withAttr = document.querySelectorAll("[aria-label],[placeholder],[title]");
    for (var i = 0; i < withAttr.length; i++) {
      var el = withAttr[i];
      for (var k = 0; k < ATTR_KEYS.length; k++) {
        var key = ATTR_KEYS[k];
        var v = el.getAttribute(key);
        if (!v) continue;
        var nv = mapAttr(v.trim());
        if (nv !== null && nv !== v) el.setAttribute(key, nv);
      }
    }
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
    // 兜住 SPA 路由切换 + 下拉/面板动态挂载（内容区在打开时才渲染）。
    var obs = new MutationObserver(schedule);
    obs.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
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
