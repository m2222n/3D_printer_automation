// gripper 초-최소판 — 열기·닫기 3회 왕복. 로봇은 안 움직인다.
// 🎯 9/7 에 실물 3회 왕복 성공한 골격 그대로다: "전 채널 Low → 300ms → 한 채널만 High → 유지"
// 🚨🚨 [9/9 실물] 채널이 바뀌었다 — OPEN = DO1(대기2 · 84mm) · CLOSE = DO3(파지2). 9/7 의 DO0/DO2 는 협력사 GUI 설정으로
//    대기1 벌림이 45mm 부품에 부족하고 파지1 설정위치가 ≈40mm 라 쓰지 않는다. 폭 40mm 이하 부품은 GUI 재설정 전까지 못 문다.
// 🚨🚨 [9/9 실물] 실행 전 그리퍼 본체 **빨간 불이 켜져 있어야** 한다(1회 누름 = DO 제어 모드). 꺼져 있으면 DO 전부 무시 = 9/7 무동작 원인.
// 🚨 [9/8 수정] 전 채널 Low 를 넣었다 — 이게 없으면 미사용 DO 의 잔류 High 가 조합을 바꾼다.
//    교안:6 조합표는 4비트다. DO3 이 High 로 남아 있으면 1000(대기1=열림)이 1001(파지4=닫힘)이 되어
//    "열어라" 했는데 닫힌다. DO1 이 남으면 0010(파지1)이 0110(파지5)이 된다.
// 🚨 sleep(ms) = 밀리초 (ko §sleep)
// 📌 CH 1행만 바꾸면 다른 시험이 된다: [1] 열기만 · [3] 닫기만 · [1,3,1,3,1,3,1] 3회 왕복
// 📌 IN0/IN1/IN2 출력은 기록용이다 — 9/9 실측으로 IN1(파지 완료)은 안 뜨고 IN2 는 물어도 뜬다 ⇒ 판정은 눈으로.
var ALL = [0, 1, 2, 3];                  // 그리퍼 OUT-1~4 = DO0~3 (9/7 iomap 확정)
var CH  = [1, 3, 1, 3, 1, 3, 1];         // 1=OPEN(대기2) · 3=CLOSE(파지2) — 마지막은 열어서 끝낸다 [9/9 실물값]
var k, i;
for (k = 0; k < CH.length; k++) {
    for (i = 0; i < ALL.length; i++) setGeneralDigitalOutput(ALL[i], 0);
    sleep(300);                          // 🚨 0000 을 컨트롤러가 확실히 보게 (교안 입력시간 기본 50ms 의 6배)
    setGeneralDigitalOutput(CH[k], 1);
    sleep(2000);
    console.log(k + ' DO' + CH[k] + ' IN0=' + getGeneralDigitalInput(0) +
                ' IN1=' + getGeneralDigitalInput(1) + ' IN2=' + getGeneralDigitalInput(2));
}
console.log('END (열림 상태로 종료)');
