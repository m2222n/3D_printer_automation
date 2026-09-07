// iomap 초-최소판 (9/7) — DO 하나씩 1.5초 High → 👁️ 열림/닫힘/무반응 기록. 로봇은 안 움직인다.
// 🚨 실행 전: 제어반 단자대에서 그리퍼 6페어가 물린 DO 4개를 눈으로 확인해 CH 에 그 번호만 넣는다 (공압 매니폴드 DO 0·DO 2 주의)
// 🚨 sleep(ms) = 밀리초 (ko §sleep) — 초로 쓰면 1.5ms 가 된다
var CH = [0, 1, 2, 3];
var k, i;
for (k = 0; k < CH.length; k++) {
    for (i = 0; i < CH.length; i++) setGeneralDigitalOutput(CH[i], 0);
    sleep(300);
    console.log('DO' + CH[k] + ' High 1.5s');
    setGeneralDigitalOutput(CH[k], 1);
    sleep(1500);
    console.log(' IN0=' + getGeneralDigitalInput(0) + ' IN1=' + getGeneralDigitalInput(1) + ' IN2=' + getGeneralDigitalInput(2));
}
for (i = 0; i < CH.length; i++) setGeneralDigitalOutput(CH[i], 0);
console.log('END');
