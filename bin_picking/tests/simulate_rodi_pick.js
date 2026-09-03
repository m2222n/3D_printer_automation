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
        // ⭐ readyHighAtStart = 전원 투입 직후 상태 재현: 그리퍼가 스스로 원점(0mm·닫힘)까지 가고 IN_1 을 올려 둔 채(교안:5·25)
        gripperClosed: !!opts.readyHighAtStart,
        // gen_dio(교안 신호조합) 시나리오 — 컨트롤러 DO0~3 = OUT-1~4 / DI0~2 = IN_1~3 (교안:5 손글씨)
        gripOut: [0, 0, 0, 0],
        gripIn: { ready: opts.readyHighAtStart ? 1 : 0, grasped: 0, error: 0 },
        // 시나리오 제어
        graspWillSucceed: opts.graspWillSucceed !== false,
        hasGraspSensor: opts.hasGraspSensor !== false,
        unreachableAt: opts.unreachableAt || null,   // 이 라벨 이동을 불가로
        // rs485 시나리오: 스크립트에 넣은 GRIP_REG 와 같은 값을 스텁도 알아야 한다
        regCmd: opts.regCmd !== undefined ? opts.regCmd : 0x0100,
        regCloseVal: opts.regCloseVal !== undefined ? opts.regCloseVal : 1,
        log: [],
    };
}

// ── 교안:6 신호조합표 (시뮬 독립 사본 · 스크립트 표와 별개로 옮겼다) ────────
const JRT_STANDBY = ['1000', '0100', '1100', '1110', '1111'];                       // 대기 1~5
const JRT_GRASP   = ['0010', '0001', '1010', '1001', '0110', '0101', '0011', '1101', '1011', '0111'];  // 파지 1~10

/** DO0~3 현재 패턴을 교안 표에 대조해 가짜 그리퍼 상태를 갱신한다. 상태가 바뀔 때만 개폐 이벤트를 남긴다. */
function applyGripCombo(R) {
    const pat = R.gripOut.join('');
    const rec = (name, args) => R.calls.push({ name, args });
    if (JRT_STANDBY.includes(pat)) {
        // 대기 n = 열림 → IN_1(대기위치 이동 완료) High
        if (R.gripperClosed) rec('__gripOpen', ['combo', pat, `대기${JRT_STANDBY.indexOf(pat) + 1}`]);
        R.gripperClosed = false;
        R.gripIn = { ready: 1, grasped: 0, error: 0 };
    } else if (JRT_GRASP.includes(pat)) {
        // 파지 n = 닫힘 → 교안:22 범위 안에서 멈추면 IN_2(파지 완료), 밖이면 IN_3(파지 실패 = 에러)
        if (!R.gripperClosed) rec('__gripClose', ['combo', pat, `파지${JRT_GRASP.indexOf(pat) + 1}`]);
        R.gripperClosed = true;
        R.gripIn = R.graspWillSucceed
            ? { ready: 0, grasped: 1, error: 0 }
            : { ready: 0, grasped: 0, error: 1 };
    }
    // 0000 또는 표에 없는 조합 = 명령 없음 → 상태 유지 (교안:6 표에 all-Low 없음)
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
        // ⭐ 시간이 흐를 때(sleep) 가짜 그리퍼가 DO 패턴을 읽는다 = 교안:18·24 "입력시간"(패턴이 유지된 뒤 판정) 모델.
        //    🚨 DO 를 한 채널씩 쓰는 도중의 과도 패턴(예: 1111→0111 가는 길의 0110=파지5)이 먹히면 안 된다 —
        //    9/3 시뮬이 실제로 이 오작동을 잡았고, 그래서 판정 시점을 "쓸 때"가 아니라 "입력시간이 흐른 뒤"로 뒀다.
        sleep: (s) => { rec('sleep', [s]); applyGripCombo(R); },
        halt: () => { rec('halt', []); throw new Error('__HALT__'); },

        // ── 툴 플랜지 I/O (ko:58~60) — 비교용 'dio' 모드. 개폐 이벤트를 __gripClose/__gripOpen 으로 남긴다
        setToolDigitalOutput: (n, v) => {
            rec('setToolDigitalOutput', [n, v]);
            R.gripperClosed = (v === 1);
            rec(v === 1 ? '__gripClose' : '__gripOpen', ['tool']);
        },
        getToolDigitalInput: (n) => {
            rec('getToolDigitalInput', [n]);
            if (!R.hasGraspSensor) return 0;
            return (R.gripperClosed && R.graspWillSucceed) ? 1 : 0;
        },
        // ── 본체 일반 디지털 I/O (§3.1.1~3.1.2) — 교안:6 신호조합을 **독립 사본**으로 재현하는 가짜 그리퍼
        //    ⭐ 스크립트의 GRIP_COMBO 를 import 하지 않는다 — 표를 잘못 옮기면 여기서 어긋나 잡히게.
        //    교안:5 손글씨 채널 배정(OUT_1~4→DO0~3 · IN_1→DI0 · IN_2→DI1 · IN_3→DI2)을 그대로 쓴다.
        setGeneralDigitalOutput: (n, v) => {
            rec('setGeneralDigitalOutput', [n, v]);
            if (n < 0 || n > 3) throw new Error(`DO${n} 는 그리퍼 배선(DO0~3) 밖`);
            if (v !== 0 && v !== 1) throw new Error(`DO 값은 0/1 이어야 한다: ${v}`);
            R.gripOut[n] = v;          // 판정은 sleep(입력시간) 때 — 위 sleep 스텁 참조
        },
        getGeneralDigitalInput: (n) => {
            rec('getGeneralDigitalInput', [n]);
            const key = ({ 0: 'ready', 1: 'grasped', 2: 'error' })[n];
            if (key === undefined) throw new Error(`DI${n} 는 그리퍼 배선(DI0~2) 밖`);
            if (!R.hasGraspSensor) return 0;                 // 상태선(IN_1~3) 미배선 시나리오
            return R.gripIn[key];
        },
        serialSendString: (n, s) => rec('serialSendString', [n, s]),

        // ── RS485 / Modbus RTU (ko:115~124) ───────────────────────────────
        robotToolIoRs485Set: (...a) => rec('robotToolIoRs485Set', a),
        robotToolIoRs485ModbusRtuWrite: (id, slave, fn, addr, num, tx) => {
            rec('robotToolIoRs485ModbusRtuWrite', [id, slave, fn, addr, num, tx]);
            // 🚨 인자 유효성 — 매뉴얼 규격을 어기면 여기서 걸린다
            if (slave < 1 || slave > 247) throw new Error('slaveAddress 범위 위반(1~247)');
            if (!Array.isArray(tx)) throw new Error('txData 가 배열이 아니다');
            if (tx.length > 64) throw new Error('txData 64바이트 초과');
            if (tx.some(b => b < 0 || b > 255)) throw new Error('txData 에 바이트 아닌 값');
            if (addr === null || addr === undefined) throw new Error('startAddress 가 null');
            // 개폐 상태 추적 (cmd 레지스터에 쓴 값으로 판단)
            const w = (tx[0] << 8) | tx[1];
            if (addr === R.regCmd) R.gripperClosed = (w === R.regCloseVal);
        },
        robotToolIoRs485ModbusRtuRead: (id, slave, fn, addr, num, buf) => {
            rec('robotToolIoRs485ModbusRtuRead', [id, slave, fn, addr, num, buf]);
            if (buf > 64) throw new Error('bufferSize 64 초과');
            if (!R.hasGraspSensor) return [0x00, 0x00];
            return (R.gripperClosed && R.graspWillSucceed) ? [0x00, 0x01] : [0x00, 0x00];
        },

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
// 개폐 이벤트(모드 무관): dio 는 setToolDigitalOutput 에서, gen_dio 는 조합 판정에서 남긴다
const gripEvents = (R) => R.calls.filter(c => c.name === '__gripOpen' || c.name === '__gripClose');
let pass = 0, fail = 0;
function check(label, cond, detail) {
    if (cond) { console.log(`  🟢 ${label}`); pass++; }
    else { console.log(`  🔴 ${label}${detail ? '  — ' + detail : ''}`); fail++; }
}

// ═══════════════════════════════════════════════════════════════════════════
console.log('① MODE gripper — 로봇이 움직이지 않아야 한다 (기본 = gen_dio · 교안 신호조합)');
{
    const R = run(makeRobot(), { MODE: 'gripper' });
    const n = names(R);
    check('moveLinear 호출 0건', !n.includes('moveLinear'),
          `실제 ${n.filter(x => x === 'moveLinear').length}건`);
    const ev = gripEvents(R);
    check('개폐 6회 (닫기3+열기3)', ev.filter(c => c.name === '__gripClose').length === 3
                                   && ev.filter(c => c.name === '__gripOpen').length === 3,
          `이벤트 ${ev.map(c => c.name).join(',')}`);
    check('setPayload 로 도구 무게 설정', R.payload === 1.5);
    check('파지 입력(IN_2=DI1) 조회 ≥3회',
          R.calls.filter(c => c.name === 'getGeneralDigitalInput' && c.args[0] === 1).length >= 3);
    check('🚨 기본 모드는 툴 I/O 를 건드리지 않는다', !n.includes('setToolDigitalOutput'),
          '교안:5 = 그리퍼는 컨트롤러 본체 I/O 에 물린다');
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
    const iOpen  = R.calls.findIndex(c => c.name === '__gripOpen');
    const iDown  = R.calls.findIndex((c, k) => c.name === 'moveLinear' && k > iOpen);
    const iClose = R.calls.findIndex(c => c.name === '__gripClose');
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
    const last = gripEvents(R).pop();
    check('마지막 그리퍼 동작 = 열기(교안:25 대기위치 복귀)', last && last.name === '__gripOpen');
    check('에러(IN_3)를 로그로 알린다', R.log.some(l => l.includes('그리퍼 에러(IN_3)')),
          '파지 실패 = 그리퍼가 IN_3 을 올린다(교안:22)');
}

console.log('\n⑤ 🚨 파지 센서 배선 없음 — "놓쳤다"로 오판하지 않아야 한다');
{
    const R = run(makeRobot({ hasGraspSensor: false }),
                  { MODE: 'teach', TEACH_POSE: [400, 0, 250, 180, 0, 0] });
    // 상태선(IN_1~3)이 없으면 완료 신호가 영원히 안 와서 "놓쳤다"가 된다 —
    // 이것이 실제 위험이라 드러내는 것이 목적이다
    const missed = R.log.some(l => l.includes('🔴 놓쳤다'));
    check('⚠️ 배선 없으면 "놓쳤다"로 읽힌다 (알려진 한계)', missed,
          '이 결과가 나오는 것이 정상 — 현장에서 배선 확인 필요');
    check('완료 신호 대기 초과를 로그로 알린다(조용히 넘어가지 않는다)',
          R.log.some(l => l.includes('대기 초과')));
}

console.log('\n⑥ 🚨 도달 불가 — 멈추고 진행하지 않아야 한다');
{
    const R = run(makeRobot({ unreachableAt: '하강' }),
                  { MODE: 'teach', TEACH_POSE: [400, 0, 250, 180, 0, 0] });
    check('도달 불가 로그', R.log.some(l => l.includes('도달 불가')));
    check('닫기(파지) 시도 안 함',
          !R.calls.some(c => c.name === '__gripClose'),
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

console.log('\n⑧ 🚨 GRIPPER_MODE rs485 — 레지스터 맵이 비어 있으면 "조용히" 넘어가면 안 된다');
{
    const R = run(makeRobot(), { MODE: 'gripper', GRIPPER_MODE: 'rs485' });
    check('RS485 초기화를 먼저 부른다',
          names(R).includes('robotToolIoRs485Set'),
          'ko:123 = Set 을 먼저 해야 ModbusRtu 헬퍼가 동작한다');
    check('맵 없음을 로그로 알린다', R.log.some(l => l.includes('레지스터 맵')));
    check('🚨 추측 주소로 쓰지 않는다',
          !names(R).includes('robotToolIoRs485ModbusRtuWrite'),
          '맵을 모르는 채로 쓰면 엉뚱한 레지스터를 건드린다');
    check('⭐ 열기 실패도 알린다(닫힌 채 방치 경고)',
          R.log.some(l => l.includes('닫힌 채로') || l.includes('열기를 수행하지 못')),
          '9/1 발견: 원래 gripperOpen 에 rs485 분기가 없어 조용히 통과했다');
}

console.log('\n⑨ ⭐ GRIPPER_MODE rs485 + 맵 채움 — 개폐가 레지스터 쓰기로 나가야 한다');
{
    const R = run(makeRobot(), {
        MODE: 'gripper',
        GRIPPER_MODE: 'rs485',
        GRIP_REG: { cmd: 0x0100, openVal: 0, closeVal: 1,
                    width: 0x0102, force: 0x0103, status: 0x0200 },
        GRIP_TARGET_WIDTH: 60,
        GRIP_TARGET_FORCE: 80,
    });
    const w = R.calls.filter(c => c.name === 'robotToolIoRs485ModbusRtuWrite');
    check('레지스터 쓰기가 발생', w.length > 0);
    check('닫기 = cmd 레지스터에 closeVal',
          w.some(c => c.args[3] === 0x0100 && ((c.args[5][0] << 8) | c.args[5][1]) === 1));
    check('열기 = cmd 레지스터에 openVal',
          w.some(c => c.args[3] === 0x0100 && ((c.args[5][0] << 8) | c.args[5][1]) === 0));
    check('⭐ 벌림 폭을 지정한다 (rs485 를 쓰는 이유)',
          w.some(c => c.args[3] === 0x0102 && ((c.args[5][0] << 8) | c.args[5][1]) === 60),
          '이게 되면 8/10 "벌림 19가지→15점 묶기"가 불필요해진다');
    check('파지력을 지정한다',
          w.some(c => c.args[3] === 0x0103 && ((c.args[5][0] << 8) | c.args[5][1]) === 80));
    check('function code 6 (single register write)', w.every(c => c.args[2] === 6));
    check('⭐ 상태 레지스터로 파지 확인',
          names(R).includes('robotToolIoRs485ModbusRtuRead'));
    check('🚨 setToolDigitalOutput 은 쓰지 않는다',
          !names(R).includes('setToolDigitalOutput'),
          '배선이 rs485 면 DIO 를 건드리면 안 된다');
}

console.log('\n⑩ GRIPPER_MODE serial — 열기·닫기 둘 다 나가야 한다');
{
    const R = run(makeRobot(), { MODE: 'gripper', GRIPPER_MODE: 'serial' });
    const ss = R.calls.filter(c => c.name === 'serialSendString');
    check('CLOSE 3회', ss.filter(c => c.args[1] === 'CLOSE').length === 3);
    check('OPEN 3회', ss.filter(c => c.args[1] === 'OPEN').length === 3);
    check('마지막은 열기', ss[ss.length - 1].args[1] === 'OPEN');
    check('파지 확인은 판단 불가(null)로 나온다',
          R.log.some(l => l.includes('배선없음')),
          'serial 은 피드백 경로가 없다 — "놓쳤다"로 오판하면 안 된다');
}

console.log('\n⑪ ⭐⭐ GRIPPER_MODE gen_dio — 교안:6 신호조합으로 개폐한다 (단일 채널 토글이 아니다)');
{
    const R = run(makeRobot(), { MODE: 'gripper', GRIPPER_MODE: 'gen_dio' });
    const g  = R.calls.filter(c => c.name === 'setGeneralDigitalOutput');
    const ev = gripEvents(R);
    check('OUT-1~4 = DO0~3 네 채널만 쓴다',
          g.length > 0 && g.every(c => c.args[0] >= 0 && c.args[0] <= 3)
                       && new Set(g.map(c => c.args[0])).size === 4,
          `사용 채널 ${[...new Set(g.map(c => c.args[0]))].join(',')}`);
    check('명령 1회 = 4채널 쓰기 (6회 명령 = 24회)', g.length === 24, `실제 ${g.length}회`);
    check('닫기 3회 = 파지1 조합(0010)', ev.filter(c => c.name === '__gripClose' && c.args[1] === '0010').length === 3,
          `이벤트 ${ev.map(c => c.args[2]).join(',')}`);
    check('열기 3회 = 대기1 조합(1000)', ev.filter(c => c.name === '__gripOpen' && c.args[1] === '1000').length === 3);
    check('마지막은 열기', ev[ev.length - 1].name === '__gripOpen');
    check('교안:24 입력시간 50ms 를 조합 출력 뒤에 둔다',
          R.calls.some(c => c.name === 'sleep' && Math.abs(c.args[0] - 0.05) < 1e-9));
    check('파지 완료는 IN_2 = DI1 로 읽는다',
          R.calls.some(c => c.name === 'getGeneralDigitalInput' && c.args[0] === 1));
    check('에러는 IN_3 = DI2 를 함께 감시한다',
          R.calls.some(c => c.name === 'getGeneralDigitalInput' && c.args[0] === 2));
    check('🚨 setToolDigitalOutput 은 쓰지 않는다',
          !R.calls.some(c => c.name === 'setToolDigitalOutput'),
          '툴 플랜지 I/O 와 본체 DO 를 섞으면 어느 쪽 배선인지 못 가린다');
    check('파지 입력이 true 로 읽힌다(가짜 그리퍼가 IN_2 를 올림)', R.log.some(l => l.includes('파지 입력 = true')));
}

console.log('\n⑫ 🚨 gen_dio 파지 실패 — 그리퍼가 IN_3(에러)를 올리면 교안:25 대로 대기위치로 복귀해야 한다');
{
    const R = run(makeRobot({ graspWillSucceed: false }),
                  { MODE: 'teach', TEACH_POSE: [400, 0, 250, 180, 0, 0] });
    check('에러(IN_3) 감지 로그', R.log.some(l => l.includes('그리퍼 에러(IN_3)')));
    check('"놓쳤다" 판정', R.log.some(l => l.includes('🔴 놓쳤다')));
    const ev = gripEvents(R);
    check('마지막 동작 = 대기 조합(열기) — 에러 후 대기위치 복귀', ev.length > 0 && ev[ev.length - 1].name === '__gripOpen',
          `이벤트 ${ev.map(c => c.args[2] || c.args[0]).join(',')}`);
    check('페이로드 복원 1.5', R.payload === 1.5);
    check('놓기(PLACE) 이동을 하지 않았다', R.calls.filter(c => c.name === 'moveLinear').length === 3,
          `moveLinear ${R.calls.filter(c => c.name === 'moveLinear').length}회 (접근·하강·상승만이어야)`);
}

console.log('\n⑬ 위치 번호를 바꾸면 조합도 따라 바뀌어야 한다 (대기5=1111 · 파지10=0111)');
{
    const R = run(makeRobot(), { MODE: 'gripper', GRIP_STANDBY_PT: 5, GRIP_GRASP_PT: 10 });
    const ev = gripEvents(R);
    check('닫기 = 파지10(0111)', ev.filter(c => c.name === '__gripClose' && c.args[1] === '0111').length === 3,
          `이벤트 ${ev.map(c => c.args[2]).join(',')}`);
    check('열기 = 대기5(1111)', ev.filter(c => c.name === '__gripOpen' && c.args[1] === '1111').length === 3);
    check('🚨 과도 패턴(파지5=0110 등)이 먹히지 않는다 — 입력시간 뒤에만 판정',
          ev.every(c => c.args[1] === '0111' || c.args[1] === '1111'),
          `이벤트 ${ev.map(c => c.args[2]).join(',')} · 9/3 시뮬이 잡은 실제 오작동 = GUI 입력시간을 0ms 로 두면 실물에서도 난다`);
}

console.log('\n⑭ 비교용 dio(툴 I/O) 모드는 여전히 동작한다 — 단 기본값이 아니다');
{
    const R = run(makeRobot(), { MODE: 'gripper', GRIPPER_MODE: 'dio' });
    const n = names(R);
    check('setToolDigitalOutput 6회', n.filter(x => x === 'setToolDigitalOutput').length === 6);
    check('본체 DO 는 건드리지 않는다', !n.includes('setGeneralDigitalOutput'));
    const src = require('fs').readFileSync(SCRIPT, 'utf8');
    check("스크립트 기본값이 'gen_dio'(교안 기준)", /^var GRIPPER_MODE\s*=\s*'gen_dio'/m.test(src));
}

console.log('\n⑮ 🥇 MODE iomap — DO 를 하나씩만 올려 채널을 판정한다 (9/4 첫 실행 · 로봇 안 움직임)');
{
    const R = run(makeRobot(), { MODE: 'iomap' });
    const n = names(R);
    check('moveLinear 호출 0건', !n.includes('moveLinear'));
    const sets = R.calls.filter(c => c.name === 'setGeneralDigitalOutput');
    // 한 시점에 High 인 DO 가 둘 이상이면 "조합"이 되어 단일 채널 판정이 아니다 — 마지막 대기1 이전까지 검사
    let live = [0, 0, 0, 0], maxHigh = 0, highs = [];
    for (const c of sets) { live[c.args[0]] = c.args[1]; const h = live.reduce((a, b) => a + b, 0); maxHigh = Math.max(maxHigh, h); if (c.args[1] === 1) highs.push(c.args[0]); }
    check('🚨 어느 시점에도 High 인 DO 는 1개 이하', maxHigh <= 1, `최대 동시 High ${maxHigh}`);
    check('DO0~3 을 각각 한 번씩 올렸다', [0, 1, 2, 3].every(ch => highs.filter(h => h === ch).length >= 1), `High 순서 ${highs.join(',')}`);
    check('각 채널마다 DI 세 개를 읽어 기록한다', R.log.filter(l => l.includes('IN_1(대기완료)=')).length === 4);
    check('마지막은 대기1(열림)으로 조우를 열어 둔다', R.gripOut.join('') === '1000', `최종 DO ${R.gripOut.join('')}`);
    check('로그에 열림/닫힘/무반응 해석 안내가 있다', R.log.some(l => l.includes('그리퍼 아님')));
}

console.log('\n⑯ 🚨 완료 신호가 "이미 High" — 전원 직후 IN_1 이 서 있으면 닫힌 조우를 열렸다고 오판하면 안 된다');
{
    // 가짜 그리퍼는 대기 명령에도 IN_1 을 계속 High 로 둔다(에지 없음) ⇒ 스크립트는 최소 동작시간을 채워야만 인정해야 한다
    // ⭐ 이 상황이 실제로 물리는 곳 = pickOne 의 첫 동작 "② 그리퍼 열기" (MODE gripper 는 닫기부터라 안 걸린다 — 첫 시도에서 그렇게 배웠다)
    const sumSleep = (R) => R.calls.filter(c => c.name === 'sleep').reduce((a, c) => a + c.args[0], 0);
    const T = { MODE: 'teach', TEACH_POSE: [400, 0, 250, 180, 0, 0] };
    const Rnorm = run(makeRobot(), T);
    const Redge = run(makeRobot({ readyHighAtStart: true }), T);
    const Rtear = run(makeRobot({ readyHighAtStart: true }), Object.assign({ GRIP_MIN_MOTION_S: 0 }, T));
    check('평상시(IN_1 Low 로 시작)는 즉시 인정 — 총 대기 < 1.0s', sumSleep(Rnorm) < 1.0, `${sumSleep(Rnorm).toFixed(2)}s`);
    check('⭐ IN_1 이 이미 High 면 최소 동작시간(1.0s)을 채운 뒤에만 하강한다 — 총 대기 ≥ 1.0s', sumSleep(Redge) >= 1.0, `${sumSleep(Redge).toFixed(2)}s`);
    check('🧪 그물 확인: GRIP_MIN_MOTION_S=0 이면 방어가 사라져 닫힌 조우로 즉시 하강한다(< 1.0s)', sumSleep(Rtear) < 1.0, `${sumSleep(Rtear).toFixed(2)}s`);
    check('에지 상황에서도 파지는 결국 성공한다', Redge.log.some(l => l.includes('✅ 파지 성공')));
    // 순서 검증: 열기 인정(대기 완료) 이 하강 moveLinear 보다 먼저인가 — 열기 전에 내려가면 충돌
    const idxOpen = Redge.calls.findIndex(c => c.name === '__gripOpen');
    const idxDown = Redge.calls.map((c, i) => [c, i]).filter(([c]) => c.name === 'moveLinear').map(([, i]) => i)[1]; // 2번째 이동 = 하강
    check('열림 이벤트가 하강 이동보다 먼저 기록된다', idxOpen >= 0 && idxDown !== undefined && idxOpen < idxDown, `open@${idxOpen} down@${idxDown}`);
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
