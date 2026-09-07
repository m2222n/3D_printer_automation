/* ============================================================================
 * 소켓 통신 확인 최소 스크립트 (로봇은 움직이지 않는다) — 9/7 신설
 *
 *   IPC:  C:\binpick_venv\Scripts\python -m bin_picking.src.communication.pick_socket_server --mode handshake
 *   펜던트: 이 파일을 타이핑/가져오기 → 실행
 *
 *   서버(IPC)가 빈 배열 "[]\n" 을 보내고 로봇이 "DONE\n" 을 돌려주면 통과.
 *   근거: rodi_script_api_manual_ko.pdf ko:172~178 (socket*) · 협력사 검증 골격(8/4 801건)
 *   🚨 SERVER_IP = IPC 로봇용 포트 주소 — 실물 확정값(9/7)은 CLAUDE.local.md / memory robot-network-0907 (리포엔 넣지 않는다)
 *   ✅ 9/7 실물 검증: 로봇 접속 → "[]" 수신 → "DONE" 회신 2/2 성공 (이 12줄을 펜던트에 타이핑)
 * ========================================================================== */

var SERVER_IP    = 'SET_ME';           // IPC 로봇용 포트 IP
var SERVER_PORT  = 5000;               // pick_socket_server.py DEFAULT_PORT
var SOCK         = 'vision';           // ko:172 예제 소켓명
var READ_TIMEOUT = 10000;              // ms — 🚨 socketReadLine 허용 범위 1~15000ms (매뉴얼 ko §11.1) · 30000은 유효성 검사 거부(9/7 실측)

console.log('=== 소켓 통신 확인: ' + SERVER_IP + ':' + SERVER_PORT + ' ===');

socketCreate(SOCK, SERVER_IP, SERVER_PORT);        // ko:172
socketOpen(SOCK);                                  // 실패 시 7초 후 재시도 (ko:172)
socketWaitConnection(SOCK, READ_TIMEOUT);          // ko:173
console.log('연결됨');

var line = socketReadLine(SOCK, READ_TIMEOUT);     // ko:177
console.log('수신: ' + line);

var poses = JSON.parse(line);
console.log('포즈 ' + poses.length + '건 (handshake 는 0건이 정상)');

socketSendLine(SOCK, 'DONE');                      // 협력사 규약
socketDisconnect(SOCK);
console.log('✅ 통신 확인 완료 — DONE 송신');
