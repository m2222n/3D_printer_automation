// gripper 초-최소판 (9/7) — 열기(대기1)·닫기(파지1) 3회. 로봇은 안 움직인다.
// 교안:6 조합표 = 단일 High: OUT_1→대기1(개방) · OUT_3→파지1(닫힘). OPEN/CLOSE 에 iomap 으로 확정한 DO 번호를 넣는다.
// 🚨 sleep(ms) = 밀리초
var OPEN = 0, CLOSE = 2, HOLD = 2000;
var n;
for (n = 1; n <= 3; n++) {
    setGeneralDigitalOutput(CLOSE, 0); setGeneralDigitalOutput(OPEN, 1);
    sleep(HOLD);
    console.log(n + ' open  IN0=' + getGeneralDigitalInput(0) + ' IN2=' + getGeneralDigitalInput(2));
    setGeneralDigitalOutput(OPEN, 0); setGeneralDigitalOutput(CLOSE, 1);
    sleep(HOLD);
    console.log(n + ' close IN1=' + getGeneralDigitalInput(1) + ' IN2=' + getGeneralDigitalInput(2));
}
setGeneralDigitalOutput(CLOSE, 0); setGeneralDigitalOutput(OPEN, 1);
sleep(HOLD);
console.log('END open');
