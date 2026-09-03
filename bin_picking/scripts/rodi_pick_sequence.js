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

var MODE = 'gripper';          // 'iomap' | 'gripper' | 'teach' | 'vision'  ← 단계별로 바꿔 실행 (9/4 첫 실행은 'iomap')

// --- 소켓 (MODE 'vision') ---
var SOCK      = 'vision';      // ⭐ 매뉴얼 예제의 소켓명이 실제로 'vision' (ko:172,175,178)
var SERVER_IP = 'SET_ME';      // 🚨 IPC 의 IP — 금요일에 `ipconfig` 로 확인해 채운다
                               //    (플레이스홀더다. 실제 값을 이 파일에 커밋하지 않는다)
var SERVER_PORT = 5000;        // pick_socket_server.py DEFAULT_PORT
var READ_TIMEOUT = 10000;      // 협력사 예시와 동일 10초

// --- 그리퍼 (주강로보테크 JEGB-4285P-3MA) ---
// 🚨🚨 [9/3 태민님 지시] 그리퍼 작업 기준 = 주강로보테크 교안. 아래 근거는 전부 `교안:쪽`(Electric Gripper Quick Guide).
//   교안:5   핀 표(CONTROLLER 기준) = A/B 24V·0V · C/D RS485± · E~G IN_1~3(그리퍼→컨트롤러 **상태**)
//             · H~M OUT_1~5(컨트롤러→그리퍼 **명령**) · 쉴드. 케이블 = 6페어 12선(9/2 사진 `6P×24AWG`와 정합)
//             협력사 손글씨 = IN_1→DI0 · IN_2→DI1 · IN_3→DI2 · OUT_1~4→DO0~3 · "PNP"   [사진 판독 · 9/4 펜던트로 확인]
//   교안:6   🚨🚨 OUT-1~4 는 **단일 채널 열기/닫기가 아니라 4비트 신호조합**으로 15위치(대기 5 + 파지 10)를 고른다
//   교안:5   🚨 RS-485 는 "GUI 설정(힘·위치·속도) 전용" ⇒ **런타임 제어 경로가 아니다** ⇒ rs485 모드는 보류
//   교안:18  위치·속도·토크는 GUI Data Table 에서 설정(기본 = 대기 85.00mm · 파지 설정위치 3.05mm · 80%/80% · 50ms)
//   교안:22  파지 판정 = 설정위치 < 실제 파지위치 < 외측파지범위 ⇒ IN_2(파지 완료) High / 밖이면 IN_3(에러)
//   교안:25  🚨 에러 시 **반드시 대기위치로 이동 후 다음 동작**
//   ⇒ 컨트롤러 본체 일반 I/O = setGeneralDigitalOutput(n) §3.1.1 ko:53 / getGeneralDigitalInput(n) §3.1.2 ko:54
//   ⇒ 옛 'dio'(툴 플랜지 I/O 1채널·ko:59 예제)는 이 그리퍼의 배선·명령 방식 둘 다와 어긋난다. 비교용으로만 남긴다.
var GRIPPER_MODE = 'gen_dio';  // 'gen_dio'(교안 기준·기본) | 'dio'(툴 I/O 1채널·비교용) | 'rs485'(교안상 GUI 전용→보류) | 'serial'

// 컨트롤러 채널 배정 — 🚨🚨 [9/3 Fable 재판독] 교안:5 한 장에 **번호 체계가 셋** 겹쳐 있어 문서로는 확정이 안 된다:
//   ⓐ JRT 인쇄 배선도(예시) = OUT_1→DO1 · OUT_2→DO0 · OUT_3→DO2 · OUT_4→DO3 · OUT_5→DO4  ← 🚨 OUT_1/OUT_2 가 우리 가정과 뒤바뀜
//   ⓑ 협력사 손글씨(표 안)   = IN_1→0 · IN_2→1 · IN_3→2 / OUT_1→"01" · OUT_2→"02" · OUT_3→"03" · OUT_4→(지움)"F0" · OUT_5→"F1"
//      ⇒ "DO1·DO2·DO3 + Flexible I/O 0" 로도 읽힌다 = 이 경우 **DO0 은 그리퍼가 아니다**(0000 = 명령 없음이 되어 "안 움직임")
//   ⓒ 협력사 손글씨(여백)   = DI0/1/2 옆 ⑤⑥⑦ · DO0~3 옆 3·4·5·6 = 한화 IO MAP 보드 **단자 번호**로 추정 [미확인]
//   우리 7/27 기록 `D_GEN_OUT_0~3 = OUT-1~4` 는 협력사 인터페이스 문서 기준 ⇒ 아래 기본값은 그것을 따른다.
//
// ⭐⭐ 그런데 교안:6 조합표는 **OUT_1↔OUT_2 를 맞바꿔도 대기/파지 결과가 전부 같다**(대칭) — 그리고 OUT_3↔OUT_4 도 같다
//    (1000↔0100 둘 다 대기 · 0010↔0001 둘 다 파지 · 3비트도 전부 같은 부류). 기본값(대기 전부 85.00 · 파지 전부 3.05)에서는
//    ⇒ 📌 **"어느 DO 들이 열고 어느 DO 들이 닫나"만 맞으면 순서는 틀려도 동작한다.** ⓐ 처럼 뒤바뀌어도 무해.
//    🚨 무해하지 않은 경우 = ⓑ (DO0 이 그리퍼가 아니고 DO2 가 OUT_2=대기 = **"닫아라" 했는데 열린다**)
//    ⇒ 그래서 9/4 첫 작업 = MODE 'iomap' 으로 DO 하나씩 올려 **열림/닫힘/무반응**을 눈으로 기록한다.
// 🚨🚨 토글 전 확인 = 9/2 사진에서 **공압 매니폴드(JIG GRIP·ROBO GRIP·BLOW) 배선 라벨이 `DO 0`·`DO 2`·`FO D`** 였다.
//    그 DO 가 로봇 D_GEN_OUT 이면 토글 순간 **지그 클램프·에어블로가 동작**한다 ⇒ 제어반 단자대(`DI 0~5·DO 0~4·FI/FO·IN-1~3`)에서
//    그리퍼 6페어가 어느 DO 에 물렸는지 **눈으로 먼저 따라가고**, 토글은 그 채널만 한다.
var GRIP_OUT_CH = [0, 1, 2, 3];                          // OUT-1..OUT-4 → D_GEN_OUT_n  ← 🅐 iomap 결과로 고친다
var GRIP_IN_CH  = { ready: 0, grasped: 1, error: 2 };    // IN_1(원점·대기 완료)→DI0 · IN_2(파지 완료)→DI1 · IN_3(에러)→DI2
var IOMAP_DO_CANDIDATES = [0, 1, 2, 3];                  // MODE 'iomap' 이 올려볼 DO — 🚨 단자대 추적 후 그리퍼 선만 남긴다
var IOMAP_DWELL_S = 1.5;                                 // 한 채널 High 유지 시간(눈으로 볼 시간)
// 🥇🥇 기본값(1번) 그대로 27종을 커버한다 — 9/3 DB 전수 대조로 확인. GUI 설정 없이 금요일 진행 가능.
//   교안:18 공장 기본값 = 설정위치 3.05 / 외측파지범위 85.00 / 내측 0.00 / 속도 80 / 토크 80 / 입력시간 50ms
//   교안:22 파지완료 판정 = 설정위치 < 파지위치 < 외측파지범위  (= 3.05 ~ 85.00 구간)
//   ✅ grasp_database.yaml 실측: pickable 20종 파지폭 17.50~69.00mm ⇒ 전부 이 구간 안 (상한까지 16mm 여유)
//      · 3.05 이하 0종(최소 4.80 bracket_sensor2) · 85.00 초과는 top_inner_sheet004 88.98 하나뿐이나 not_pickable+DB전용
//   ⇒ 📌 8/10 "벌림 19가지→15점 묶기"는 불필요해 보인다. 단 근거가 바뀌었다:
//        ~~rs485로 폭 지정~~(교안상 RS-485는 GUI 전용이라 닫힘) → **판정 창이 이미 전 구간이라서**
//   🚨 "판정 통과"가 "집힌다"는 뜻은 아니다 — 힘·얇은 판 눌림은 실물에서만 답난다(교안:18 = 무른 물체는 속도·토크를 낮춘다)
var GRIP_STANDBY_PT = 1;        // 열기 = 대기위치 번호 1~5  (GUI 설정값 · 기본 85.00mm = 완전 개방)
var GRIP_GRASP_PT   = 1;        // 닫기 = 파지위치 번호 1~10 (설정위치 = "파지 못하고 멈추는" 에러 위치 · 기본 3.05mm)
var GRIP_INPUT_TIME_S = 0.05;   // 교안:24 입력시간 기본 50ms — 조합 출력 후 이만큼 유지한 뒤 완료 신호를 본다
                                //   ⭐ 교안:24 = 대기[1],[2]/파지[1],[2]는 단일 비트라 "신호조합이 필요 없어 입력시간을 낮게" ⇒ 우리(대기1·파지1)는 0ms 도 된다
var GRIP_TIMEOUT_S    = 3.0;    // 완료 신호(IN_1/IN_2) 대기 상한 [확인필요 — 교안에 값 없음, 실측 후 조정]
// 🚨🚨 [9/3 Fable] 완료 신호가 "이미 High" 일 수 있다 — 교안:5 IN_1 = "원점 이동 완료(초기 1회) **및** 대기위치 이동 완료".
//   전원 투입 직후 그리퍼는 원점(0mm·완전 닫힘, 교안:25)까지 스스로 가고 IN_1 을 올려 둔다. 그 상태에서 대기1 을 명령하면
//   IN_1 이 **내려갔다 다시 오르는지, 아니면 계속 High 인지** 교안에 없다 [확인필요].
//   계속 High 면 gripCommand 가 **조우가 아직 닫힌 채로 즉시 true** 를 돌려주고 로봇이 닫힌 조우로 하강한다 = 충돌.
//   ⇒ 방어 = ①완료 신호가 한 번 Low 로 내려간 것을 봤으면 즉시 인정 ②못 봤으면 최소 동작시간을 채운 뒤에만 인정.
var GRIP_MIN_MOTION_S = 1.0;    // 85mm 스트로크 이동에 걸릴 최소 시간 [확인필요 — 실측 후 줄인다]

// 교안:6 신호조합표 (적용 모델 JEGB·JEGC·JEGD·JEGH) — 행 = [OUT-1, OUT-2, OUT-3, OUT-4], 1=High
// 🚨 표를 옮겨 적은 것이다. 바꾸지 말 것. all-Low(0000)는 표에 없다(= 명령 없음).
var GRIP_COMBO = {
    standby: [ [1,0,0,0], [0,1,0,0], [1,1,0,0], [1,1,1,0], [1,1,1,1] ],                      // 대기 1~5
    grasp:   [ [0,0,1,0], [0,0,0,1], [1,0,1,0], [1,0,0,1], [0,1,1,0],
               [0,1,0,1], [0,0,1,1], [1,1,0,1], [1,0,1,1], [0,1,1,1] ]                        // 파지 1~10
};

// (비교용 'dio' 모드 전용) 툴 플랜지 I/O 1채널 — ko:59 예제값
var GRIP_DO_CH   = 0;
var GRIP_DI_CH   = 1;
var GRIP_CLOSE_S = 0.5;        // 닫힘 대기 [s] — ko:59 예제는 0.3
var GRIP_OPEN_S  = 0.5;

// --- RS485 (GRIPPER_MODE === 'rs485' 일 때만) ---
// 근거 = ko:115(robotToolIoRs485Set 시그니처) · ko:117(예제) · ko:123~124(ModbusRtu Read/Write)
var RS485_ROBOT_ID  = 1;
var RS485_BAUD      = 'BAUDRATE_115200';   // 🚨 [확인필요] 그리퍼 기본값과 맞아야 한다
var RS485_FRAME     = 'FRAME_8N1';         // 🚨 [확인필요]
var RS485_SCAN_RATE = 100;                 // ko:117 예제값
var GRIP_SLAVE_ADDR = 1;                   // 🚨 [확인필요] Modbus 슬레이브 주소(1~247)

// 🚨🚨 **이 그리퍼(JEGB-4285P-3MA)의 레지스터 맵은 우리 기록에 없다.**
//    제조사 카탈로그 미확보 상태다(reference_gripper_jegb4285.md 확인필요 ④).
//    ⇒ 📌 **null 로 둔다. 추측 주소를 넣지 않는다.** 채워지면 rs485 경로가 살아난다.
//    ⭐ 채우는 법 = 그리퍼 제품 매뉴얼의 "Modbus 레지스터 맵" 표를 그대로 옮긴다.
var GRIP_REG = {
    cmd:      null,   // 개폐 명령 레지스터 주소   (예: 0x0100)
    openVal:  null,   // 열기 명령 값
    closeVal: null,   // 닫기 명령 값
    width:    null,   // ⭐ 목표 벌림 폭 레지스터 (있으면 15점 묶기가 불필요해진다)
    force:    null,   // 파지력 레지스터 (15~150N 프로그래머블)
    status:   null    // 상태(파지 여부) 레지스터
};
var GRIP_TARGET_WIDTH = null;   // [mm 또는 제품 단위] 🚨 단위는 매뉴얼 확인
var GRIP_TARGET_FORCE = null;   // [N 또는 제품 단위]

// --- 드릴링 (MODE 'drill') — 🚨 [9/4 뼈대] 9/2 지시 "하나를 집어서 드릴링까지". 9/4 현장 확인 3개로 채운다 ---
//   ①10L 펜던트에 협력사 드릴 프로그램이 있나 → 있으면 DRILL_SUBPROGRAM 에 이름을 적고 우리는 "집어서 넘기기"만 한다
//   ②스핀들 ON 신호 = 펜던트 이름 `D_CONF_OUT_2`(14k 드릴 2개) / `_3`(24k 연마) — 🚨 Rodi-Script 함수명 [확인필요]:
//     ko:53 I/O 종류 표 = General / Redundant(안전 이중화) / Tool / Safeguard 넷뿐이고 "Configurable"이 없다.
//     ⇒ D_CONF_OUT 이 setRedundantDigitalOutput(ko:53 §3.1.4)인지 setGeneralDigitalOutput 의 다른 번호인지 펜던트 I/O 모니터에서 갈라야 한다.
//     ⇒ 📌 그래서 기본값 SPINDLE_API='none' = **호출하지 않고 로그만 남긴다.** 추측 함수로 스핀들을 돌리지 않는다.
//   ③드릴 비트(ø3.0 · 데모 부품 02_sol_block_b = 관통 수직 홀 10개 · 리그립 불필요) — 콜렛이 비어 있었다(9/2)
var DRILL_SUBPROGRAM = null;       // 협력사 드릴 프로그램 이름(있으면) — 서브프로그램 호출 함수명도 [확인필요]
var SPINDLE_API      = 'none';     // 'none'(로그만) | 'redundant'(setRedundantDigitalOutput) | 'general'(setGeneralDigitalOutput)
var SPINDLE_CH       = 2;          // D_CONF_OUT_2 = 14k 드릴 스핀들 2개(모터 1개에 묶임 · 8/31 협력사 확인)
var SPINDLE_SPINUP_S = 3.0;        // ON 뒤 정속까지 [확인필요 — 인버터 가속 시간]
var DRILL_POSE       = null;       // 드릴 스테이션 위 대기 자세(부품을 물고) — 🚨 티칭으로 채운다
var DRILL_DEPTH_MM   = 0;          // 진입 깊이(0 = 진입 안 함 · 스핀들 ON/OFF 만 시험)
var DRILL_FEED_V     = 5, DRILL_FEED_A = 20;   // 진입 속도 — 매우 느리게 [확인필요]
var DONE_BIN_POSE    = null;       // 완료 빈 — 티칭

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

/**
 * ⭐⭐ RS485 초기화 — MODE 'rs485' 를 쓰기 전에 반드시 한 번 부른다.
 * 근거 = rodi_script_api_manual_ko.pdf:115(시그니처) · :117(예제 원문 그대로)
 *   robotToolIoRs485Set(robotId, serialInterface, baudrate, dataFrame,
 *                       protocol, txContinuousEnable, txScanRate)
 * 🚨 매뉴얼 :123 = *"robotToolIoRs485Set 에서 프로토콜을 'MODBUS_RTU'로 설정한 후 사용해야 한다"*
 * ⭐ CRC 는 로봇이 내부에서 자동 처리한다(:123 원문) ⇒ 우리가 CRC 를 만들지 않는다.
 */
function rs485Init() {
    robotToolIoRs485Set(
        RS485_ROBOT_ID,
        'RS485',            // :115 옵션 = UNDEFINED|RS422|RS422_120OHM|RS485|RS485_120OHM
        RS485_BAUD,         // :115 옵션 = 'BAUDRATE_115200' 등
        RS485_FRAME,        // 예: 'FRAME_8N1'
        'MODBUS_RTU',       // :117 옵션 = STANDARD|MODBUS_RTU|MODBUS_ASCII
        false,              // txContinuousEnable
        RS485_SCAN_RATE     // txScanRate
    );
    console.log('RS485 초기화: ' + RS485_BAUD + ' ' + RS485_FRAME + ' MODBUS_RTU');
}

/**
 * 그리퍼 레지스터에 한 워드 쓰기 (Modbus function 6 = single register write)
 * 근거 = ko:124 예제 `robotToolIoRs485ModbusRtuWrite(1, 1, 6, 0x10, 1, [0x00, 0x01])`
 * 🚨 txData 는 **바이트 배열**이다(하이바이트 먼저) — 워드 하나가 2바이트다.
 */
function gripWriteReg(addr, value) {
    var hi = (value >> 8) & 0xFF;
    var lo = value & 0xFF;
    robotToolIoRs485ModbusRtuWrite(
        RS485_ROBOT_ID, GRIP_SLAVE_ADDR, 6, addr, 1, [hi, lo]
    );
}

/** 그리퍼 레지스터 읽기 (function 3 = holding register read) — 근거 ko:123 */
function gripReadReg(addr, count) {
    return robotToolIoRs485ModbusRtuRead(
        RS485_ROBOT_ID, GRIP_SLAVE_ADDR, 3, addr, count, 8
    );
}

/**
 * 🚨🚨 레지스터 주소·값이 채워져 있는지 검사한다.
 * ⭐ 이 그리퍼(JEGB-4285P-3MA)의 **레지스터 맵은 우리 기록에 없다**
 *    (제조사 카탈로그 미확보 — memory/reference_gripper_jegb4285.md 확인 필요 항목 ④).
 * ⇒ 📌 **추측한 주소로 쓰지 않는다.** 모르는 채로 쓰면 엉뚱한 레지스터를 건드린다.
 */
function rs485MapReady() {
    return GRIP_REG.cmd !== null && GRIP_REG.openVal !== null && GRIP_REG.closeVal !== null;
}

/* ---- gen_dio: 교안:5~6 신호조합 방식 ------------------------------------ */

/** OUT-1~4 에 조합 한 행을 쓴다 (§3.1.1 ko:53) */
function gripSetCombo(row) {
    var i;
    for (i = 0; i < 4; i++) {
        setGeneralDigitalOutput(GRIP_OUT_CH[i], row[i]);
    }
}

/** IN_1~3 읽기 (§3.1.2 ko:54) — key = 'ready' | 'grasped' | 'error' */
function gripReadIn(key) {
    return getGeneralDigitalInput(GRIP_IN_CH[key]) === 1;
}

/**
 * 조합 출력 → 입력시간 유지(교안:24) → 완료 신호 대기.
 * ⭐ 시간으로 기다리지 않고 **그리퍼가 주는 완료 신호(IN_1/IN_2)로 판정**한다 — 교안이 그렇게 설계돼 있다.
 * 🚨 IN_3(에러)가 서면 즉시 false — 교안:25 "에러 시 반드시 대기위치로 이동 후 다음 동작"은 호출자가 gripperOpen()으로 수행.
 */
function gripCommand(row, doneKey, label) {
    // ⭐ 명령 전에 완료 신호가 이미 서 있는지 본다 — 서 있으면 "내려갔다 오르는 에지"를 기다려야 진짜 완료다
    var wasHigh = gripReadIn(doneKey);
    var sawLow  = !wasHigh;
    gripSetCombo(row);
    sleep(GRIP_INPUT_TIME_S);
    var waited = 0;
    while (waited < GRIP_TIMEOUT_S) {
        if (gripReadIn('error')) {
            console.log('🔴 그리퍼 에러(IN_3) — ' + label + ' · 교안:25 = 대기위치로 복귀 후 재시도');
            return false;
        }
        var hi = gripReadIn(doneKey);
        if (!hi) sawLow = true;
        // 인정 조건 = High 이고 (한 번 Low 를 봤거나 · 최소 동작시간이 지났거나)
        if (hi && (sawLow || waited >= GRIP_MIN_MOTION_S)) return true;
        sleep(0.05);
        waited += 0.05;
    }
    console.log('⚠️ 그리퍼 완료 신호(' + doneKey + ') 대기 초과 ' + GRIP_TIMEOUT_S + 's — ' + label
                + ' · 배선(DI' + GRIP_IN_CH[doneKey] + ')·조합·채널 배정을 의심');
    return false;
}

function gripperClose() {
    if (GRIPPER_MODE === 'gen_dio') {
        // 교안:6 파지 n 조합 → 교안:22 설정위치 < 파지위치 < 외측파지범위 이면 IN_2(파지 완료)
        return gripCommand(GRIP_COMBO.grasp[GRIP_GRASP_PT - 1], 'grasped', '파지' + GRIP_GRASP_PT);
    }
    if (GRIPPER_MODE === 'dio') {
        setToolDigitalOutput(GRIP_DO_CH, 1);        // ko:59 "그리퍼 닫기" — 🚨 이 그리퍼엔 안 맞는 방식(비교용)

    } else if (GRIPPER_MODE === 'serial') {
        serialSendString('gripper', 'CLOSE');       // ko:181

    } else if (GRIPPER_MODE === 'rs485') {
        // 🚨 교안:5 = RS-485 는 GUI 설정 전용. 이 분기는 제조사가 런타임 Modbus 를 확인해 줄 때까지 보류.
        if (!rs485MapReady()) {
            console.log('🔴 rs485 레지스터 맵이 비어 있다 — 교안:5 상 RS-485 는 GUI 전용이라 맵 자체가 없을 수 있다.');
            console.log('   🚨 추측 주소로 쓰지 않는다(엉뚱한 레지스터를 건드린다).');
            console.log('   ⭐ 대안 = GRIPPER_MODE 를 "gen_dio"(교안 기준) 로 두고 진행한다.');
            return false;
        }
        // ⭐ 폭을 지정할 수 있으면 지정한다 = rs485 를 쓰는 이유가 이것이다
        if (GRIP_REG.width !== null && GRIP_TARGET_WIDTH !== null) {
            gripWriteReg(GRIP_REG.width, GRIP_TARGET_WIDTH);
        }
        if (GRIP_REG.force !== null && GRIP_TARGET_FORCE !== null) {
            gripWriteReg(GRIP_REG.force, GRIP_TARGET_FORCE);
        }
        gripWriteReg(GRIP_REG.cmd, GRIP_REG.closeVal);

    } else {
        console.log('🔴 알 수 없는 GRIPPER_MODE: ' + GRIPPER_MODE);
        return false;
    }
    sleep(GRIP_CLOSE_S);
    return true;
}

function gripperOpen() {
    if (GRIPPER_MODE === 'gen_dio') {
        // 교안:6 대기 n 조합 → IN_1(원점·대기위치 이동 완료). 🚨 닫기와 반드시 쌍으로(9/1 rs485 구멍 교훈)
        return gripCommand(GRIP_COMBO.standby[GRIP_STANDBY_PT - 1], 'ready', '대기' + GRIP_STANDBY_PT);
    }
    if (GRIPPER_MODE === 'dio') {
        setToolDigitalOutput(GRIP_DO_CH, 0);        // ko:59 "그리퍼 열기"

    } else if (GRIPPER_MODE === 'serial') {
        serialSendString('gripper', 'OPEN');

    } else if (GRIPPER_MODE === 'rs485') {
        // 🚨🚨 여기가 원래 **분기 자체가 없어서 조용히 안 열렸다**(9/1 발견).
        //    닫기는 halt() 로 크게 실패했는데 열기는 아무 일도 안 하고 통과했다
        //    ⇒ ⭐ 부품을 문 채로 다음 단계로 갔다 = 가장 위험한 형태.
        if (!rs485MapReady()) {
            console.log('🔴 rs485 레지스터 맵 없음 — 열기를 수행하지 못했다.');
            console.log('   🚨 그리퍼가 닫힌 채로 남아 있을 수 있다. 펜던트에서 수동으로 열어라.');
            return false;
        }
        gripWriteReg(GRIP_REG.cmd, GRIP_REG.openVal);

    } else {
        console.log('🔴 알 수 없는 GRIPPER_MODE: ' + GRIPPER_MODE);
        return false;
    }
    sleep(GRIP_OPEN_S);
    return true;
}

/**
 * ⭐⭐ 집었는지 로봇이 스스로 확인한다 (ko:59~60)
 * 매뉴얼 예제 원문이 정확히 *"그리퍼가 부품을 잡았는지 확인"* 이다.
 * 🎯 이것이 P5(10회 성공률)를 **사람이 세지 않게** 만든다.
 * ⚠️ [확인필요] JEGB-4285P 에 이 피드백 배선이 실제로 있는지 — 없으면 항상 0 이 온다.
 */
function isGrasped() {
    if (GRIPPER_MODE === 'dio') {
        return getToolDigitalInput(GRIP_DI_CH) === 1;
    }
    if (GRIPPER_MODE === 'gen_dio') {
        return gripReadIn('grasped');               // 교안:5 IN_2 "파지 완료" = DI1(손글씨) · §3.1.2 ko:54
    }
    if (GRIPPER_MODE === 'rs485' && GRIP_REG.status !== null) {
        // ⭐ rs485 면 상태 레지스터로 읽는다 — dio 보다 정보가 많다(폭·파지 여부)
        var r = gripReadReg(GRIP_REG.status, 1);
        if (!r || r.length < 2) return null;
        return ((r[0] << 8) | r[1]) !== 0;          // 🚨 [확인필요] 판정 규칙은 제품 매뉴얼
    }
    return null;                                    // ⭐ 판단 불가 → null (거짓과 구분)
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

/**
 * ⭐ 배선 방식에 따라 필요한 초기화를 한다. 모든 MODE 앞에 부른다.
 * 🚨 rs485 는 robotToolIoRs485Set 을 먼저 호출해야 ModbusRtu 헬퍼가 동작한다(ko:123).
 */
function gripperInit() {
    if (GRIPPER_MODE === 'gen_dio') {
        console.log('그리퍼 = 교안 신호조합 · OUT-1~4 → DO' + GRIP_OUT_CH.join('/DO')
                    + ' · IN_1~3 → DI' + GRIP_IN_CH.ready + '/DI' + GRIP_IN_CH.grasped + '/DI' + GRIP_IN_CH.error
                    + ' · 대기' + GRIP_STANDBY_PT + ' / 파지' + GRIP_GRASP_PT);
    }
    if (GRIPPER_MODE === 'rs485') {
        rs485Init();
        if (!rs485MapReady()) {
            console.log('⚠️  rs485 를 골랐으나 레지스터 맵이 비어 있다(교안:5 상 RS-485 는 GUI 전용).');
            console.log('   ⭐ GRIPPER_MODE="gen_dio" 로 되돌려라.');
        }
    }
}

/**
 * MODE 0 'iomap' — 🥇 9/4 첫 작업. DO 를 **하나씩** 올려 그리퍼가 열리나/닫히나/무반응인지 눈으로 기록한다.
 * 교안:6 = 단일 High 는 OUT_1→대기1(열림) · OUT_2→대기2(열림) · OUT_3→파지1(닫힘) · OUT_4→파지2(닫힘)
 * ⇒ 열리는 DO 두 개 = {OUT_1,OUT_2} · 닫히는 DO 두 개 = {OUT_3,OUT_4} · 무반응 = 그리퍼가 아니다(다른 장비일 수 있다!)
 * ⭐ 기본값에서는 열림 둘·닫힘 둘의 **안 순서는 구별도 안 되고 필요도 없다**(조합표가 대칭) ⇒ 열림 둘을 OUT_1/2 로, 닫힘 둘을 OUT_3/4 로 적으면 끝.
 * 🚨 로봇은 안 움직인다. 🚨 한 채널 끝날 때마다 반드시 Low 로 되돌린다(마지막 상태가 남으면 다음 시험이 오염된다).
 * 🚨🚨 공압 매니폴드 라벨 `DO 0`·`DO 2` — 그 DO 가 로봇 D_GEN_OUT 이면 지그 클램프가 움직인다. 단자대 추적 후에만 실행.
 */
function runIoMap() {
    console.log('=== MODE 0: I/O 채널 판정 (로봇 안 움직임 · DO 하나씩) ===');
    console.log('🚨 제어반 단자대에서 그리퍼 6페어가 물린 DO 만 IOMAP_DO_CANDIDATES 에 남겼는지 확인했나?');
    var i, ch, r1, r2, r3;
    for (i = 0; i < IOMAP_DO_CANDIDATES.length; i++) {
        ch = IOMAP_DO_CANDIDATES[i];
        // 전부 Low 로 시작 — 겹치면 조합이 되어 판정이 흐려진다
        var j;
        for (j = 0; j < IOMAP_DO_CANDIDATES.length; j++) setGeneralDigitalOutput(IOMAP_DO_CANDIDATES[j], 0);
        sleep(GRIP_INPUT_TIME_S);
        console.log('--- DO' + ch + ' 만 High (' + IOMAP_DWELL_S + 's) — 👁️ 그리퍼가 열리나 / 닫히나 / 가만히 있나 ---');
        setGeneralDigitalOutput(ch, 1);
        sleep(IOMAP_DWELL_S);
        r1 = gripReadIn('ready'); r2 = gripReadIn('grasped'); r3 = gripReadIn('error');
        console.log('    DI 상태: IN_1(대기완료)=' + (r1 ? 1 : 0) + ' IN_2(파지완료)=' + (r2 ? 1 : 0) + ' IN_3(에러)=' + (r3 ? 1 : 0));
        console.log('    해석: IN_1↑=열림(OUT_1 또는 OUT_2) · 빈손이면 IN_3↑=닫힘(OUT_3 또는 OUT_4) · 셋 다 0 이고 안 움직임=그리퍼 아님');
        setGeneralDigitalOutput(ch, 0);
        sleep(GRIP_INPUT_TIME_S);
    }
    console.log('✅ 끝 — 열림 DO 두 개를 GRIP_OUT_CH[0],[1] 에, 닫힘 DO 두 개를 [2],[3] 에 적고 MODE=gripper 로 간다');
    console.log('   ⚠️ 마지막으로 대기1(열림)을 한 번 보내 조우를 열어 둔다');
    gripperOpen();
}

function runGripperOnly() {
    console.log('=== MODE 1: 그리퍼만 (로봇 안 움직임) ===');
    console.log('배선 = ' + GRIPPER_MODE);
    console.log('페이로드 = 도구만 ' + PAYLOAD_TOOL + 'kg');
    gripperInit();
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

/* ---------------------------------------------------------------------------
 * 3-B. 드릴링 뼈대 (MODE 'drill') — 🚨 9/4 확인 3개(협력사 프로그램·스핀들 함수명·비트)로 채운다
 * ------------------------------------------------------------------------- */

/** 스핀들 ON/OFF — 🚨 SPINDLE_API 가 'none' 이면 **호출하지 않고 로그만**(함수명 미확정 상태에서 스핀들을 돌리지 않는다) */
function spindle(on) {
    var v = on ? 1 : 0;
    if (SPINDLE_API === 'redundant') {
        setRedundantDigitalOutput(SPINDLE_CH, v);              // ko:53 §3.1.4 — D_CONF_OUT 이 이것인지 [확인필요]
    } else if (SPINDLE_API === 'general') {
        setGeneralDigitalOutput(SPINDLE_CH, v);                // §3.1.1 — 다른 번호일 수 있다 [확인필요]
    } else {
        console.log('⚠️ 스핀들 ' + (on ? 'ON' : 'OFF') + ' — SPINDLE_API="none" 이라 호출 안 함(로그만). 펜던트 I/O 모니터로 함수명 확정 후 바꾼다');
        return false;
    }
    console.log('스핀들 ' + (on ? 'ON' : 'OFF') + ' (' + SPINDLE_API + ' ch' + SPINDLE_CH + ')');
    return true;
}

/**
 * 집은 부품을 드릴 스테이션으로 가져가 (스핀들 ON → 진입 → 후퇴 → OFF) 완료 빈에 놓는다.
 * 🚨 pickOne 이 성공(부품을 물고 상승)한 직후에만 부른다. DRILL_POSE 가 없으면 아무것도 하지 않는다.
 * ⭐ 안전 순서 = 스핀들은 **부품을 문 상태에서만 ON**, **후퇴가 끝난 뒤 OFF**, 그리퍼는 **OFF 뒤에만 연다**.
 */
function drillOne() {
    if (!DRILL_POSE) {
        console.log('🔴 DRILL_POSE 가 비어 있다 — 드릴 스테이션 위 자세를 티칭해 넣어라. 추측값 금지.');
        return false;
    }
    if (DRILL_SUBPROGRAM) {
        console.log('ℹ️ 협력사 드릴 프로그램 "' + DRILL_SUBPROGRAM + '" 이 있다 — 서브프로그램 호출 함수명 [확인필요]. 아래 자체 시퀀스는 건너뛴다.');
        return false;
    }
    console.log('⑧ 드릴 스테이션 상공으로 이송');
    if (!safeMoveLinear(liftZ(DRILL_POSE, RETREAT_DZ), V_FAST, A_FAST, '드릴이송')) return false;
    if (!safeMoveLinear(DRILL_POSE, V_SLOW, A_SLOW, '드릴대기자세')) return false;

    console.log('⑨ 스핀들 ON → 정속 대기 ' + SPINDLE_SPINUP_S + 's');
    var spinning = spindle(true);
    sleep(SPINDLE_SPINUP_S);

    if (DRILL_DEPTH_MM > 0) {
        console.log('⑩ 진입 ' + DRILL_DEPTH_MM + 'mm (느리게 v' + DRILL_FEED_V + ')');
        var inPose = liftZ(DRILL_POSE, -DRILL_DEPTH_MM);        // 🚨 콜렛이 위를 향한다(9/2 사진) = 부품을 아래로 내린다 [현장 재확인]
        if (!safeMoveLinear(inPose, DRILL_FEED_V, DRILL_FEED_A, '드릴진입')) { spindle(false); return false; }
        console.log('⑪ 후퇴');
        if (!safeMoveLinear(DRILL_POSE, DRILL_FEED_V, DRILL_FEED_A, '드릴후퇴')) { spindle(false); return false; }
    } else {
        console.log('⑩ DRILL_DEPTH_MM=0 — 진입 없이 스핀들 ON/OFF 만 시험(의도된 동작)');
    }

    console.log('⑫ 스핀들 OFF');
    if (spinning) spindle(false);
    if (!safeMoveLinear(liftZ(DRILL_POSE, RETREAT_DZ), V_SLOW, A_SLOW, '드릴상공')) return false;

    if (DONE_BIN_POSE) {
        console.log('⑬ 완료 빈에 놓기');
        if (!safeMoveLinear(liftZ(DONE_BIN_POSE, RETREAT_DZ), V_FAST, A_FAST, '완료빈이송')) return false;
        if (!safeMoveLinear(DONE_BIN_POSE, V_SLOW, A_SLOW, '완료빈하강')) return false;
        gripperOpen();
        setPayload(PAYLOAD_TOOL);
        safeMoveLinear(liftZ(DONE_BIN_POSE, RETREAT_DZ), V_SLOW, A_SLOW, '완료빈후퇴');
    } else {
        console.log('⑬ DONE_BIN_POSE 없음 — 부품을 물고 정지(의도된 동작)');
    }
    return true;
}

function runDrill() {
    console.log('=== MODE 4: 집어서 드릴링까지 (티칭 좌표 · 인식 없음) ===');
    if (!TEACH_POSE) { console.log('🔴 TEACH_POSE 가 비어 있다.'); return; }
    if (PLACE_POSE) { console.log('🔴 MODE drill 에서는 PLACE_POSE 를 비워라 — pickOne 이 먼저 놓아버린다.'); return; }
    gripperInit();
    setPayload(PAYLOAD_TOOL);
    if (!pickOne(TEACH_POSE)) { console.log('🔴 파지 실패 — 드릴링 진행 안 함'); return; }
    var ok = drillOne();
    console.log(ok ? '✅ 집어서 드릴링까지 완료' : '🔴 드릴링 단계 실패/미완');
}

function runTeach() {
    console.log('=== MODE 2: 티칭 좌표로 파지 (인식 없음) ===');
    if (!TEACH_POSE) {
        console.log('🔴 TEACH_POSE 가 비어 있다. 펜던트로 티칭한 좌표를 넣어라.');
        console.log('   🚨 추측값을 넣고 돌리지 말 것.');
        return;
    }
    gripperInit();
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

if (MODE === 'iomap')        runIoMap();
else if (MODE === 'gripper') runGripperOnly();
else if (MODE === 'teach')   runTeach();
else if (MODE === 'drill')   runDrill();
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
 *   교안:5~6·22·24~25  그리퍼 배선·신호조합·파지 판정·입력시간·에러 규칙 (주강로보테크 Quick Guide)
 *
 * 🚨 9/4 현장에서 채울 [확인필요]
 *   1. 🥇 채널 배정 (GRIP_OUT_CH / GRIP_IN_CH) — 교안:5 한 장에 번호 체계 3개(인쇄 배선도·손글씨 표·손글씨 여백)가 겹쳐 문서로 확정 불가
 *      판정법 = ①제어반 단자대(IN-1~3 · DO 0~4 라벨)에서 그리퍼 6페어가 물린 DO 를 눈으로 추적 ②MODE 'iomap' 으로 그 DO 만 하나씩 High
 *      ⭐ 열림 DO 둘 → [0],[1] / 닫힘 DO 둘 → [2],[3] (조합표가 대칭이라 둘 사이 순서는 무관) / 무반응 = 그리퍼 아님
 *   2. GUI 설정값 = 🟢 기본값(대기 85.00 · 파지 설정위치 3.05 · 80/80 · 50ms)이면 27종 커버 확인(9/3 DB 대조) ⇒ GUI 없이 진행 가능
 *      🟡 단 협력사가 값을 바꿨을 수 있다 — 열림 폭이 눈에 띄게 좁으면 그때 GUI(RS-485 컨버터+JRT_Gripper_SetUp.exe) 필요
 *   2'. GRIP_MIN_MOTION_S(1.0s) — IN_1 이 전원 후 계속 High 인지·명령 시 내려갔다 오르는지 [확인필요] → 실측 후 줄인다
 *   3. IPC IP                                              (SERVER_IP)
 *   4. TEACH_POSE · PLACE_POSE 티칭값
 *   5. 부품 무게 실측                                       (PAYLOAD_PART)
 *
 * ⚠️ 아직 하지 않은 것 = setToolCenterPoint / setToolBoundingBox 호출.
 *    TCP 는 펜던트에 이미 a_0115(Z=200)가 등록돼 있어 **덮어쓰면 위험**하므로
 *    현장에서 현재 등록값을 확인한 뒤 결정한다.
 * ========================================================================== */
