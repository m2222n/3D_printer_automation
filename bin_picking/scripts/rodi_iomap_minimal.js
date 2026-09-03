// 🥇 9/4 펜던트에 "직접 타이핑"할 수 있는 최소판 (약 40줄) — rodi_pick_sequence.js 의 MODE iomap + gripper 만 뗀 것
// 이유 = 500줄 본판을 펜던트에 넣는 방법이 기록에 없다(8/1 확인 = "직접 타이핑하면 인식"). USB 투입이 안 되면 이걸 친다.
// 로봇은 안 움직인다. 근거 = 교안:5(핀·채널) · 교안:6(조합표 · 단일 High = 대기1/대기2/파지1/파지2) · ko:53~54(setGeneral*/getGeneral*)
// 🚨 실행 전 = 제어반 단자대에서 그리퍼 6페어가 물린 DO 4개를 눈으로 확인하고 CH 에 그 번호만 넣는다(공압 매니폴드 DO 0·DO 2 주의)

var STEP = 'iomap';            // 'iomap' = DO 하나씩 판정  |  'grip' = 열기·닫기 3회
var CH   = [0, 1, 2, 3];       // 올려볼 DO (iomap) / OUT-1~4 배정 (grip) ← iomap 결과로 채운다: 열림 둘, 닫힘 둘
var DI   = [0, 1, 2];          // IN_1(대기완료) IN_2(파지완료) IN_3(에러)
var DWELL = 1.5, MIN_MOVE = 1.0, TMO = 3.0;

function din() {
    return 'IN_1=' + getGeneralDigitalInput(DI[0]) + ' IN_2=' + getGeneralDigitalInput(DI[1]) + ' IN_3=' + getGeneralDigitalInput(DI[2]);
}
function allLow() { var i; for (i = 0; i < CH.length; i++) setGeneralDigitalOutput(CH[i], 0); sleep(0.05); }

// 조합 출력 → 완료신호(doneDi) 대기. IN_1 이 전원 후 이미 High 일 수 있어 "한 번 Low 를 봤거나 MIN_MOVE 경과" 후에만 인정
function cmd(row, doneDi, label) {
    var sawLow = getGeneralDigitalInput(doneDi) !== 1, i, t = 0, hi;
    for (i = 0; i < 4; i++) setGeneralDigitalOutput(CH[i], row[i]);
    sleep(0.05);
    while (t < TMO) {
        if (getGeneralDigitalInput(DI[2]) === 1) { console.log('🔴 ' + label + ' 에러(IN_3) — 빈손 파지면 정상'); return false; }
        hi = getGeneralDigitalInput(doneDi) === 1;
        if (!hi) sawLow = true;
        if (hi && (sawLow || t >= MIN_MOVE)) { console.log('✅ ' + label + ' 완료 ' + t.toFixed(2) + 's'); return true; }
        sleep(0.05); t += 0.05;
    }
    console.log('⚠️ ' + label + ' 대기 초과 — 채널 배정·배선 의심 · ' + din()); return false;
}

if (STEP === 'iomap') {
    var k;
    for (k = 0; k < CH.length; k++) {
        allLow();
        console.log('--- DO' + CH[k] + ' 만 High ' + DWELL + 's — 👁️ 열리나 / 닫히나 / 가만히? ---');
        setGeneralDigitalOutput(CH[k], 1); sleep(DWELL);
        console.log('    ' + din() + '   (IN_1↑=열림=OUT1/2 · 빈손 IN_3↑=닫힘=OUT3/4 · 전부0+무반응=그리퍼 아님)');
    }
    allLow();
    console.log('끝 — 열림 DO 둘 → CH[0],[1] / 닫힘 DO 둘 → CH[2],[3] 로 적고 STEP=grip');
} else {
    var n;
    for (n = 1; n <= 3; n++) {
        cmd([1, 0, 0, 0], DI[0], n + '회 열기(대기1)');
        cmd([0, 0, 1, 0], DI[1], n + '회 닫기(파지1)');
    }
    cmd([1, 0, 0, 0], DI[0], '마지막 열기');
}
