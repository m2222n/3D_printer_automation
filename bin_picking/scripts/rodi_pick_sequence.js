/* ============================================================================
 * 빈피킹 파지 시퀀스 (Rodi-Script) — 8/29(금) P3 / 9/1~ P4
 * ============================================================================
 *
 * 🎯 목적 = **로봇이 부품 한 개를 집는다.** 9/5 판정의 본체.
 *
 * ⭐ 이 파일이 서 있는 두 개의 검증된 토대
 *   ① 협력사 예시 `rodi_tcp_motion_client.js` — **801건 왕복이 검증된 소켓 경로**
 *      (그 골격을 그대로 쓴다. socketCreate → Open → WaitConnection → ReadLine → createPose → moveLinear)
 *   ② 한화 매뉴얼 `rodi_script_api_manual_ko.pdf` — 아래 모든 함수에 **쪽수를 달았다**
 *      🚨 근거 없는 함수는 쓰지 않았다. 기억으로 쓰면 현장에서 무너진다.
 *
 * 🚨🚨 실행 단계를 나눈 이유 = "조용히 틀리지 말고 크게 실패하라"
 *   같이 하면 실패했을 때 **어디가 문제인지 못 가린다**(8/14 *"플래그 빼면 좌우가
 *   뒤바뀌는데 무경고"* 와 같은 계열). 그래서 MODE 로 갈라놨다:
 *
 *     MODE 1 'gripper'  그리퍼만 개폐        — 로봇 안 움직임
 *     MODE 2 'teach'    사람이 넣은 좌표로 집기 — 인식 없음  ⭐ 8/29 P3 = 여기까지
 *     MODE 3 'vision'   소켓으로 받은 좌표로 집기 — 9/1~ P4
 *
 * ⚠️ 이 파일은 **현장 검증 전**이다(8/25 재택 작성). 값은 전부 확인 대상이다.
 * ========================================================================== */

/* ---------------------------------------------------------------------------
 * 0. 설정 — 🚨 금요일에 실물로 채울 자리
 * ------------------------------------------------------------------------- */

var MODE = 'gripper';          // 'gripper' | 'teach' | 'vision'  ← 단계별로 바꿔 실행

// --- 소켓 (MODE 'vision') ---
var SOCK      = 'vision';      // ⭐ 매뉴얼 예제의 소켓명이 실제로 'vision' (ko:172,175,178)
var SERVER_IP = 'SET_ME';      // 🚨 IPC 의 IP — 금요일에 `ipconfig` 로 확인해 채운다
                               //    (플레이스홀더다. 실제 값을 이 파일에 커밋하지 않는다)
var SERVER_PORT = 5000;        // pick_socket_server.py DEFAULT_PORT
var READ_TIMEOUT = 10000;      // 협력사 예시와 동일 10초

// --- 그리퍼 ---
// 🚨🚨 [확인필요] 배선이 3가지 후보다 (ko:58 / ko:123~124 / ko:181) — 금요일 실물 확인
//    A. 도구 디지털 I/O   setToolDigitalOutput      ← 가장 단순. 우선 이것으로 가정
//    B. RS485+ModbusRTU  robotToolIoRs485ModbusRtuWrite  ← 위치·힘 지정 가능(벌림 15점 활용)
//    C. 시리얼           serialSendString('gripper','OPEN')
var GRIPPER_MODE = 'dio';      // 'dio' | 'rs485' | 'serial'
var GRIP_DO_CH   = 0;          // 개폐 출력 채널 (ko:59 예제가 0)
var GRIP_DI_CH   = 1;          // ⭐ 파지 확인 입력 채널 (ko:59 예제가 1)
var GRIP_CLOSE_S = 0.5;        // 닫힘 대기 [s] — ko:59 예제는 0.3
var GRIP_OPEN_S  = 0.5;

// --- 모션 ---
var V_FAST = 100, A_FAST = 1000;   // 이동
var V_SLOW = 20,  A_SLOW = 100;    // ⭐ 접근/후퇴 — 협력사 예시 값(검증됨)

var APPROACH_DZ = 80;   // 목표 위 몇 mm 에서 접근 시작
var RETREAT_DZ  = 120;  // 집은 뒤 들어올릴 높이
var PLACE_POSE  = null; // 🚨 놓을 자리 — 금요일 티칭으로 채운다

// --- 페이로드 (ko:129) ---
// 🚨 setPayload 를 부품 잡을 때마다 갱신해야 충돌 감지가 정상 동작한다 (ko:129 원문)
var PAYLOAD_TOOL = 1.5;         // 그리퍼만 [kg] — JEGB-4285P
var PAYLOAD_PART = 0.05;        // 부품 1개 추정 [kg] 🚨 [확인필요] 실측 아님
var PART_COM     = { x: 0, y: 0, z: 50 };   // 무게중심 (ko:129 예제 형식)

// --- 티칭 좌표 (MODE 'teach') ---
// 🚨 금요일에 펜던트로 직접 티칭해 채운다. **추측값을 넣고 돌리지 말 것**
var TEACH_POSE = null;   // 예: [400, 0, 250, 180, 0, 0]

/* ---------------------------------------------------------------------------
 * 1. 그리퍼 — 배선 3경로를 한 함수로 감싼다
 * ------------------------------------------------------------------------- */

function gripperClose() {
    if (GRIPPER_MODE === 'dio') {
        setToolDigitalOutput(GRIP_DO_CH, 1);        // ko:59 "그리퍼 닫기"
    } else if (GRIPPER_MODE === 'serial') {
        serialSendString('gripper', 'CLOSE');       // ko:181
    } else {
        // 🚨 rs485 는 레지스터 맵이 그리퍼 제품 매뉴얼에 있다 — 확인 후 채운다
        console.log('🚨 rs485 경로 미구현 — 그리퍼 매뉴얼 레지스터 확인 필요');
        halt();
    }
    sleep(GRIP_CLOSE_S);
}

function gripperOpen() {
    if (GRIPPER_MODE === 'dio') {
        setToolDigitalOutput(GRIP_DO_CH, 0);        // ko:59 "그리퍼 열기"
    } else if (GRIPPER_MODE === 'serial') {
        serialSendString('gripper', 'OPEN');
    }
    sleep(GRIP_OPEN_S);
}

/**
 * ⭐⭐ 집었는지 로봇이 스스로 확인한다 (ko:59~60)
 * 매뉴얼 예제 원문이 정확히 *"그리퍼가 부품을 잡았는지 확인"* 이다.
 * 🎯 이것이 P5(10회 성공률)를 **사람이 세지 않게** 만든다.
 * ⚠️ [확인필요] JEGB-4285P 에 이 피드백 배선이 실제로 있는지 — 없으면 항상 0 이 온다.
 */
function isGrasped() {
    if (GRIPPER_MODE !== 'dio') return null;        // 판단 불가 → null (거짓과 구분)
    return getToolDigitalInput(GRIP_DI_CH) === 1;
}

/* ---------------------------------------------------------------------------
 * 2. 안전 이동 — 🚨 매 이동 전에 도달 가능한지 먼저 묻는다
 * ------------------------------------------------------------------------- */

/**
 * checkRunnableMotion(type, startPose, endPose, m_v, m_a, moveType)  ko:38~40
 * 🚨 startPose 가 **필수**다 — 목표만 주는 함수가 아니다(내가 처음 그렇게 적어 틀렸다).
 * ko:20 경고 = *"조인트 한계나 특이점 근처를 지나가는 직선 경로는 실패할 수 있다"*
 */
function safeMoveLinear(pose, v, a, label) {
    var here = getCurrentPose('tcp');               // ko:203
    if (!checkRunnableMotion('tcp', here, pose, v, a, 'linear')) {
        console.log('🔴 [' + label + '] 도달 불가 — 중단한다');
        return false;
    }
    moveLinear('tcp', pose, v, a);
    while (!isSteady()) sleep(10);                  // ko:205~206 정지 확인
    return true;
}

/** 같은 자리에서 z 만 띄운 포즈 */
function liftZ(pose, dz) {
    return [pose[0], pose[1], pose[2] + dz, pose[3], pose[4], pose[5]];
}

/* ---------------------------------------------------------------------------
 * 3. ⭐ 파지 1회 — 이 함수가 이 파일의 본체
 * ------------------------------------------------------------------------- */

function pickOne(target) {
    var above = liftZ(target, APPROACH_DZ);

    console.log('① 접근 상공  z+' + APPROACH_DZ);
    if (!safeMoveLinear(above, V_FAST, A_FAST, '접근상공')) return false;

    console.log('② 그리퍼 열기');
    gripperOpen();

    console.log('③ 하강 → 파지 위치');
    if (!safeMoveLinear(target, V_SLOW, A_SLOW, '하강')) return false;   // ⭐ 천천히

    console.log('④ 그리퍼 닫기');
    gripperClose();

    // ⭐⭐ 페이로드 갱신 — 들어올리기 **전에** 한다 (ko:129)
    setPayload(PAYLOAD_TOOL + PAYLOAD_PART, PART_COM);

    console.log('⑤ 상승  z+' + RETREAT_DZ);
    if (!safeMoveLinear(liftZ(target, RETREAT_DZ), V_SLOW, A_SLOW, '상승')) return false;

    // ⑥ 집었는지 확인 — 🚨 성공/실패를 여기서 가른다
    var ok = isGrasped();
    if (ok === null) {
        console.log('⑥ 파지 확인: ⚠️ 배선 없음 — 사람이 눈으로 판정');
    } else if (ok) {
        console.log('⑥ 파지 확인: 🟢 잡았다');
    } else {
        console.log('⑥ 파지 확인: 🔴 놓쳤다');
        setPayload(PAYLOAD_TOOL);                   // 무게 복원 (ko:129)
        gripperOpen();
        return false;
    }

    // ⑦ 놓기 — PLACE_POSE 가 없으면 들고만 있는다(현장 1차엔 이게 안전하다)
    if (PLACE_POSE) {
        console.log('⑦ 이송 → 놓기');
        if (!safeMoveLinear(liftZ(PLACE_POSE, RETREAT_DZ), V_FAST, A_FAST, '이송')) return false;
        if (!safeMoveLinear(PLACE_POSE, V_SLOW, A_SLOW, '놓기하강')) return false;
        gripperOpen();
        setPayload(PAYLOAD_TOOL);                   // 🚨 놓은 뒤 도구 무게로 복원 (ko:129)
        safeMoveLinear(liftZ(PLACE_POSE, RETREAT_DZ), V_SLOW, A_SLOW, '놓기후퇴');
    } else {
        console.log('⑦ PLACE_POSE 없음 — 들고 정지 (의도된 동작)');
    }
    return true;
}

/* ---------------------------------------------------------------------------
 * 4. MODE 별 실행
 * ------------------------------------------------------------------------- */

function runGripperOnly() {
    console.log('=== MODE 1: 그리퍼만 (로봇 안 움직임) ===');
    console.log('페이로드 = 도구만 ' + PAYLOAD_TOOL + 'kg');
    setPayload(PAYLOAD_TOOL);                       // ko:129
    var i;
    for (i = 0; i < 3; i++) {
        console.log('  ' + (i + 1) + '회 닫기');
        gripperClose();
        var g = isGrasped();
        console.log('    파지 입력 = ' + (g === null ? '배선없음' : g));
        console.log('  ' + (i + 1) + '회 열기');
        gripperOpen();
    }
    console.log('✅ 개폐 3회 — 눈으로 확인: 열고 닫히나');
}

function runTeach() {
    console.log('=== MODE 2: 티칭 좌표로 파지 (인식 없음) ===');
    if (!TEACH_POSE) {
        console.log('🔴 TEACH_POSE 가 비어 있다. 펜던트로 티칭한 좌표를 넣어라.');
        console.log('   🚨 추측값을 넣고 돌리지 말 것.');
        return;
    }
    setPayload(PAYLOAD_TOOL);
    var ok = pickOne(TEACH_POSE);
    console.log(ok ? '✅ 파지 성공' : '🔴 파지 실패');
}

function runVision() {
    console.log('=== MODE 3: 소켓 좌표로 파지 ===');
    console.log('🚨 hand-eye 캘리브가 끝난 뒤에만 실행한다.');

    // ⭐ 협력사 검증 골격 그대로
    socketCreate(SOCK, SERVER_IP, SERVER_PORT);     // ko:172
    socketOpen(SOCK);                               // 🚨 실패 시 7초 후 재시도 (ko:172)
    socketWaitConnection(SOCK, READ_TIMEOUT);       // ko:173

    var line = socketReadLine(SOCK, READ_TIMEOUT);  // ko:177
    var poses = JSON.parse(line);
    console.log('수신 ' + poses.length + '건');

    setPayload(PAYLOAD_TOOL);

    var okCount = 0, i, p, target;
    for (i = 0; i < poses.length; i++) {
        p = poses[i];
        target = createPose(p[0], p[1], p[2], p[3], p[4], p[5]);   // ko:196
        console.log('--- ' + (i + 1) + '/' + poses.length + ' ---');
        if (pickOne(target)) okCount++;
        if (PLACE_POSE === null) {
            console.log('🚨 PLACE_POSE 가 없어 1개만 시도하고 멈춘다');
            break;
        }
    }
    console.log('✅ 성공 ' + okCount + '/' + poses.length);

    socketSendLine(SOCK, 'DONE');                   // 협력사 규약
    socketDisconnect(SOCK);
}

/* ---------------------------------------------------------------------------
 * 5. main
 * ------------------------------------------------------------------------- */

console.log('MODE = ' + MODE + ' / 그리퍼 = ' + GRIPPER_MODE);

if (MODE === 'gripper')      runGripperOnly();
else if (MODE === 'teach')   runTeach();
else if (MODE === 'vision')  runVision();
else console.log('🔴 MODE 오류: ' + MODE);

/* ============================================================================
 * 📌 근거 색인 (전부 rodi_script_api_manual_ko.pdf)
 *
 *   ko:38~40  checkRunnableMotion(type, startPose, endPose, m_v, m_a, moveType) → boolean
 *   ko:58~60  setToolDigitalOutput(n, value) / getToolDigitalInput(n)
 *   ko:127~128 setToolCenterPoint(pose)      ← 그리퍼 달면 반드시. 우리 a_0115 Z=200
 *   ko:129    setPayload(payload, center)    ← 🚨 부품 잡을 때마다
 *   ko:131~132 setToolBoundingBox            ← 충돌 박스. 예제가 80×60×100(우리 그리퍼급)
 *   ko:172~178 socket*                      ← 예제 소켓명이 'vision'
 *   ko:196    createPose(x,y,z,rx,ry,rz)
 *   ko:203    getCurrentPose(type)
 *   ko:205~206 isSteady()
 *
 * 🚨 금요일에 채울 [확인필요] 5개
 *   1. 그리퍼 배선 = dio / rs485 / serial 중 무엇인가        (GRIPPER_MODE)
 *   2. 파지 확인 입력 배선이 있는가                          (GRIP_DI_CH)
 *   3. IPC IP                                              (SERVER_IP)
 *   4. TEACH_POSE · PLACE_POSE 티칭값
 *   5. 부품 무게 실측                                       (PAYLOAD_PART)
 *
 * ⚠️ 아직 하지 않은 것 = setToolCenterPoint / setToolBoundingBox 호출.
 *    TCP 는 펜던트에 이미 a_0115(Z=200)가 등록돼 있어 **덮어쓰면 위험**하므로
 *    현장에서 현재 등록값을 확인한 뒤 결정한다.
 * ========================================================================== */
