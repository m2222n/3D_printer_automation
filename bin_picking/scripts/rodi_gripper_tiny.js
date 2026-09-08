// gripper 초-최소판 — 열기·닫기 3회 왕복. 로봇은 안 움직인다.
// 🎯 9/7 에 실물 3회 왕복 성공한 골격 그대로다: "전 채널 Low → 300ms → 한 채널만 High → 유지"
// 🚨 [9/8 수정] 전 채널 Low 를 넣었다 — 이게 없으면 미사용 DO 의 잔류 High 가 조합을 바꾼다.
//    교안:6 조합표는 4비트다. DO3 이 High 로 남아 있으면 1000(대기1=열림)이 1001(파지4=닫힘)이 되어
//    "열어라" 했는데 닫힌다. DO1 이 남으면 0010(파지1)이 0110(파지5)이 된다.
// 🚨 sleep(ms) = 밀리초 (ko §sleep)
// 📌 CH 1행만 바꾸면 다른 시험이 된다: [0] 열기만 · [2] 닫기만 · [0,2,0,2,0,2,0] 3회 왕복
var ALL = [0, 1, 2, 3];                  // 그리퍼 OUT-1~4 (iomap 으로 확정한 DO 번호)
var CH  = [0, 2, 0, 2, 0, 2, 0];         // 0=OPEN(대기1) · 2=CLOSE(파지1) — 마지막은 열어서 끝낸다
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
