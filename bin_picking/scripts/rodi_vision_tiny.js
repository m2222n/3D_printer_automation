// 인식 좌표로 이동 1회(집기 없음) — 9/22 성공 정의 ③''. 서버가 보낸 첫 포즈(base 좌표 · hover 포함)로 moveLinear 하고 끝. 그리퍼는 안 건드린다.
// 서버(IPC · 먼저 띄운다): python -m bin_picking.src.run_live_pick --capture --calib <cam_to_base.json> --hover-mm 50 --checkpoint … --out-dir …
//   (또는 pick_socket_server --mode vision --six-json … --calib … --hover-mm 50) · 🚨 --calib 없으면 서버가 시작을 거부한다(9/17 변환 계층)
// 🚨 로봇은 P_capture(capture_test)에서 촬영이 끝난 뒤 이 스크립트를 ▶ · 속도 20 · 사람이 정지 버튼에 손 · 도달 불가면 안 움직이고 로그만
// 🚨 IP = 9/7 확정값(CLAUDE.local 참조) · 근거 ko:172~178 socket* · ko:196 createPose · ko:38 checkRunnableMotion(startPose 필수) · ko:203 getCurrentPose · ko:205 isSteady
var IP = 'SET_ME', PORT = 5000, T = 10000, V = 20, A = 100;
socketCreate('vision', IP, PORT); socketOpen('vision'); socketWaitConnection('vision', T);
var poses = JSON.parse(socketReadLine('vision', T));
console.log('수신 ' + poses.length + '건: ' + JSON.stringify(poses));
if (poses.length > 0) {
  var p = poses[0], target = createPose(p[0], p[1], p[2], p[3], p[4], p[5]), here = getCurrentPose('tcp');
  if (checkRunnableMotion('tcp', here, target, V, A, 'linear')) { moveLinear('tcp', target, V, A); while (!isSteady()) sleep(10); console.log('OK 도착 ' + JSON.stringify(getCurrentPose('tcp'))); }
  else console.log('NG 도달 불가 — 안 움직임 · 자세(rx/ry/rz)·z 를 볼 것');
}
socketSendLine('vision', 'DONE'); socketDisconnect('vision');
