/** 돌고 있는 데모 FE 를 jsdom 으로 실제 실행해서 탭별 DOM 을 뜬다. */
const fs = require('fs');
const { JSDOM } = require('jsdom');

const API = 'http://127.0.0.1:8085';
const OUT = process.argv[2] || '/tmp/fe-snapshot.json';

(async () => {
  const r = await fetch(API + '/api/v1/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'demo', password: 'demo1234' }),
  });
  const { access_token } = await r.json();

  const html = fs.readFileSync('/tmp/dist-snap/index.html', 'utf8')
    .replace(/<script[^>]*><\/script>/, '');
  const dom = new JSDOM(html, { runScripts: 'dangerously', url: 'http://127.0.0.1:5180/', pretendToBeVisual: true });
  const W = dom.window;

  W.localStorage.setItem('orinu_auth_token', access_token);
  W.localStorage.setItem('orinu_auth_username', 'demo');

  // 상대 경로 fetch → 데모 백엔드로
  W.fetch = (input, init) => {
    let url = typeof input === 'string' ? input : input.url;
    if (url.startsWith('/')) url = API + url;
    return fetch(url, init);
  };
  W.WebSocket = class { constructor() { this.readyState = 3; } close() {} addEventListener() {} };
  W.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
  W.scrollTo = () => {};
  W.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} });
  const errs = [];
  W.addEventListener('error', (e) => errs.push(String(e.message || e.error)));

  const script = W.document.createElement('script');
  script.textContent = fs.readFileSync('/tmp/dist-snap/app.js', 'utf8');
  W.document.body.appendChild(script);

  const wait = (ms) => new Promise((res) => setTimeout(res, ms));
  await wait(2500);

  const D = W.document;
  const root = D.getElementById('root');
  const tabs = () => Array.from(D.querySelectorAll('nav button'));
  console.log('탭:', tabs().map((t) => t.textContent.trim()).join(' | '));

  const shot = { css: '', tabs: {}, header: '', nav: '' };
  shot.css = Array.from(D.querySelectorAll('style')).map((s) => s.textContent).join('\n');

  const labels = ['모니터링', '프린트 제어', '대기 중인 작업', '이전 작업 내용', '통계', '자동화', '자동화 수동제어'];
  for (const label of labels) {
    const btn = tabs().find((t) => t.textContent.trim() === label);
    if (!btn) { console.log('  ✗ 탭 없음:', label); continue; }
    btn.dispatchEvent(new W.MouseEvent('click', { bubbles: true }));
    await wait(1600);
    const main = D.querySelector('main') || root;
    shot.tabs[label] = main.innerHTML;
    console.log('  ✓', label, main.innerHTML.length, 'chars');
  }
  shot.header = D.querySelector('header') ? D.querySelector('header').outerHTML : '';
  shot.nav = D.querySelector('nav') ? D.querySelector('nav').outerHTML : '';

  fs.writeFileSync(OUT, JSON.stringify(shot, null, 1));
  console.log('js errors:', errs.length, errs.slice(0, 3));
  console.log('saved', OUT, (fs.statSync(OUT).size / 1024).toFixed(0) + 'KB');
  process.exit(0);
})();
