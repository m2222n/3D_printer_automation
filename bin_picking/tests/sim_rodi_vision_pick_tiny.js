// rodi_vision_pick_tiny.js 모의 실행 — 펜던트 없이 동작 순서·DO 펄스·놓기 분기를 검증 (node bin_picking/tests/sim_rodi_vision_pick_tiny.js)
// 실제 스크립트 파일을 그대로 읽어 Rodi 함수만 가짜로 바꿔 실행한다(복붙본 아님 → 파일을 고치면 이 검사도 따라간다)
const fs = require('fs'), path = require('path');
const SRC = fs.readFileSync(path.join(__dirname, '..', 'scripts', 'rodi_vision_pick_tiny.js'), 'utf8');

// 🚨 펜던트 script 노드는 한글 입력 불가(9/28) — 코드 줄(주석 아닌 줄)에 ASCII 밖 문자가 있으면 실패
function asciiCheck() {
  const bad = SRC.split('\n').map((l, i) => [i + 1, l]).filter(([, l]) => !l.trim().startsWith('//') && /[^\x00-\x7F]/.test(l));
  return bad;
}

function run({ place = null, held = 1, unreachable = () => false, poses = [[700, -600, 430, 180, 0, -90]] }) {
  const log = [], moves = [], dos = [];
  let tcp = [759.08, -593.74, 379.41, -176.28, -3.94, -90.16];
  const env = {
    socketCreate() {}, socketOpen() {}, socketWaitConnection() {}, socketDisconnect() {},
    socketReadLine() { return JSON.stringify(poses); },
    socketSendLine(_, s) { log.push('SEND ' + s); },
    getCurrentPose() { return tcp.slice(); },
    createPose(...a) { return a; },
    checkRunnableMotion(_, here, target) { return !unreachable(target); },
    moveLinear(_, target, v) { moves.push({ target: target.slice(), v }); tcp = target.slice(); },
    isSteady() { return true; }, sleep() {},
    setGeneralDigitalOutput(ch, v) { dos.push([ch, v]); },
    getGeneralDigitalInput(ch) { return ch === 1 ? held : ch === 2 ? (held ? 0 : 1) : 0; },
    console: { log: (m) => log.push(m) },
  };
  let src = SRC.replace("var PLACE = null;", 'var PLACE = ' + JSON.stringify(place) + ';').replace("'SET_ME'", "'192.168.101.50'");
  const fn = new Function(...Object.keys(env), src);
  fn(...Object.values(env));
  const highs = dos.filter(([, v]) => v === 1).map(([ch]) => ch);   // 펄스로 High 된 채널 순서
  return { log, moves, highs };
}

let pass = 0, fail = 0;
function ok(cond, msg) { if (cond) { pass++; console.log('  🟢 ' + msg); } else { fail++; console.log('  🔴 ' + msg); } }
const near = (a, b) => a.every((x, i) => Math.abs(x - b[i]) < 1e-6);

console.log('① ASCII (펜던트 타이핑 가능)');
ok(asciiCheck().length === 0, '코드 줄 ASCII only' + (asciiCheck().length ? ' — ' + JSON.stringify(asciiCheck()) : ''));

console.log('② PLACE 없음 = 10/8 동작(집고 들어올리기까지)');
let r = run({ place: null });
ok(r.highs.join(',') === '1,3', 'DO 펄스 = 열기(1) → 닫기(3)');
ok(r.moves.length === 3, '이동 3번 = hover → 하강 → 상승');
ok(near(r.moves[1].target, [700, -600, 380, 180, 0, -90]), '하강 z = hover − 50');
ok(r.moves[1].v === 10, '하강 속도 VD 10');
ok(r.log.includes('SEND DONE'), 'DONE 회신');

console.log('③ PLACE 있음 + 물었음(IN1=1) = 놓기까지');
const P = [650, -450, 340, 180, 0, -90];
r = run({ place: P, held: 1 });
ok(r.highs.join(',') === '1,3,1', 'DO 펄스 = 열기 → 닫기 → 열기(놓기)');
ok(r.moves.length === 6, '이동 6번 = hover → 하강 → 상승 → 놓을 자리 위 → 내려놓기 → 상승');
ok(near(r.moves[3].target, [650, -450, 390, 180, 0, -90]), '놓을 자리 위 = PLACE z + 50');
ok(near(r.moves[4].target, P), '내려놓기 = PLACE 그대로');
ok(r.moves[4].v === 10, '내려놓기 속도 VD 10');
ok(r.log.some(l => l.startsWith('OK PLACED')), 'OK PLACED 로그');

console.log('④ PLACE 있음 + 못 물었음(IN1=0) = 놓으러 가지 않는다');
r = run({ place: P, held: 0 });
ok(r.highs.join(',') === '1,3', 'DO 펄스 = 열기 → 닫기 (놓기 열기 없음)');
ok(r.moves.length === 3, '이동 3번에서 멈춤');
ok(r.log.some(l => l.startsWith('SKIP PLACE')), 'SKIP PLACE 로그');

console.log('⑤ 도달 불가 = 움직이지 않는다');
r = run({ place: P, unreachable: () => true });
ok(r.moves.length === 0 && r.highs.length === 0, 'hover 도달 불가 → 이동 0 · 그리퍼 0');
ok(r.log.some(l => l.startsWith('NG UNREACHABLE')), 'NG UNREACHABLE 로그');
r = run({ place: P, unreachable: (t) => t[0] === 650 });
ok(r.highs.join(',') === '1,3' && !r.log.some(l => l.startsWith('OK PLACED')), '놓을 자리 도달 불가 → 문 채로 hover 에 머문다(열지 않음)');

console.log('⑥ 받은 포즈 0개 = 아무것도 안 한다');
r = run({ poses: [] });
ok(r.moves.length === 0 && r.log.includes('SEND DONE'), '이동 0 · DONE 회신');

console.log(fail === 0 ? `✅ 통과 ${pass}` : `🔴 실패 ${fail} / 통과 ${pass}`);
process.exit(fail === 0 ? 0 : 1);
