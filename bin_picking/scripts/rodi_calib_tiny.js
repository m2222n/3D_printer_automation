// hand-eye 샘플 초-최소판 — 현재 TCP 포즈를 IPC 서버에 한 줄 보고하고 끝난다. 로봇은 안 움직인다.
// 🎯 한 번 실행 = 샘플 하나. 로봇을 다음 자세로 옮기고(직접교시/조그) 다시 ▶ 실행. 10~15회 반복.
// 🚨 서버를 먼저 띄운다: python -m bin_picking.src.communication.calib_pose_server --out <dir> --capture blaze
// 🚨 IP = 9/7 확정값(CLAUDE.local 참조). 포트 5000 = pick_socket_server 와 같다(서버는 하나만 띄운다).
// 🚨 단위 = getCurrentPose 원값(mm·deg) 그대로. 여기서 바꾸지 않는다.
var IP = 'SET_ME', PORT = 5000, T = 10000;
while (!isSteady()) sleep(10);
var p = getCurrentPose('tcp');
socketCreate('vision', IP, PORT);
socketOpen('vision');
socketWaitConnection('vision', T);
socketSendLine('vision', JSON.stringify({ kind: 'calib', tcp: [p[0], p[1], p[2], p[3], p[4], p[5]], unit: 'mm_deg' }));
console.log('ACK ' + socketReadLine('vision', T) + ' pose ' + JSON.stringify(p));
socketDisconnect('vision');
