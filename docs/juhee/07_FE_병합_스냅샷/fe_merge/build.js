/** 기존 FE 스냅샷 + 새 와이어프레임 패널 → 단일 HTML.
 *  node docs/juhee/07_FE_병합_스냅샷/fe_merge/build.js */
const fs = require('fs');
const path = require('path');
const HERE = __dirname;
const R = (p) => fs.readFileSync(p, 'utf8');

const shot = JSON.parse(R('/tmp/fe-snapshot.json'));
const css = R('/tmp/dist-css/wf.css');
const OUT = path.join(HERE, '..', '20260916_fe_merged.html');

const FE_TABS = ['모니터링', '프린트 제어', '대기 중인 작업', '이전 작업 내용', '통계', '자동화', '자동화 수동제어'];
const NEW_TABS = [['line', '라인 모니터링'], ['control', '공정 제어']];
const BTN = 'py-3 px-2 sm:px-1 border-b-2 font-medium text-sm whitespace-nowrap transition-colors';

const navBtn = (key, label, on, isNew) =>
  `<button data-tab="${key}" class="${BTN} ${on ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}">` +
  `${label}${isNew ? '<span class="ml-1 align-middle px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-600 text-[10px] font-semibold">NEW</span>' : ''}</button>`;

const nav =
  '<nav class="bg-white border-b sticky top-0 z-10"><div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">' +
  '<div class="flex space-x-1 sm:space-x-6 overflow-x-auto scrollbar-hide">' +
  FE_TABS.map((t, i) => navBtn('fe-' + i, t, i === 0, false)).join('') +
  NEW_TABS.map(([k, l]) => navBtn(k, l, false, true)).join('') +
  '</div></div></nav>';

const fePanels = FE_TABS.map((t, i) =>
  `<section data-panel="fe-${i}"${i === 0 ? '' : ' hidden'}>${shot.tabs[t] || ''}</section>`).join('\n');

const html = `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>3D 프린터 자동화 시스템 — FE + 라인 MES 와이어프레임</title>
<style>
${css}
/* 스냅샷 안의 실제 동작 버튼은 정지 화면이므로 눌러도 아무 일도 없다 */
section[data-panel^="fe-"] button:not([data-tab]){cursor:default}
</style>
</head>
<body class="min-h-screen bg-gray-100">
${shot.header}
${nav}
<main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
${fePanels}
${R(path.join(HERE, 'panels.html'))}
</main>

<script>${R(path.join(HERE, 'ctl_logic.js'))}</script>
<script>
(function () {
  var panels = [].slice.call(document.querySelectorAll('[data-panel]'));
  var tabs = [].slice.call(document.querySelectorAll('nav [data-tab]'));
  function show(key) {
    panels.forEach(function (p) { p.hidden = p.dataset.panel !== key; });
    tabs.forEach(function (b) {
      var on = b.dataset.tab === key;
      b.className = '${BTN} ' + (on ? 'border-blue-500 text-blue-600'
        : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300');
    });
    if (location.hash.slice(1) !== key) location.hash = key;
    window.scrollTo(0, 0);
    if (key === 'line' && window.WF_LINE) window.WF_LINE.render();
    if (key === 'control' && window.WF_CONTROL) window.WF_CONTROL.render();
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest('nav [data-tab]');
    if (b) show(b.dataset.tab);
  });
  window.addEventListener('hashchange', function () { show(location.hash.slice(1) || 'fe-0'); });
  window.__showTab = show;
  show(location.hash.slice(1) || 'fe-0');
})();
</script>
<script>window.WF_TOPO = ${R('/tmp/wf-topo.json')};</script>
<script>${R(path.join(HERE, 'line_view.js'))}</script>
<script>${R(path.join(HERE, 'robot_view.js'))}</script>
<script>${R(path.join(HERE, 'ctl_view.js'))}</script>
</body>
</html>
`;

fs.writeFileSync(OUT, html);
console.log('→', OUT, (html.length / 1024).toFixed(0) + 'KB');
