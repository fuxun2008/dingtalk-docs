// Mintlify footer.socials 不原生支持 email key，故用脚本在 socials 容器末尾追加邮箱图标。
// 样式严格复用 Mintlify 自带写法（mask-image + FontAwesome envelope），与 X/Instagram/LinkedIn 视觉一致。
// MutationObserver 监听 body 是为了应对 Next.js 路由切换后 footer 被重建的场景。
(function () {
  var EMAIL_HREF = 'mailto:questions@service.dingtalk.com';
  var ENVELOPE_SVG = 'https://d3gk2c5xim1je2.cloudfront.net/v7.1.0/solid/envelope.svg';

  function inject() {
    var container = document.querySelector('#footer > div.flex.gap-6');
    if (!container) return;
    if (container.querySelector('a[data-injected-email]')) return;

    var link = document.createElement('a');
    link.href = EMAIL_HREF;
    link.target = '_blank';
    link.className = 'h-fit';
    link.setAttribute('data-injected-email', '');
    link.innerHTML =
      '<span class="sr-only">email</span>' +
      '<svg class="w-5 h-5 bg-gray-400 dark:bg-gray-500 hover:bg-gray-500 dark:hover:bg-gray-400" aria-hidden="true" focusable="false" ' +
      'style="-webkit-mask-image:url(' + ENVELOPE_SVG + ');-webkit-mask-repeat:no-repeat;-webkit-mask-position:center;' +
      'mask-image:url(' + ENVELOPE_SVG + ');mask-repeat:no-repeat;mask-position:center"></svg>';

    container.appendChild(link);
  }

  function start() {
    inject();
    new MutationObserver(inject).observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
