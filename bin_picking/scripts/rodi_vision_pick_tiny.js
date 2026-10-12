// 인식 좌표로 1개 집기 — 10/8 리허설용 초-최소판 (rodi_vision_tiny.js + 하강·닫기·상승 6줄)
// 서버(IPC · 먼저): python -m bin_picking.src.run_live_pick --capture --calib <cam_to_base.json> --hover-mm 50 --rz-mode angle --checkpoint … --out-dir … --limit 1
//   🚨 서버의 --hover-mm 와 아래 HOVER 가 같아야 한다(서버는 hover 를 더한 z 를 보내고, 이 스크립트가 그만큼 내려간다)
//   🚨 --rz-mode angle 은 GRASP_ANGLE 3값으로 build 한 calib 에서만 · 값이 없으면 fixed + 부품을 조우 방향에 맞춰 놓는다
// 순서: hover 로 이동 → 열기(DO1) → HOVER 만큼 수직 하강 → 닫기(DO3) → IN1/IN2 보고 → 상승 → DONE
// 🚨 그리퍼 빨간 불 켜짐(DO 모드) · 속도 20 · 정지 버튼에 손 · 도달 불가면 안 움직임 · 펄스 = 전부 Low → 300ms → 한 채널 High 500ms → 전부 Low (9/9 GUI Reverse)
// 🚨 ASCII only (9/28) · IP = 9/7 확정값 · OPEN=DO1(대기2) CLOSE=DO3(파지2) · 열림 IN0 · 물음 IN1 · 빈손 IN2 (9/16 GUI)
var IP = 'SET_ME', PORT = 5000, T = 10000, V = 20, A = 100, HOVER = 50, VD = 10;
function pulse(ch) { var i; for (i = 0; i < 4; i++) setGeneralDigitalOutput(i, 0); sleep(300); setGeneralDigitalOutput(ch, 1); sleep(500); for (i = 0; i < 4; i++) setGeneralDigitalOutput(i, 0); }
function go(target, v) { var here = getCurrentPose('tcp'); if (!checkRunnableMotion('tcp', here, target, v, A, 'linear')) { console.log('NG UNREACHABLE ' + JSON.stringify(target)); return false; } moveLinear('tcp', target, v, A); while (!isSteady()) sleep(10); return true; }
socketCreate('vision', IP, PORT); socketOpen('vision'); socketWaitConnection('vision', T);
var poses = JSON.parse(socketReadLine('vision', T));
console.log('RECV ' + poses.length + ': ' + JSON.stringify(poses));
if (poses.length > 0) {
  var p = poses[0], hov = createPose(p[0], p[1], p[2], p[3], p[4], p[5]), low = createPose(p[0], p[1], p[2] - HOVER, p[3], p[4], p[5]);
  if (go(hov, V)) { pulse(1); sleep(1500); if (go(low, VD)) { pulse(3); sleep(2000);
      console.log('GRIP IN0=' + getGeneralDigitalInput(0) + ' IN1=' + getGeneralDigitalInput(1) + ' IN2=' + getGeneralDigitalInput(2) + ' (IN1=1 held, IN2=1 empty)');
      go(hov, VD); console.log('OK LIFTED ' + JSON.stringify(getCurrentPose('tcp'))); } }
}
socketSendLine('vision', 'DONE'); socketDisconnect('vision');
