# 시퀀스 서비스 배포 논의 (2026-04-23 예승님 미팅)

> 작성: 2026-04-22
> 참석: 정태민(오리누), 이예승(한솔코에버)
> 목적: `sequence_service`(Automation/Automation_Manual 탭)를 현장·원격 어디에서 어떻게 실행할지 합의

---

## 1. 현재 상태 요약

### 서버별 역할
| 서버 | URL | 현재 동작 | sequence_service | 비고 |
|------|-----|----------|------------------|------|
| **카카오 VM** | `61.109.239.142:8085` | web-api만 | ❌ 미실행 | Basic Auth, Cloud API 폴링, 모니터링 전용 |
| **6000 서버** | `106.244.6.242:8085` | web-api만 | ❌ 미실행 | VPN 경유 → 공장 PC 프린터 제어 가능 |
| **공장 PC** | `127.0.0.1:8085` (로컬) | ? (예승님 확인 필요) | ? | 실제 로봇/Ajin IO 연결됨 |

### 오늘(4/22) 발견한 이슈
- 태민님 노트북 → 6000 서버 접속: **프리셋·프린터 제어 정상**
- AnyDesk → 공장 PC → `127.0.0.1:8085` 접속: **"Local API Error" 발생**
  - 원인 가설: 공장 PC에 실행 중인 8085 프로세스가 구버전(또는 sequence_service 통합 런처)일 가능성
  - 예승님이 현재 공장 PC에서 돌리는 프로세스 확인 필요 (`netstat -ano | findstr :8085`)

---

## 2. sequence_service가 **반드시 공장 PC에서만** 돌아야 하는 이유

### 하드웨어 제약
| 의존 대상 | 연결 방식 | 원격 실행 가능? |
|----------|-----------|---------------|
| Ajin IO 보드 (AXL.dll) | PCIe/USB 물리 연결 | ❌ Windows + 물리 연결 필수 |
| HCR-10L 로봇 (Modbus TCP) | 공장 LAN (`127.0.0.1:9100` 기본) | △ 네트워크 도달만 되면 가능하나 지연/안전성 문제 |
| Vision TCP (`127.0.0.1:9200`) | 공장 LAN (비전 PC) | △ 동일 |
| PreFormServer (`10.145.113.3:44388`) | VPN | ✅ 가능 |
| MySQL (시퀀스 로그) | 공장 PC 로컬 | △ 네트워크로 열면 가능 |

**결론**: Ajin IO가 Windows DLL + 물리 하드웨어 의존이라 공장 PC를 벗어날 수 없음.

### 코드 구조 확인
- `sequence_service/app/main.py`: `venv\Scripts\python.exe` 같은 Windows 경로 기본
- `sequence_service/app/io/axl.py`: `from ctypes import WinDLL` — Windows 전용
- `SIMUL_MODE=true` / `AJIN_SIMULATION=true`로 **시뮬레이션은 어느 OS에서도 가능** (단, 실제 로봇은 안 움직임)

---

## 3. 운영 시나리오 3가지 — 장단점 비교

### 🅰️ 시나리오 A: 공장 PC 단독 실행 (현재 상태)
```
공장 PC : python main.py (통합 런처 = web-api + sequence_service)
현장 관리자 : 공장 PC 화면 또는 AnyDesk로 localhost:8085 접속
```
- ✅ 가장 안전, 구조 단순
- ✅ 로봇·IO 제어 지연 없음 (localhost)
- ❌ 재부팅 시 자동 시작 안 됨 (수동 실행 필요) — **4/14 문제 반복**
- ❌ 태민님 노트북 등 외부에서 Automation 탭 사용 불가

### 🅱️ 시나리오 B: 공장 PC 백엔드 + 원격 UI 접속 (프록시)
```
공장 PC : python main.py (통합 런처)
카카오 VM / 6000 서버 : web-api에 /api/v1/automation/* 를 공장 PC로 프록시
사용자 : 태민님 노트북 → 원격 서버 → (프록시) → 공장 PC
```
- ✅ 태민님 노트북에서도 Automation 탭 동작
- ❌ **원격 로봇 제어 = 안전성 문제** (네트워크 끊김 시 로봇 멈춤 처리 필요)
- ❌ 프록시 코드 추가 구현 + 테스트 필요 (1~2일)
- ❌ 4/23 Basler 도착 코앞 → 다른 리스크 추가 금물

### 🅲 시나리오 C: 원격 접속 시 Automation 탭 가드
```
현장 관리자 (공장 PC localhost) : Automation 탭 활성화
외부 접속자 (태민/예승님 노트북) : Automation 탭 비활성화 + 안내 메시지
```
- ✅ 오조작 방지 (원격에서 실수로 로봇 제어 차단)
- ✅ 구현 간단 (프론트엔드 조건부 렌더링, 30분~1시간)
- ❌ 태민님 노트북 등 외부에서 Automation 탭 사용 여전히 불가 (의도된 제약)

---

## 4. 내일 논의할 쟁점

### 🔴 P0. 공장 PC에서 sequence_service **자동 시작** 보장
- 현재 PreFormServer, file_receiver, AnyDesk는 시작프로그램 등록됨 (4/14 확인)
- **`python main.py`(통합 런처)는 등록됐는지 예승님 확인 필요**
- 미등록이면 방법 2가지:
  - (간단) 시작프로그램 폴더에 bat 파일 등록: `cd C:\...\3D_printer_automation && python main.py`
  - (권장) Windows 서비스화: NSSM 또는 Task Scheduler로 로그인 없이도 실행
- MySQL 자동 시작 여부도 확인 필요

### 🟡 P1. 공장 PC 배포 디렉토리 확정
- 예승님 4/16 질문: "공장 PC 배포 디렉토리?" → 아직 답변 못 드림
- 후보: `C:\3D_printer_automation\` / `C:\Users\devfl\3D_printer_automation\`
- git clone + pull 시 사용자 권한 고려

### 🟡 P2. 카카오 VM / 6000 서버에서 Automation 탭 어떻게 할지
- 옵션 a: 버튼 남기되 "원격 접속 시 실제 실행 안 됨" 안내 배너
- 옵션 b: 완전히 숨김 (공장 PC 접속일 때만 표시)
- 옵션 c: 원격에서도 표시하되 프록시로 실제 동작 (시나리오 B) — **4/23 이후 고려**

### 🟢 P3. 원격 프리셋 에러 (AnyDesk → 공장 PC 127.0.0.1:8085)
- 공장 PC의 8085가 무엇인지 확인:
  ```cmd
  netstat -ano | findstr :8085
  tasklist | findstr <PID>
  ```
- 가능성:
  1. 구버전 코드 (업데이트 필요)
  2. sequence_service 통합 런처인데 DB 마이그레이션 빠짐
  3. 포트 중복 (다른 프로세스)
- 확인 후 최신 코드로 재배포 필요 여부 결정

### 🟢 P4. Cloudflare Tunnel 진행 (`factory.flickdone.com`)
- 대표님 Cloudflare 초대 대기 중
- 초대 오면 태민님이 직접 진행 → 공장 PC 연결
- 그때 시나리오 B 검토 가능 (터널로 안전하게 공장 PC 노출)

---

## 5. 내일 합의해야 할 것

1. **[P0]** 공장 PC 자동 시작 체인 확정 + 시작프로그램 등록 책임자
2. **[P1]** 공장 PC 배포 디렉토리 경로 확정 + git pull 프로세스 합의
3. **[P2]** 당장은 **시나리오 A + C 조합** 권장 (= 공장 PC 단독 실행 + 원격 UI는 Automation 탭 가드)
4. **[P3]** 공장 PC 8085 프로세스 정체 확인 → 재배포 필요 여부 결정
5. **[P4]** Cloudflare Tunnel 이후(4/23~)에 시나리오 B 재검토

---

## 부록: 태민님 권장 방향

- **4/23 Basler 입고 앞두고 있어 위험 감수 금물** — 원격 로봇 제어(시나리오 B)는 4월 중 하지 않음
- 공장 PC 자동 시작 안정화(P0)가 가장 먼저 해결해야 할 이슈
- Automation 탭 가드(시나리오 C)는 30분 작업으로 오조작 리스크 크게 줄어듦 — 합의되면 즉시 구현 가능
- 원격에서 자동화 쓰려면 **Cloudflare Tunnel + 프록시 + 안전 장치(heartbeat, 연결 끊김 시 로봇 정지)** 삼박자 필요 → 최소 1주 작업, 4/23 Basler 안정화 후 착수 제안
