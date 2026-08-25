/* ============================================================================
 * `rodi_pick_sequence.js` 시뮬레이터 — 로봇 없이 로직을 검증한다
 * ============================================================================
 *
 * ⭐ 왜 필요한가
 *   금요일(8/29) 현장 시간은 짧고, 로봇은 **실물이 움직이므로 실수가 비싸다.**
 *   순서·페이로드 갱신·실패 처리 같은 **로직 오류는 지금 잡을 수 있다.**
 *
 * 🚨 이 시뮬레이터가 검증하는 것 / 못 하는 것
 *   🟢 호출 순서 (접근→열기→하강→닫기→페이로드→상승→확인)
 *   🟢 setPayload 가 **들어올리기 전에** 호출되는가 (ko:129 요구사항)
 *   🟢 파지 실패 시 페이로드 복원 + 그리퍼 열기
 *   🟢 checkRunnableMotion 이 false 를 주면 정말 멈추는가
 *   🔴 실제 좌표가 맞는가 · 그리퍼가 물리적으로 잡는가 → **현장만**
 *
 * 사용법:  node bin_picking/tests/simulate_rodi_pick.js
 * ========================================================================== */

const fs = require('fs');
const path = require('path');

const SCRIPT = path.join(__dirname, '..', 'scripts', 'rodi_pick_sequence.js');

// ── 가짜 로봇 상태 ────────────────────────────────────────────────────────
function makeRobot(opts) {
    opts = opts || {};
    return {
        calls: [],
        pose: [300, 0, 400, 180, 0, 0],
        payload: null,
        gripperClosed: false,
        // 시나리오 제어
        graspWillSucceed: opts.graspWillSucceed !== false,
        hasGraspSensor: opts.hasGraspSensor !== false,
        unreachableAt: opts.unreachableAt || null,   // 이 라벨 이동을 불가로
        log: [],
    };
}

// ── 한화 API 스텁 ─────────────────────────────────────────────────────────
function buildSandbox(R) {
    const rec = (name, args) => R.calls.push({ name, args: JSON.parse(JSON.stringify(args)) });

    return {
        console: { log: (...a) => R.log.push(a.join(' ')) },
        JSON,

        createPose: (x, y, z, rx, ry, rz) => [x, y, z, rx, ry, rz],
        getCurrentPose: (t) => { rec('getCurrentPose', [t]); return R.pose.slice(); },
        getTargetPose: (t) => R.pose.slice(),

        checkRunnableMotion: (type, s, e, v, a, mt) => {
            rec('checkRunnableMotion', [type, s, e, v, a, mt]);
            // 인자 유효성도 검사한다 — startPose 를 빠뜨리면 여기서 걸린다
            if (!Array.isArray(s) || s.length !== 6) throw new Error('startPose 가 pose 가 아니다');
            if (!Array.isArray(e) || e.length !== 6) throw new Error('endPose 가 pose 가 아니다');
            if (R.unreachableAt && R._pendingLabel === R.unreachableAt) return false;
            return true;
        },
        moveLinear: (type, pose, v, a) => {
            rec('moveLinear', [type, pose, v, a]);
            R.pose = pose.slice();
        },
        isSteady: () => true,
        sleep: (s) => rec('sleep', [s]),
        halt: () => { rec('halt', []); throw new Error('__HALT__'); },

        setToolDigitalOutput: (n, v) => {
            rec('setToolDigitalOutput', [n, v]);
            R.gripperClosed = (v === 1);
        },
        getToolDigitalInput: (n) => {
            rec('getToolDigitalInput', [n]);
            if (!R.hasGraspSensor) return 0;
            return (R.gripperClosed && R.graspWillSucceed) ? 1 : 0;
        },
        serialSendString: (n, s) => rec('serialSendString', [n, s]),

        setPayload: (p, c) => { rec('setPayload', [p, c || null]); R.payload = p; },
        setToolCenterPoint: (p) => rec('setToolCenterPoint', [p]),

        socketCreate: (...a) => rec('socketCreate', a),
        socketOpen: (...a) => rec('socketOpen', a),
        socketWaitConnection: (...a) => rec('socketWaitConnection', a),
        socketReadLine: () => JSON.stringify([[400, 50, 250, 180, 0, 0]]),
        socketSendLine: (...a) => rec('socketSendLine', a),
        socketDisconnect: (...a) => rec('socketDisconnect', a),
    };
}

// ── 실행기: 스크립트를 읽어 MODE/설정을 바꿔 돌린다 ────────────────────────
function run(R, overrides) {
    let src = fs.readFileSync(SCRIPT, 'utf8');
    for (const [k, v] of Object.entries(overrides || {})) {
        const re = new RegExp(`^(var ${k}\\s*=)[^;]*;`, 'm');
        if (!re.test(src)) throw new Error(`설정 ${k} 을 스크립트에서 못 찾음`);
        src = src.replace(re, `$1 ${JSON.stringify(v)};`);
    }
    // safeMoveLinear 의 label 을 스텁이 볼 수 있게 살짝 감싼다
    src = src.replace(
        'function safeMoveLinear(pose, v, a, label) {',
        'function safeMoveLinear(pose, v, a, label) { __setLabel(label);'
    );
    const sandbox = buildSandbox(R);
    sandbox.__setLabel = (l) => { R._pendingLabel = l; };

    const vm = require('vm');
    const ctx = vm.createContext(sandbox);
    try {
        vm.runInContext(src, ctx, { timeout: 5000 });
    } catch (e) {
        if (e.message !== '__HALT__') throw e;
        R.halted = true;
    }
    return R;
}

const names = (R) => R.calls.map(c => c.name);
let pass = 0, fail = 0;
function check(label, cond, detail) {
    if (cond) { console.log(`  🟢 ${label}`); pass++; }
    else { console.log(`  🔴 ${label}${detail ? '  — ' + detail : ''}`); fail++; }
}

// ═══════════════════════════════════════════════════════════════════════════
console.log('① MODE gripper — 로봇이 움직이지 않아야 한다');
{
    const R = run(makeRobot(), { MODE: 'gripper' });
    const n = names(R);
    check('moveLinear 호출 0건', !n.includes('moveLinear'),
          `실제 ${n.filter(x => x === 'moveLinear').length}건`);
    check('개폐 6회 (닫기3+열기3)', n.filter(x => x === 'setToolDigitalOutput').length === 6);
    check('setPayload 로 도구 무게 설정', R.payload === 1.5);
    check('파지 입력 조회 3회', n.filter(x => x === 'getToolDigitalInput').length === 3);
}

console.log('\n② MODE teach — TEACH_POSE 가 없으면 아무것도 하지 않아야 한다');
{
    const R = run(makeRobot(), { MODE: 'teach' });
    check('moveLinear 0건', !names(R).includes('moveLinear'));
    check('경고 출력', R.log.some(l => l.includes('TEACH_POSE 가 비어')));
}

console.log('\n③ MODE teach + 좌표 — 파지 순서가 맞아야 한다');
{
    const R = run(makeRobot(), { MODE: 'teach', TEACH_POSE: [400, 0, 250, 180, 0, 0] });
    const n = names(R);
    const iOpen  = R.calls.findIndex(c => c.name === 'setToolDigitalOutput' && c.args[1] === 0);
    const iDown  = R.calls.findIndex((c, k) => c.name === 'moveLinear' && k > iOpen);
    const iClose = R.calls.findIndex(c => c.name === 'setToolDigitalOutput' && c.args[1] === 1);
    const iPay   = R.calls.findIndex(c => c.name === 'setPayload' && c.args[0] > 1.5);
    const iLift  = R.calls.findIndex((c, k) => c.name === 'moveLinear' && k > iPay);

    check('열기 → 하강 → 닫기 순서', iOpen < iDown && iDown < iClose,
          `open=${iOpen} down=${iDown} close=${iClose}`);
    check('⭐ setPayload 가 닫기 뒤 · 상승 앞 (ko:129)', iClose < iPay && iPay < iLift,
          `close=${iClose} pay=${iPay} lift=${iLift}`);
    check('페이로드 = 도구+부품 = 1.55', Math.abs(R.payload - 1.55) < 1e-9, `실제 ${R.payload}`);
    check('매 이동마다 checkRunnableMotion',
          n.filter(x => x === 'checkRunnableMotion').length === n.filter(x => x === 'moveLinear').length);
    check('파지 성공 로그', R.log.some(l => l.includes('🟢 잡았다')));
    // ⚠️ 인덱스 주의 = moveLinear(type, pose, v, a) → v 는 args[2], a 는 args[3]
    //    (처음 args[3]을 속도로 읽어 이 검사가 헛되게 실패했다. 코드가 아니라 테스트가 틀렸다)
    const downCall = R.calls.filter(c => c.name === 'moveLinear')[1];   // 0=접근 1=하강
    check('하강은 저속 V_SLOW=20 / A_SLOW=100',
          downCall && downCall.args[2] === 20 && downCall.args[3] === 100,
          downCall ? `v=${downCall.args[2]} a=${downCall.args[3]}` : '하강 호출 없음');
    const appCall = R.calls.filter(c => c.name === 'moveLinear')[0];
    check('접근 상공은 고속 V_FAST=100',
          appCall && appCall.args[2] === 100, appCall ? `v=${appCall.args[2]}` : '-');
}

console.log('\n④ 🚨 파지 실패 — 페이로드 복원 + 그리퍼 열기까지 해야 한다');
{
    const R = run(makeRobot({ graspWillSucceed: false }),
                  { MODE: 'teach', TEACH_POSE: [400, 0, 250, 180, 0, 0] });
    check('실패 로그', R.log.some(l => l.includes('🔴 놓쳤다')));
    check('⭐ 페이로드가 도구만으로 복원', R.payload === 1.5, `실제 ${R.payload}`);
    const last = R.calls.filter(c => c.name === 'setToolDigitalOutput').pop();
    check('마지막 그리퍼 동작 = 열기', last && last.args[1] === 0);
}

console.log('\n⑤ 🚨 파지 센서 배선 없음 — "놓쳤다"로 오판하지 않아야 한다');
{
    const R = run(makeRobot({ hasGraspSensor: false }),
                  { MODE: 'teach', TEACH_POSE: [400, 0, 250, 180, 0, 0] });
    // 배선이 없으면 dio 모드에서도 0 이 오므로 "놓쳤다"가 된다 —
    // 이것이 실제 위험이라 드러내는 것이 목적이다
    const missed = R.log.some(l => l.includes('🔴 놓쳤다'));
    check('⚠️ 배선 없으면 "놓쳤다"로 읽힌다 (알려진 한계)', missed,
          '이 결과가 나오는 것이 정상 — 현장에서 배선 확인 필요');
}

console.log('\n⑥ 🚨 도달 불가 — 멈추고 진행하지 않아야 한다');
{
    const R = run(makeRobot({ unreachableAt: '하강' }),
                  { MODE: 'teach', TEACH_POSE: [400, 0, 250, 180, 0, 0] });
    check('도달 불가 로그', R.log.some(l => l.includes('도달 불가')));
    check('닫기(파지) 시도 안 함',
          !R.calls.some(c => c.name === 'setToolDigitalOutput' && c.args[1] === 1),
          '하강이 막혔는데 그리퍼를 닫으면 허공에서 닫는다');
    check('페이로드 증가 없음', R.payload === 1.5);
}

console.log('\n⑦ MODE vision — 소켓 골격이 협력사 예시와 같아야 한다');
{
    const R = run(makeRobot(), { MODE: 'vision' });
    const n = names(R);
    const order = ['socketCreate', 'socketOpen', 'socketWaitConnection'];
    let ok = true, at = -1;
    for (const s of order) { const i = n.indexOf(s); if (i < at) ok = false; at = i; }
    check('socketCreate → Open → WaitConnection 순서', ok);
    check('DONE 전송', R.calls.some(c => c.name === 'socketSendLine' && c.args[1] === 'DONE'));
    check('socketDisconnect', n.includes('socketDisconnect'));
    check('PLACE_POSE 없으면 1개만 시도', R.log.some(l => l.includes('1개만 시도')));
}

console.log('\n' + '='.repeat(62));
console.log(`  통과 ${pass} / 실패 ${fail}`);
if (fail === 0) {
    console.log('  ✅ 로직 검증 통과 — 🚨 단 실제 좌표·그리퍼 물리 동작은 현장에서만 확인된다');
} else {
    console.log('  🔴 로직 오류 — 현장에 들고 가기 전에 고칠 것');
}
console.log('='.repeat(62));
process.exit(fail === 0 ? 0 : 1);
