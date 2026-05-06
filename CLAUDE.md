# 3D Printer Automation System

> **새 세션 시작 시**: CLAUDE.md, CLAUDE.local.md 읽은 후 `~/.claude/projects/-home-jtm/memory/MEMORY.md`도 반드시 읽을 것

---

## 🔒 보안 원칙 — 모든 외부 유출 가능 출력물에 적용 (최우선 필독)

> **⚠️ 이 항목은 README 한정이 아님.** 외부로 나갈 수 있는 **모든 출력물**에 적용된다. 작업 전에 "이게 외부에 보일 수 있나?"를 먼저 물어볼 것.

### 적용 범위 (외부 유출 가능 출력물)
- **GitHub 리포 전체** — README, 소스코드 주석, 커밋 메시지, PR/이슈 본문, 릴리즈 노트, public/private 무관 (Private도 한솔 미러로 공유됨)
- **공유 문서** — 배포용 PDF, PPT, docx, Google Docs, Notion, 회의자료
- **외부 메시지** — 카톡, 이메일, Slack, 문자 (한솔·대표·파트너·지원사업 담당자 등)
- **스크린샷·동영상** — 데모 녹화, 버그 리포트 캡처, 발표 슬라이드 이미지
- **로그·리포트** — IRIS 연구노트, 사업보고서, 외부 제출 파일
- **채팅 히스토리** — 외부 Claude 세션(웹 Claude 포함), 공유된 대화

### 절대 포함 금지 항목

| 카테고리 | 금지 항목 |
|---------|----------|
| Credentials | Basic Auth 비번, OAuth Client ID/Secret, API 키, Service Token, DB 비번, SSH 키, 2FA Backup Codes |
| 네트워크 | 공인 IP, VPN IP, 내부 IP (192.168.*, 10.*), 도메인(`factory.flickdone.com` 등), SSH 포트/커맨드 |
| 인프라 식별자 | Cloudflare Tunnel ID, Windows 서비스명, NSSM 경로, 공장 PC 디렉토리 경로, AnyDesk ID, 프린터 시리얼 |
| 개인정보 | 개인 이메일, 담당자 실명(예승/파트장/기원 등), 회사 내부 호칭("대표님"), 전화번호 |
| 내부 운영 | 장비 입고일, 수리 이력, 교육 이력, 마일스톤 일자별, 회의 안건/발언, 머지 커밋 해시 |
| 사업정보 | 사업비, 계약 조건, 협업 구조 상세, 타 업체 가격 |
| 분쟁 가능 발언 | 특정 직원·업체에 대한 부정적 평가, 내부 갈등 관련 코멘트 |

### 예외 — 내부 문서는 상세히 OK
- `CLAUDE.md`, `CLAUDE.local.md`, `~/.claude/projects/-home-jtm/memory/*.md`
- 태민님 개인 로컬 메모 (Mac 노트 앱 등)

이 파일들은 git 추적되어도 **공개되지 않는 본인 개발 문서**이므로 상세할수록 좋다. 위 규칙은 **외부 유출 가능성이 조금이라도 있는 출력물**에만 적용.

### 작업 프로토콜 (반드시 준수)

1. **작업 시작 전 자문**: "이 결과물이 어디까지 보일 수 있나?"
   - 내부 메모리·CLAUDE.md → 상세 OK
   - 그 외 전부 → 민감 정보 제거 모드
2. **작성 중**: credentials·IP·도메인·실명·경로는 **플레이스홀더**로 (`your_password`, `<SERVER_IP>`, `<담당자>`)
3. **저장/커밋 전 self-check**:
   ```bash
   grep -niE "orinu2026|jtm@|61\.109|106\.244|10\.145|192\.168|b939f49b|이예승|김주엽|김기원|대표님|factory\.flickdone|D:\\\\3D_printer|admin.*password|Bearer " <대상파일>
   ```
   하나라도 걸리면 push/전송 중단하고 정리
4. **스크린샷 공유 전**: URL 바, 터미널 prompt, 파일 경로, `.env` 내용 마스킹 확인
5. **의심스러우면 멈추고 태민님 확인 요청** — push/전송 먼저 하지 말 것

### 2026-04-24 사고 (실제 있었던 일, 반복 금지)

README 전면 개편(`51fce05`) 시 위 7 카테고리 전부 박아서 origin + personal(한솔 미러) 양쪽 push. Basic Auth 비번 `orinu2026!`, Cloudflare Tunnel ID, 공인 IP 2개, 공장 PC 경로, 담당자 실명 3명, 개인 이메일까지. 태민님 직접 지적 후 `1272ddb`로 정리.

**원인**: "내부 문서처럼 상세할수록 좋다"는 기준을 **공개 범주 문서에 잘못 적용**. 외부 노출 가능성 판단을 생략한 것이 근본 실수.

**상세**: `memory/feedback_readme_public_security.md`

---

## 프로젝트 개요

### 기본 정보
| 항목 | 내용 |
|------|------|
| 프로젝트명 | 3D프린터-로봇 연동 자동화 시스템 |
| 회사 | 오리누 주식회사 (구 플릭던) |
| GitHub (회사) | https://github.com/orinu-ai/3D_printer_automation (Private) |
| GitHub (개인) | https://github.com/m2222n/3D_printer_automation (Private) — 한솔코에버 협업용 |
| 서버 경로 | `/home/jtm/3D_printer_automation/` |
| 사업 | 2025년 경기도 제조로봇 이니셔티브 (사업비 2억원) |
| 사업 기간 | 협약일 ~ 2025.12.31 |
| 담당 개발자 | 정태민 (1인 개발) |

### 프로젝트 목적
점자프린터 플라스틱 부품(약 20종) 생산 공정 자동화
- **1차 목표**: 웹/앱에서 프린터 완료 신호 수신 및 새로운 프린팅 요청 전송
- **궁극적 목표**: 서버가 3D프린터 현황 모니터링 + 로봇 작업 지시 + 전체 공정 자동화 제어

---

## 대표님 피드백 (핵심 결정사항)

### 2025.01.28~01.30
- 자체 개발 병행 (한솔 못 믿으니 우리도 따로 개발)
- Web API 방식 선호, 모바일 모니터링 중요
- 목표: 설 전 API 구축 완료

### 2026.02.04
- 공장 PC 설치 확정 (Linux), SaaS 플랫폼 구축 예정
- 세척기/경화기 완료 감지: OpenMV 카메라로 해결 (02-06 확정)

### 2026.02.12 (데모 후)
- PreForm 대시보드 기능 동등 구현 지시 (슬라이스, 예열, 시간, 일시정지)
- 프린터 4대 각각 독립 컨테이너, 탭 구분, 히스토리/대기 페이지 추가
- 서버 구성: 5090=운영(폐기예정), **8085=개발(현재 운영 중, systemd 자동시작)**

### 2026.02.24 (한솔코에버 미팅)
- ~~소스코드 공유 X, 가이드라인만~~ → **2/26 변경: 소스코드 공유 결정**
- 한솔코에버 작업 서버: Faridh님과 세팅
- ~~협업 담당자: 김기원 주임 (한솔, GitHub: `justkiwon`), 이나라 주임 (한솔)~~ → 기원님 퇴사 (4/3)
- **현재 협업 담당자: 이예승 사원 (한솔코에버, GitHub: `eseung97@gmail.com`, 연락처: 010-4946-3610)**
- **3/3(화) 공장 방문**: Faridh님 + 정태민 → 한솔코에버 현장 협업

### 2026.02.26
- **소스코드 공유 결정** + **Phase 전환 지시**: 인수인계 후 → OpenMV 개발
- 운영 서버: 5090 VM 폐기 → **카카오 클라우드로 이전 예정**
- AICA A100: 한솔에서 3월간 1대 필요 → 근형님께 전달 완료

### 2026.03.24~26 (한솔코에버 PR → 브랜치 전환)
- 김기원 주임(`justkiwon`)이 개인 리포(`m2222n`)에 **PR #3** 제출 (3/24)
- 내용: 자동화 프론트엔드(`AutomationPage`, `AutomationManualPage`) + 시퀀스 서비스 오케스트레이터(`main.py`) + 배포 가이드
- **PR 취소 → `hansol-dev` 브랜치에 재업로드** (3/25, 커밋 `591b95a`)
- ✅ **머지 완료 (4/3)** — `hansol-merge` 브랜치에서 cherry-pick + 수동 수정 후 main 머지 (`9c161dc`)
  - 인코딩 깨짐 복원 (routes.py, auth.py, config.py, requirements.txt, App.tsx)
  - 프린터 시리얼 하드코딩 → 환경변수 복원, MQTT 설정 유지
  - 기존 코드 보존 (OpenMV, bin_picking, vision, docs, mosquitto)
  - 기원님 코드: sequence_service/, AutomationPage, AutomationManualPage, automation_db.py 등 추가
  - origin + personal 양쪽 push 완료
- **3/27 한솔코에버 최종 시연** (한솔 자체 진행, 정태민은 Azure 교육 중)
- **4/3 김기원 주임 퇴사 확인** — 한솔코에버 퇴사. 직접 지원 불가, 구조/플로우 문의는 가능. 코드 docs 폴더에 역할별 요약 있다고 함

### 2026.04.23 (한솔코에버 이예승 사원 — 경화기 2대 → 1대 축소)
- 예승님이 `hansol-dev` 브랜치에 커밋 `52a1c8f` 업로드 (4/23 14:02)
- **내용**: sequence_service + AutomationPage UI에서 Cure 2 비활성화. `cureKeys`, `cure_active_cmd`, `CuringSequence(2)` 주석 처리
- **변경 파일 3개**: `AutomationPage.tsx`(+1/-1), `ctx.py`(+2/-2, BOM 제거 포함), `mainSequence.py`(+2/-2)
- ✅ **머지 완료 (4/23 저녁)** — `hansol-merge-3` 브랜치에서 cherry-pick(`47873fe`) → main 머지(`9f97f1e`)
  - **인코딩 깨짐 없음** — 1·2차와 달리 예승님이 BOM까지 제거해서 깨끗함
  - TypeScript + Python + Vite 빌드 전부 PASS
  - origin + personal 양쪽 push 완료
- **⚠️ 예승님 패치 불완전 → 오리누 측 후속 패치 완료 (4/24)**: `sequence_service/app/cell/runtime.py:121` `{1: None, 2: None}` → `{1: None}`으로 수정. ctx.py 기본값과 정합. (미커밋)

### 2026.04.16 (한솔코에버 이예승 사원 — 프린터 할당 기능)
- 이예승 사원이 `hansol-dev` 브랜치에 커밋 `74584fb` 업로드 (4/16)
- **내용**: 자동화 CMD 생성 시 특정 프린터 할당 콤보박스 연동 (기존: 랜덤 → 1~4번 지정 가능) + 공용 큐 버그 수정
- **추가 파일**: `sequence_service/.env.copy` — Modbus 레지스터 매핑 환경변수 템플릿
- ✅ **머지 완료 (4/16)** — `hansol-merge-2` 브랜치에서 cherry-pick + 검토 후 main 머지 (`e68c2b1`)
  - 머지 커밋(`34507f0`)의 인코딩 깨짐 차단 — App.tsx mojibake, auth.py 한글 주석 파괴 방지
  - localApi.ts 불필요한 포매팅 변경 되돌림
  - TypeScript 타입 체크 + Vite 빌드 PASS 확인
  - origin + personal 양쪽 push 완료
- **예승님 질문**: 공장 PC 배포 디렉토리 → 답변 대기 중

### 2026.04.10 (산업용 PC 카메라 구성 + 로봇 교육)
- **산업용 PC 카메라 구성**: Bottom Vision 1대 + 빈피킹 2대(Blaze-112+ace2) + 3D프린터/경화기 모니터링 1~2대 + 양손 로봇(추후) 1대 = **최대 6대**
- **산업용 PC 스펙 우려**: 5060, RAM 8GB — 카메라 6대 버거울 수 있음 → **젯슨 나노로 분산** 가능성

### 2026.04.14 (HCR-10L 로봇 교육 1회차)
- ✅ **교육 완료**: 펜던트 기본 기능 + Modbus TCP 통신 + 자동화 시스템 기본 개념
- **교육 자료 수령**: `PLC_Cobot_Modbus_Guide.pdf` (34페이지) — PLC↔Robot Modbus TCP/IP 가이드 (예제 3건)
- **한화 HCR 개발 특성**: 두산/현대와 달리 **펜던트(Rodi)로 개발**해야 함. 외부 PC는 Modbus 레지스터 간접 제어
  - 비전PC가 Modbus 레지스터에 피킹 좌표 쓰기 → 펜던트 프로그램이 읽어서 모션 실행
- **사용자 사용 가능 레지스터: 130~255** (문서상 128~이나 실사용 130번부터)
- **좌표계**: Base(로봇 바닥 고정부 기준) vs TCP(Tool Center Point, 그리퍼 끝단 기준)
- **TCP 좌표 Modbus 읽기**: Register 400~405 (1/10mm, 1/10deg, 16bit 정수)
- **티칭(교시) 교육은 별도 스케줄로 추후 진행**
- **TBD 항목은 그리퍼 장착 + 빈 배치 후 실측** (TCP 오프셋, 작업 영역, 오일러 컨벤션)

### 2026.04.14 (대표님 지시 — MaixCAM 장비 모니터링)
- **Sipeed MaixCAM으로 프린터/세척기/경화기 전용 모니터링 연구**
- **OpenMV AE3 대체** — MaixCAM이 성능 우위 (RISC-V + 0.5TOPS NPU, 400만 화소)
- **Cloud 없이 온디바이스 AI로 진행** (엣지 AI, 현장 독립 동작)
- 보유 장비: MaixCAM 1대 + LicheeRV Nano 2대 (4/6 수령)
- **우선순위**: 빈피킹(Phase 5) 우선, MaixCAM은 여유 시 착수

### 2026.04.14 (웹 서비스 인프라 정비)
- **웹 서비스 접속 불가 원인**: uvicorn 수동 실행 방식이라 프로세스 종료 후 재시작 안 됨
- ✅ **systemd user service 등록**: `~/.config/systemd/user/formlabs-web.service` (포트 8085)
  - `Restart=always` (크래시 시 5초 후 자동 재시작)
  - `loginctl enable-linger jtm` (로그아웃 후에도 유지)
  - `systemctl --user enable formlabs-web` (서버 재부팅 시 자동 시작)
- ✅ **한솔 머지 코드 Linux 호환 수정**:
  - `automation_db.py`: MySQL engine lazy 초기화 (MySQL 없어도 앱 시작 가능)
  - `ajin_io.py`: `WinDLL` import를 Windows에서만 (Linux에서 import 에러 해결)
  - `pymysql` 패키지 설치
- ✅ **WireGuard VPN 복구**: `sudo wg-quick up wg0` + `systemctl enable wg-quick@wg0` (재부팅 시 자동)
- ✅ **PreFormServer(44388) + file_receiver(8089) 정상 연결 확인**
- **외부 접속**: `http://106.244.6.242:8085/` (ipTIME 포트포워딩 8085→8085)
- **관리 명령어**: `systemctl --user status/restart/stop formlabs-web`, `journalctl --user -u formlabs-web -f`

### 2026.04.10 오후 (빈피킹 보고 피드백 — 카메라 배치 + 시각화 요청)
- **카메라 배치 변경**: 1대 고정(eye-to-hand, 오버헤드) + **1대 로봇암 장착(eye-in-hand)**
  - 인식 실패 시 로봇암이 다른 각도에서 재촬영 → 가시성 보완으로 인식률 향상 기대
  - 캘리브레이션 2세트 필요: eye-to-hand(고정) + eye-in-hand(로봇암)
  - 고정 카메라 후보: Blaze-112 ToF (넓은 FOV, 빈 전체 촬영), 로봇암 카메라 후보: ace2 5MP RGB (디테일)
- **보고 시 시각화 요청**: 안 되는 케이스에 대해 **스크린샷/이미지 첨부**하여 왜 안 되는지 시각적으로 설명해달라
  - → E2E 테스트에 실패 케이스 시각화 기능 구현 필요 (매칭 결과 오버레이, 오매칭 비교 이미지 자동 저장)

### 2026.04.15 (카메라 입고 전 SW 마무리)
- ✅ **Modbus 레지스터 맵 HCR-10L 실제 스펙으로 재설계** (`a13b5ce`)
  - 레지스터 주소 40001~ → HCR-10L 사용자 영역 130~140 (비전PC→로봇), 150~151 (로봇→비전PC)
  - 인코딩 FLOAT32(2레지스터) → INT16(1레지스터, 1/10mm, 1/10deg) — 펜던트와 동일
  - 로봇 내장 레지스터 매핑: 400~405(TCP 좌표), 600(상태), 700~702(명령)
  - 시퀀스 번호 동기화 + 쓰기 순서 보장 (좌표→CMD)
- ✅ **Colored ICP 파이프라인 추가** (`b33547b`)
  - `use_colored_icp=True` 기본: 양쪽 컬러 있으면 자동 활성화, 없으면 Point-to-Plane 폴백
  - multi-scale Colored ICP (4mm→2mm→1mm coarse-to-fine)
  - hard 난이도 60% → 개선 기대 (좌우 대칭 부품 변별력 향상)
- ✅ **Basler Blaze-112 + ace2 듀얼 캡처 모듈** (`6ad4668`)
  - `basler_capture.py`: pypylon 기반, RealSenseCapture와 동일 인터페이스
  - Blaze-112(ToF depth) + ace2(RGB 5MP) 듀얼 캡처
  - save/load 라운드트립, 시뮬 프레임, CLI(--list, --test)
  - main_pipeline.py에 `--basler` 옵션 추가

### 2026.04.03 (빈피킹 지시)
- **3D+RGB 카메라 확인**: Blaze-112(ToF) 단독인지, ace2(RGB)와 조합해서 포인트 잡는지 확인
- **STL 수집+정리+중복제거 완료 (4/6)**: 55개 다운 → 중복 제거 → 46개 → bbox 동일 분석 → **29종** (17개 `_duplicates/`). STL 최종 목록은 아직 미확정 (대표님도 확정 전, 킵고잉)
- **L1~L6 전체 파이프라인 SW 완성 (4/6~10)**: cad_library + E2E 테스트 + main_pipeline + L5 그래스프 + L6 Modbus TCP. OBB SizeFilter + 포인트 비율 필터 (4/8). 그래스프 DB 29종 완성 + E2E 시나리오 확장 + multi-res ICP (4/10). **인식률 100%(easy), crowded 90%, hard 60%. RMSE 1.0~1.5mm, 매칭 0.4~0.6s/부품**
- **RealSense D435**: ✅ **라이브 연동 성공 (4/13)** — USB 3.2(5Gbps), S/N `420122070194`, FW `5.17.0.10`. macOS에서 sudo 필요 (`sudo .venv/binpick/bin/python`). pyrealsense2 v2.57.7 소스빌드 완료
  - **프레임 저장/로드 (4/13)**: `--live --save`로 영구 저장 → `--load`로 카메라 없이 테스트. 유효 depth 91%(278K/307K), range 156~4349mm, 파일 1.5MB
  - 서버 로드 검증 PASS (numpy only, Open3D 불필요)
  - **실데이터 L1~L3 테스트 PASS (4/13)**: 책상 위 일반 사물 촬영 → 11 클러스터 검출, 바닥면 정상 분리, 파이프라인 0.29s. 빈피킹 환경에서 더 좋은 결과 기대
  - **Full Pipeline L1~L5 테스트 PASS (4/14)**: 2회 실행 모두 ACCEPT 0. ①d435_frames 8클러스터 WARN 3/REJECT 5, 1.83s ②d435_realworld 6클러스터 WARN 4/REJECT 2, 0.89s. CAD 미등록 물체 오탐 없음. RMSE 3mm 임계값이 핵심 안전장치 (fitness 0.47도 차단)
  - **다음**: 공장에서 실물 SLA 부품 3~5개 가져와서 D435로 촬영 → CAD 매칭 ACCEPT 검증 (미등록 REJECT은 확인됨, 등록 부품 ACCEPT 미검증)

### 2026.03.27 (공장 PC 장애 복구)
- 공장 PC 재부팅 후 `file_receiver.py`(8089) 자동 시작 안 됨 → 미리보기 "모델 임포트 실패"
- file_receiver 위치: `C:\Users\devfl\file_receiver.py`, 수동 실행하여 복구
- Windows cmd QuickEdit 모드 때문에 file_receiver 반복 멈춤 → QuickEdit 해제로 해결
- 출력 전송 후 프린터 미동작: PreFormServer 재시작 시 빌드플랫폼 상태 MISSING 리셋 → 프린터 터치스크린 확인 필요
- ✅ file_receiver 시작 프로그램 등록 완료
- ✅ **웹 UI readiness 체크 구현 완료** (`0e3451e`): 프린트 전 6가지 검증 + 경고 배너 + 버튼 비활성화

---

## Phase별 개발 계획 (확정)

| Phase | 항목 | 우선순위 | 기간 | 상태 |
|-------|------|----------|------|------|
| **Phase 1** | Web API 모니터링 | 🔴 URGENT | 2주 | ✅ 완료 |
| **Phase 2** | Local API 원격 제어 + 프론트엔드 UI | 🔴 URGENT | 3주 | ✅ 완료 (UI 개선 완료, 운영 전환 대기) |
| **Phase 3** | HCR 로봇 연동 | 🟡 HIGH | 4주 | ✅ 한솔코에버 코드 머지 3차 완료 (4/3 기원님, 4/16 예승님 프린터 할당, 4/23 예승님 경화기 1대 축소). 시퀀스 서비스 + 자동화 프론트엔드 통합. 3/27 최종 시연 완료 (한솔 자체) |
| **Phase 4** | ~~OpenMV~~ → **MaixCAM** 장비 모니터링 | 🟡 HIGH | 6주 | 🔄 OpenMV 제외, **MaixCAM으로 전환** (4/14 대표님 지시). 리서치 완료 — 1 TOPS NPU, find_blobs()/YOLO, MQTT/Modbus 내장. 빈피킹 우선, 여유 시 PoC |
| **Phase 5** | 3D 빈피킹 비전 시스템 | 🔴 URGENT | 11주 | 🔄 W5 — **Modbus INT16 재설계 + Colored ICP 파이프라인 + Basler 듀얼 캡처 모듈** 추가. L1~L6 SW 완성 + 그래스프 DB 29종 + D435 Full Pipeline PASS. 인식률 100%(easy), crowded 90%, hard 60%. **다음: 실물 SLA 부품 ACCEPT 검증 → 카메라 입고(5월) → 실제 캘리브레이션** |

---

## 프로젝트 구조

```
3D_printer_automation/
├── CLAUDE.md                    # 프로젝트 상태 문서 (이 파일)
├── CLAUDE.local.md              # 세션별 작업 이력 (git 제외)
├── README.md
├── .gitignore
│
├── docs/                        # 문서
│   ├── Phase1_WebAPI_개발설계서.docx
│   └── Phase2_LocalAPI_아키텍처설계.md
│
├── web-api/                     # 백엔드 (FastAPI) - Phase 1 + 2 통합
│   ├── .env.example             # 환경변수 템플릿
│   ├── data/local.db            # SQLite 데이터베이스
│   ├── app/
│   │   ├── main.py              # 앱 진입점 (lifespan, CORS, SPA)
│   │   ├── core/
│   │   │   ├── config.py        # 설정 관리 (Web + Local API)
│   │   │   └── auth.py          # OAuth2 인증
│   │   ├── services/            # Phase 1: Web API 서비스
│   │   │   ├── formlabs_client.py     # Formlabs 클라우드 API
│   │   │   ├── polling_service.py     # 상태 폴링 (15초)
│   │   │   └── notification_service.py # 알림 발송
│   │   ├── api/
│   │   │   └── routes.py        # Phase 1: REST API + WebSocket (11 routes)
│   │   ├── local/               # Phase 2: Local API ✅ 완료
│   │   │   ├── routes.py        # /api/v1/local/* 라우터 (32 routes)
│   │   │   ├── schemas.py       # 프리셋/작업 스키마
│   │   │   ├── models.py        # SQLAlchemy 모델
│   │   │   ├── services.py      # 프리셋/작업 서비스
│   │   │   ├── database.py      # SQLite 설정
│   │   │   └── preform_client.py # PreFormServer 클라이언트
│   │   └── schemas/
│   │       └── printer.py       # Pydantic 모델
│   ├── tests/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── requirements.txt
│
├── frontend/                    # 프론트엔드 (React + Vite + TS + Tailwind CSS 4) ✅ 완료
│   ├── src/
│   │   ├── App.tsx              # 메인 라우터 (7탭 + 알림벨)
│   │   ├── components/
│   │   │   ├── Dashboard.tsx           # 모니터링 탭: 프린터 4대 그리드 + 타임라인
│   │   │   ├── PrinterCard.tsx         # 프린터 요약 카드
│   │   │   ├── PrinterDetail.tsx       # 프린터 상세 정보 뷰
│   │   │   ├── PrinterInfoModal.tsx    # 프린터 상세 모달 (3탭, 글로벌)
│   │   │   ├── PrinterTimeline.tsx     # 타임라인 간트 차트
│   │   │   ├── PrintPage.tsx           # 프린트 제어 탭
│   │   │   ├── PrinterPrintControl.tsx # 프린터별 독립 제어 컨테이너
│   │   │   ├── QueuePage.tsx           # 대기 중인 작업 탭
│   │   │   ├── HistoryPage.tsx         # 이전 작업 이력 탭
│   │   │   ├── StatisticsPage.tsx      # 통계 탭
│   │   │   ├── AutomationPage.tsx     # 자동화 탭 (한솔코에버)
│   │   │   └── AutomationManualPage.tsx # 자동화 수동제어 탭 (한솔코에버)
│   │   ├── types/
│   │   │   ├── printer.ts       # Phase 1 타입
│   │   │   └── local.ts         # Phase 2 타입
│   │   └── services/
│   │       ├── api.ts           # Phase 1 API
│   │       └── localApi.ts      # Phase 2 API
│   └── package.json
│
├── sequence_service/             # Phase 3: 시퀀스 서비스 (한솔코에버, 4/3 머지)
│   ├── app/cell/                # 시퀀스 런타임, Modbus, 로봇/프린터 제어
│   ├── app/core/config.py       # 시퀀스 서비스 설정
│   ├── app/db/                  # MySQL 모델/세션
│   ├── app/io/                  # Ajin IO (AXL.dll, Windows)
│   └── app/main.py              # 서비스 진입점
│
├── main.py                      # 통합 런처 (web-api + sequence_service, Windows)
│
├── factory-pc/                  # 공장 PC 스크립트
│   └── file_receiver.py         # STL 파일 수신 + 스크린샷 서빙 (포트 8089)
│
├── bin_picking/                  # Phase 5: 3D 빈피킹 비전 시스템
│   ├── src/
│   │   ├── acquisition/         # L1: 카메라 캡처 (depth_to_pointcloud, realsense_capture, basler_capture)
│   │   ├── preprocessing/       # L2: 전처리 (cloud_filter — ROI, 이상치, 다운샘플, RANSAC, 법선)
│   │   ├── segmentation/        # L3: 분할 (dbscan_segmenter)
│   │   ├── recognition/         # L4: 인식+자세 (cad_library, pose_estimator, size_filter)
│   │   ├── grasping/            # L5: 그래스프 계획 (grasp_planner, grasp_database.yaml)
│   │   └── communication/       # L6: 로봇 통신 (modbus_server — HCR-10L INT16)
│   ├── models/
│   │   ├── cad/                 # STL 원본 (46개, 고유 45종)
│   │   ├── reference_clouds/    # pickle 캐시 (포인트+법선+bbox)
│   │   └── fpfh_features/       # pickle 캐시 (FPFH 33D)
│   ├── config/
│   ├── tests/                   # E2E 테스트 (test_e2e_redwood, test_e2e_realsense)
│   └── tutorials/               # Open3D 학습 (01~11)
│
├── OpenMV/                      # Phase 4: OpenMV 카메라 (참고자료 + 스크립트)
├── robot-control/               # Phase 3: 로봇 제어 (미구현)
├── vision/                      # Phase 4: 비전 검사 (미구현)
└── shared/                      # 공유 유틸리티 (미구현)
```

---

## 하드웨어 사양

### Formlabs Form 4 (4대 보유)
| 항목 | 사양 |
|------|------|
| 기술 | mSLA (Masked Stereolithography) |
| 빌드 볼륨 | 200 × 125 × 210 mm (5.25L) |
| XY 해상도 | 50 µm |
| 연결 | Wi-Fi, USB, Ethernet |
| machine_type | `"FORM-4-0"` |

### 협동로봇
| 항목 | HCR-12 (로봇1) | HCR-10L (로봇2) |
|------|----------------|-----------------|
| 용도 | 빌드플레이트 교체, 세척기 투입 | 후가공 탭, 제품 이송 |
| 가반하중 | 12 kg | 10 kg |
| 통신 | Modbus TCP (포트 502) | 동일 |

### 후처리 장비 (⚠️ API 미지원 → 카메라로 완료 감지)
- Form Wash (2대), Form Cure (2대)
- **해결**: ~~OpenMV 카메라~~ → **Sipeed MaixCAM**으로 완료 감지 (4/14 대표님 지시, OpenMV 제외)

### Sipeed MaixCAM (세척기/경화기 완료 감지용, OpenMV 대체)
- **모델**: Sipeed MaixCAM ($33~48) - RISC-V SG2002 + **1 TOPS NPU**, WiFi 6, 2.3" IPS 터치, 4MP
- **접근법**: find_blobs() LED 감지 (100+fps, NPU 불필요) → MQTT → 서버, 온디바이스 AI
- **통신**: WiFi 6 → MQTT (paho-mqtt 내장) + Modbus TCP/RTU 내장 + Flask HTTP 서버
- **모델 학습**: MaixHub (무료, 사진→어노테이션→학습→QR배포)
- **자동 실행**: 전원 ON 시 autostart 지원
- **참고**: https://wiki.sipeed.com/maixcam
- ~~기존 OpenMV AE3는 프로젝트에서 제외 (4/14 대표님 지시)~~

---

## Formlabs API 비교

| 구분 | Web API | Local API |
|------|---------|-----------|
| 버전 | 0.8.1 (Beta) | 0.9.11 |
| 기반 | 클라우드 (api.formlabs.com) | 로컬 PC (PreFormServer) |
| 인증 | OAuth 2.0 | 없음 (로컬 실행) |
| Rate Limit | IP 100 req/sec, 사용자 1500 req/hr | 없음 |
| **프린터 모니터링** | ✅ 가능 | ⚠️ 제한적 |
| **작업 전송** | ❌ 불가 | ✅ 가능 |

> **핵심**: Web API는 읽기 전용! 원격 프린팅은 Local API 필수

### Formlabs API 사용 현황 (2026-02-26)

| 구분 | 전체 | 사용 중 | 미사용 | 사용률 |
|------|------|--------|--------|--------|
| Web API | 19개 | 6개 | 13개 | 32% |
| Local API | 35개 | 17개 | 18개 | 49% |
| **합계** | **54개** | **23개** | **31개** | **43%** |

#### 현재 사용 중인 Web API (6개) — 모니터링 전용
| # | API | 용도 |
|---|-----|------|
| 1 | `POST /o/token/` | OAuth2 토큰 발급 (자동 갱신) |
| 2 | `GET /printers/` | 프린터 4대 상태 조회 (15초 폴링) |
| 3 | `GET /printers/{serial}/` | 특정 프린터 상세 조회 |
| 4 | `GET /prints/` | 전체 프린트 이력 |
| 5 | `GET /printers/{serial}/prints/` | 프린터별 프린트 이력 |
| 6 | `GET /events/` | 프린터 이벤트 (완료/에러) |

#### 현재 사용 중인 Local API (17개) — 프린트 제어
| # | API | 용도 |
|---|-----|------|
| 1 | `GET /` | PreFormServer 연결 상태 확인 |
| 2 | `POST /discover-devices/` | 네트워크 프린터 검색 |
| 3 | `POST /scene/` | Scene 생성 |
| 4 | `DELETE /scene/{id}/` | Scene 삭제 |
| 5 | `GET /scene/{id}/` | Scene 정보 조회 |
| 6 | `POST /scene/{id}/import-model/` | STL 파일 로드 |
| 7 | `POST /scene/{id}/auto-orient/` | 자동 방향 설정 |
| 8 | `POST /scene/{id}/auto-support/` | 자동 서포트 생성 |
| 9 | `POST /scene/{id}/auto-layout/` | 자동 배치 |
| 10 | `POST /scene/{id}/print/` | 프린터로 작업 전송 |
| 11 | `GET /scene/{id}/print-validation/` | 프린트 전 유효성 검사 |
| 12 | `POST /scene/{id}/models/{id}/duplicate/` | 모델 복제 (대량 배치) |
| 13 | `GET /list-materials/` | 사용 가능 재료 목록 |
| 14 | `POST /scene/{id}/hollow-model/` | 내부 비우기 (레진 절약) |
| 15 | `POST /scene/{id}/save-screenshot/` | 미리보기 스크린샷 |
| 16 | `POST /scene/{id}/estimate-print-time/` | 정밀 시간 예측 |
| 17 | `POST /scene/{id}/interferences/` | 모델 간 간섭 검사 |

#### 미사용 API 중 활용 가치 높은 것 (미구현)
| API | 분류 | 기능 |
|-----|------|------|
| `GET /tanks/` | Web | 레진 탱크 이력 |
| `GET /cartridges/` | Web | 카트리지 소모 이력 |
| `POST /scene/{id}/label-part/` | Local | 모델에 라벨 각인 |
| `POST /load-form/` | Local | .form 파일 로드 |
| `POST /save-form/` | Local | Scene → .form 저장 |

#### API로 할 수 없는 것 (한계)
| 기능 | 상태 | 우리 대안 |
|------|------|----------|
| 프린트 일시정지/재개/취소 (원격) | **미지원** | 터치스크린 안내 표시 |
| Webhook (실시간 이벤트 푸시) | **미지원** | 15초 폴링 |
| Form Wash/Cure 제어 | **API 없음** | OpenMV 카메라 완료 감지 |
| 프린터 설정 변경 (원격) | **미지원** | 터치스크린 |

---

## Phase 1: Web API 모니터링 ✅ 완료

### API 엔드포인트
| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/v1/dashboard` | 4대 프린터 상태 요약 |
| GET | `/api/v1/printers` | 프린터 목록 |
| GET | `/api/v1/printers/{serial}` | 특정 프린터 상태 |
| GET | `/api/v1/prints` | 프린트 이력 (날짜/상태/프린터 필터) |
| GET | `/api/v1/statistics` | 통계 데이터 |
| WS | `/api/v1/ws` | 실시간 업데이트 |

### 확인된 프린터 (4대)
| 이름 | 시리얼 | IP | 비고 |
|------|--------|-----|------|
| CapableGecko | Form4-CapableGecko | 192.168.219.46 | Grey V5 |
| HeavenlyTuna | Form4-HeavenlyTuna | 192.168.219.48 | Clear V5 |
| CorrectPelican | Form4-CorrectPelican | 192.168.219.43 | Flexible 80A V1.1 |
| ShrewdStork | Form4-ShrewdStork | 192.168.219.45 | ✅ 운용 중 (4/3 헤드커버 수리 완료) |

---

## 프론트엔드 UI 구조 (2026-02-27 최신)

### 5탭 네비게이션 + 알림벨
| 탭 | 컴포넌트 | 기능 |
|----|----------|------|
| **모니터링** | Dashboard.tsx | 프린터 4대 그리드 카드, 상태 필터(토글), 타임라인 간트 차트 |
| **프린트 제어** | PrintPage.tsx | 프린터별 독립 컨테이너 (PrinterPrintControl) |
| **대기 중인 작업** | QueuePage.tsx | 드래그앤드롭 순서 변경, 예약 시간 |
| **이전 작업 내용** | HistoryPage.tsx | 로컬+클라우드 이력, 필터, CSV, 메모 |
| **통계** | StatisticsPage.tsx | 재료 도넛차트, 일별 바차트, 프린터별 가동률 |
| **🔔 알림벨** | App.tsx | 미읽음 뱃지, 드롭다운, 30초 폴링 |

### 프린터 상세 모달 (PrinterInfoModal) — PreForm 앱 수준 3탭
- **트리거**: 프린터 이름(파란 링크) 또는 ℹ️ 아이콘 클릭 → 슬라이드-오버
- **Details / Settings / Services** 3탭

### 데이터 흐름
```
REST 초기 로드 → State → WebSocket 실시간 구독 (15초 폴링 폴백)
Phase 1: api.ts (Formlabs Cloud)  →  Dashboard, HistoryPage, StatisticsPage
Phase 2: localApi.ts (Local API)  →  PrintPage, QueuePage, HistoryPage, Notifications
```

---

## Phase 2: Local API 원격 제어 ✅ 완료

### API 엔드포인트 (32 routes)
| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/v1/local/health` | Local API 상태 확인 |
| POST | `/api/v1/local/printers/discover` | 프린터 검색 |
| POST/GET/PUT/DELETE | `/api/v1/local/presets[/{id}]` | 프리셋 CRUD |
| POST | `/api/v1/local/presets/{id}/print` | 프리셋으로 프린트 |
| POST/GET/DELETE | `/api/v1/local/upload`, `/files[/{filename}]` | 파일 관리 |
| POST/GET | `/api/v1/local/print[/{id}]` | 프린트 작업 |
| POST/DELETE | `/api/v1/local/scene/prepare`, `/{id}/print`, `/{id}` | Scene 관리 |
| GET/POST | `/api/v1/local/scene/{id}/validate`, `/models`, `/models/{id}/duplicate` | 유효성/복제 |
| GET | `/api/v1/local/materials` | 재료 목록 |
| GET/POST | `/api/v1/local/scene/{id}/screenshot[/{filename}]` | 스크린샷 |
| POST | `/api/v1/local/scene/{id}/estimate-time`, `/interferences` | 시간/간섭 |
| GET/POST/PUT/DELETE | `/api/v1/local/notes[/{print_guid}][/{note_id}]` | 메모 CRUD |
| GET/POST | `/api/v1/local/notifications[/mark-read]` | 알림 |

### TODO (미완료)
- [ ] 실제 프린터 프린트 전송 테스트 (레진 탱크 장착 필요)

### 인프라
| 구분 | 서버 | 외부 포트 | 용도 | 상태 |
|------|------|----------|------|------|
| 6000 서버 | 192.168.100.29:8085 (VPN: 10.145.113.8) | 8085 | **개발용** (이전 후 git 저장소만) | ✅ 동작 중 |
| 카카오 클라우드 | 61.109.239.142:8085 | 8085 | **운영용** (웹 서비스) | ✅ 외부 접속 정상 |

### 네트워크 구조
```
[기존/6000] 브라우저 → 106.244.6.242:8085 → 6000서버 → WireGuard → 공장PC → 프린터
[이전/카카오] 브라우저 → 61.109.239.142:8085 → 카카오VM → (TBD) → 공장PC → 프린터
```
- **6000 서버 WireGuard 클라이언트 설치 완료 (3/26)**: Method B 적용 — 파리드님 conf 파일 제공, VPN IP `10.145.113.8/24`
- ~~Method A (공유기 라우팅)~~ 실패 → Method B (서버에 WG 직접 설치)로 해결
- WireGuard 서버: 사무실 ipTIME 공유기 (192.168.100.1 / 10.145.113.1), Endpoint: `orinu.iptime.org:56461`
- conf 파일: `/etc/wireguard/wg0.conf` (키 정보 포함, 커밋 금지)
- ⚠️ `systemctl`은 inactive — 서버 재부팅 시 `sudo systemctl enable --now wg-quick@wg0` 필요
> ✅ VPN-로봇 충돌 해결 (3/18): WireGuard `AllowedIPs`에서 `192.168.100.0/24` 제거 → VPN + 로봇 동시 운용 가능
> 🔄 중기: 카카오 클라우드 + Cloudflare Tunnel로 전환 예정 (대표님 도메인 답변 대기)

### 카카오 클라우드 전환 계획 (파리드님 제안, 3/16)
```
브라우저 → 도메인(orinumonitoringfactory.com 등) → Cloudflare → 카카오 클라우드(Public IP) → Cloudflare Tunnel → 공장 PC → 프린터/로봇/카메라
```
- **배경**: 대표님 2/26 지시 (5090 VM 폐기 → 카카오 클라우드 이전) + VPN-로봇 충돌 문제
- **장점**: VPN 제거 → 로봇 네트워크 충돌 해결, outbound 터널이라 방화벽/포트포워딩 불필요, 도메인+HTTPS 자동
- **도메인 확정 (3/18)**: `lab.flickdone.com` (flickdone.com 서브도메인, 대표님 지시). 향후 flickdone.com을 제조공정 자동화 브랜드로 사용 예정
- **필요 사항**: Cloudflare 설정 (파리드님), 공장 PC에 Tunnel 설치, 백엔드 마이그레이션
- ~~**미해결**: 공장 PC가 프린터(219.x)와 로봇(100.x) 양쪽 네트워크 동시 접근~~ → ✅ WireGuard AllowedIPs 수정으로 해결 (3/18)
- ~~**주의**: 데모 시연 3/27~31~~ → **데모 시연 3/20 완료**

### 6000 서버 WireGuard 정보
| 항목 | 값 |
|------|-----|
| VPN IP | 10.145.113.8/24 |
| 인터페이스 | wg0 |
| conf 파일 | `/etc/wireguard/wg0.conf` |
| Peer Endpoint | 106.244.6.242:56461 (= orinu.iptime.org) |
| AllowedIPs | 10.145.113.0/24, 192.168.100.0/24 |
| PersistentKeepalive | 25 |
| DNS | 203.248.252.2 |

### 공장 PC 정보
| 항목 | 값 |
|------|-----|
| Windows 사용자 | `devfl` |
| VPN IP | 10.145.113.3 |
| PreFormServer | `C:\PreFormServer\PreFormServer.exe -p 44388` (v3.55.0.606) |
| file_receiver | 포트 8089 → `C:\STL_Files` |
| AnyDesk ID | 1 382 237 708 |
| 자동 시작 | WireGuard + PreFormServer + file_receiver + AnyDesk |
| PreForm 앱 | `C:\Program Files\Formlabs\PreForm\3.57.0.622\PreForm.exe` (별도, 서버 아님) |

> ⚠️ PreFormServer는 `-p 44388` 옵션 필수. 옵션 없이 실행하면 바로 종료됨.
> 시작 프로그램 바로가기: `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\PreFormServer.lnk`

---

## Phase 3: HCR 로봇 연동 🔄 한솔코에버 진행 중

- **프로토콜**: ~~TCP/IP Socket~~ → **Modbus TCP** 전환 완료 (포트 502), pymodbus
- **로봇**: HCR-12 (빌드플레이트 교체, 세척기 투입) + HCR-10L (후가공, 제품 이송)
- **한솔코에버 협업**: `hansol-dev` 브랜치에서 작업
- **현재 상태 (3/23 한솔 김기원 주임)**:
  - 프린터 1대 시나리오까지 원활하게 동작
  - 자동화 부분 = Python 단일 thread로 구현
  - 수주 단위 장기 운영 테스트는 아직 (자동화 라인 특성상 수주 돌려봐야 이슈 파악)
  - 3/27 최종 시연 예정

---

## Phase 4: 비전 검사 (YOLO + OpenMV) ⬜ 대기

### 용도 (3가지)
1. **부품 식별** — YOLO + Intel RealSense
2. **세척기/경화기 완료 감지** — OpenMV 카메라 (02-06 확정)
3. **불량 검출** — YOLO + RealSense

### OpenMV 카메라 배치 (4대)
| 카메라 | 설치 위치 | 감지 내용 |
|--------|----------|----------|
| #1, #2 | 세척기 1, 2번 전면 | 세척 중/완료 |
| #3, #4 | 경화기 1, 2번 전면 | 경화 중/완료 |

### 통신 아키텍처
```
[OpenMV #1~#4] → WiFi → MQTT → [Mosquitto] → [FastAPI] → [HCR 로봇 (Modbus)]
```

### 기술 스택
- **YOLO**: YOLOv8s/v11s, Intel RealSense D457
- **OpenMV**: AE3 ($85), Edge Impulse (Classification)
- **학습**: 최소 400장+ (상태별 100장)
- **설계 문서**: `리서치문서6_OpenMV카메라_리서치.pdf`, `OpenMV_개발설계서.pdf`

---

## Phase 5: 3D 빈피킹 비전 시스템 🔄 W3+ 완료 → 카메라 입고 대기

> **문서**: ORINU-DEV-2026-002 (구본경 대표, 2026-03-18) — PDF로 재수령 (4/1), docx는 헤더 깨짐
> **개발**: Mac (Intel) + venv binpick (Python 3.12 + Open3D 0.19.0) — 6000 서버 Open3D 불가 (AVX2 미지원)
> **파이프라인**: L1 영상취득 → L2 전처리 → L3 DBSCAN분할 → L4 FPFH+RANSAC+ICP → L5 그래스프 → L6 Modbus
> **대표님 지시 (4/1)**: ① 문서 이해 ② 7.1 튜토리얼 ③ 논문 참고 ④ Basler 기반 개발 ⑤ 보고. **카메라 입고 전 SW 완성 필수**, OpenMV보다 우선순위 높음

### W0 학습 현황 (2026-03-23 완료)

| 구분 | 파일 수 | 줄 수 | 상태 |
|------|--------|-------|------|
| 논문 리뷰 | 3편 (FPFH, ICP, Open3D) | — | ✅ 완료 |
| 튜토리얼 (`tutorials/01~11`) | 11개 | 4,247줄 | ✅ 전체 PASS |
| 실전 코드 (`src/`) | 3개 | 1,902줄 | ✅ 전체 PASS |
| **합계** | **14개** | **6,149줄** | **✅** |

### 핵심 성과 수치

**W0~W2 (더미 데이터 시뮬)**:
| 지표 | 결과 | 목표 | 판정 |
|------|------|------|------|
| 부품당 매칭 시간 | **0.33초** | 2.0초 | ✅ 6배 여유 |
| 인식률 | **100%** (더미 3종 자기매칭) | 85% | ✅ |
| SizeFilter 효과 | 5종→2.2종 (56% 절감) | — | ✅ |

**W3+ (실제 STL 29종 기반 E2E, 4/6~4/10)**:
| 지표 | 결과 | 목표 | 판정 |
|------|------|------|------|
| 인식률 (easy, 5종) | **100%** (5/5) | 85% | ✅ |
| 인식률 (crowded, 10종) | **90%** (9/10) | 80% | ✅ |
| 인식률 (hard, 5종) | **60%** (3/5) | 85% | ⚠️ FPFH 한계, Colored ICP 필요 |
| RMSE | **1.0~1.5mm** | 3mm | ✅ 우수 |
| 매칭 시간 (OBB SizeFilter) | **0.4~0.6초** | 2.0초 | ✅ 3~5배 여유 |
| L1~L6 파이프라인 | **전체 구현 완료** | 카메라 전 SW 완성 | ✅ |
| L5 그래스프 DB | **29종 완성** | 29종 | ✅ |
| L6 Modbus TCP | 서버 동작 확인 | 로봇 실전 | 🔄 입고 후 |

### 레진별 파라미터 추천

| 레진 | voxel | Robust kernel | 비고 |
|------|-------|--------------|------|
| Grey/White | 2mm | Tukey 1mm | 표준 파라미터 |
| Clear | 3~4mm | SOR + 멀티스케일 | 반투명 → ToF 노이즈 큼 |
| Flexible | 2mm | Huber 1.5mm | 변형 허용 |

### 구현 코드 목록

| 파일 | 줄 | 역할 |
|------|-----|------|
| `tutorials/01_registration_pipeline.py` | 321 | FPFH+RANSAC+ICP 기본 |
| `tutorials/02_stl_to_reference.py` | 223 | STL→레퍼런스+FPFH 캐싱 |
| `tutorials/03_dbscan_segmentation.py` | 273 | DBSCAN 분할 |
| `tutorials/04_fgr_fast_global_registration.py` | 385 | FGR vs RANSAC |
| `tutorials/05_multiscale_icp.py` | 438 | 다중 스케일 ICP |
| `tutorials/06_registration_confidence.py` | 476 | 신뢰도 평가 |
| `tutorials/07_full_binpicking_simulation.py` | 599 | 전체 파이프라인 시뮬 |
| `tutorials/08_colored_icp.py` | 337 | Colored ICP |
| `tutorials/09_noise_robustness.py` | 481 | 노이즈 강건성 |
| `tutorials/10_pypylon_api_study.py` | 714 | pypylon API + Blaze-112 스펙 |
| `tutorials/11_noise_robustness_advanced.py` | 590 | 노이즈 심화 (Clear 대응) |
| `src/recognition/cad_library.py` | 430 | STL→레퍼런스 클라우드+FPFH 캐시 (빌드/로드/변경감지) |
| `src/recognition/size_filter.py` | 441 | 크기 사전 필터 (30→2.2종) |
| `src/recognition/pose_estimator.py` | 776 | 1:N 매칭 루프 + multi-res ICP + top-K 리파인 |
| `src/grasping/grasp_planner.py` | 250 | L5 그래스프 자세 계산 (grasp_database.yaml 기반) |
| `src/communication/modbus_server.py` | 250 | L6 Modbus TCP 서버 (pymodbus 3.x, FLOAT32) |
| `src/main_pipeline.py` | 350 | L1~L6 통합 파이프라인 (BinPickingPipeline) |
| `src/acquisition/hand_eye_calibration.py` | 842 | 핸드-아이 캘리브레이션 |
| `src/acquisition/depth_to_pointcloud.py` | 155 | depth map → Open3D PointCloud 변환 |
| `src/preprocessing/cloud_filter.py` | 236 | L2 전처리 파이프라인 (레진별 프리셋) |
| `src/segmentation/dbscan_segmenter.py` | 208 | L3 DBSCAN 분할 + Cluster 클래스 |
| `config/grasp_database.yaml` | 307 | 29종 부품별 그래스프 파라미터 정의 |
| `tests/test_e2e_redwood.py` | 240 | Redwood RGB-D E2E 5단계 테스트 |
| `tests/test_e2e_cad_matching.py` | 700 | 실제 STL 29종 기반 합성 씬 E2E (easy/medium/hard + crowded/mixed-size/stress 시나리오) |

### 7.1 필수 학습 체크리스트

| # | 항목 | 상태 |
|---|------|------|
| 1 | Open3D 공식 튜토리얼 (Registration 섹션) | ✅ tutorials 01~11 |
| 2 | pypylon 공식 예제 | ✅ tutorials/10 + 6000서버 pypylon 26.3.1 설치 (4/1) |
| 3 | Basler Blaze-112 Application Note | ⬜ pylon 설치 후 문서 폴더, 또는 웹 다운로드 필요 |

### 카메라 입고 전 할 일 (문서 4.1절)

| # | 항목 | 상태 |
|---|------|------|
| 1 | Redwood RGB-D 데이터셋으로 E2E 파이프라인 테스트 | ✅ Mac 실행 완료 (4/3) — 전체 PASS, 2.2s, fitness=1.0 |
| 2 | depth_to_pointcloud() 변환 함수 작성/검증 | ✅ 완료 (4/3) — confidence map 필터링, colored PC 지원 |
| 3 | pypylon 설치 + API 숙지 | ✅ pypylon 26.3.1 (pylon 런타임 번들 포함) |
| 4 | pylon Camera Software Suite 8.x 시스템 설치 | ➡️ 비전 PC 입고 후 |
| 5 | Blaze-112 Supplementary Package 설치 | ➡️ 비전 PC 입고 후 |

### 남은 개발 작업

| 작업 | 산출물 | 블로커 | 예상 시점 |
|------|--------|--------|----------|
| ~~공장 PC STL 25종 가져오기~~ | ~~models/cad/~~ | — | ✅ 완료 (4/6) — Google Drive 55개 → 29종 |
| ~~STL→레퍼런스 + FPFH 캐싱~~ | ~~cad_library.py~~ | — | ✅ 완료 (4/6, `b111192`) |
| ~~폴더 구조 리팩토링~~ | ~~문서 섹션 6 구조로 전환~~ | — | ✅ 완료 (4/3, `99b02fe`) |
| ~~depth_to_pointcloud + Redwood E2E~~ | ~~blaze_camera.py 스켈레톤~~ | — | ✅ 완료 (4/3, `d977890`) |
| ~~L2 전처리 모듈화~~ | ~~src/preprocessing/cloud_filter.py~~ | — | ✅ 완료 (4/3, `9517987`) |
| ~~L3 분할 모듈화~~ | ~~src/segmentation/dbscan_segmenter.py~~ | — | ✅ 완료 (4/3, `9517987`) |
| ~~L5 그래스프 계획~~ | ~~grasp_planner.py, grasp_database.yaml~~ | — | ✅ 완료 (4/6, `8c6629b`) — 17종 |
| ~~L6 로봇 통신~~ | ~~modbus_server.py~~ | — | ✅ 완료 (4/6, `8c6629b`) |
| ~~L1~L6 통합~~ | ~~main_pipeline.py~~ | — | ✅ 완료 (4/6, `8c6629b`) |
| ~~OBB SizeFilter + 포인트 비율 필터~~ | ~~size_filter.py, pose_estimator.py~~ | — | ✅ 완료 (4/8, `9cce5de`) — medium 100%, 0.5s |
| ~~E2E 난이도 테스트 (medium/hard)~~ | ~~테스트 결과 분석~~ | — | ✅ 완료 (4/8) — easy/medium 100%, hard 60% |
| ~~그래스프 DB 29종 완성~~ | ~~grasp_database.yaml~~ | — | ✅ 완료 (4/10, `2c27a9f`) — STL bbox 기반 추정 |
| ~~E2E 시나리오 확장~~ | ~~crowded/mixed-size/stress~~ | — | ✅ 완료 (4/10, `2c27a9f`) — crowded 90%, multi-res ICP |
| E2E 실패 케이스 시각화 | 매칭 결과 오버레이 PNG 자동 저장 | — | 4월 중 |
| eye-in-hand 캘리브레이션 설계 | hand_eye_calibration.py 확장 | 카메라 5월 초 | 카메라 입고 후 |
| multi-view 재촬영 파이프라인 | 로봇암 카메라 재촬영 로직 | 카메라+로봇 | 카메라 입고 후 |
| W7: 카메라 입고 + 실제 연동 | calibration.py (eye-to-hand + eye-in-hand 2세트) | 카메라 5월 초 | 5/5~5/9 |
| Colored ICP 적용 | pose_estimator.py 확장 | 카메라 입고 (RGB 필요) | 카메라 입고 후 |
| 대표님 보고 | 진행 보고서 + **실패 케이스 이미지 첨부** | — | 수시 |

---

## 기술적 제약사항 및 대안

| 제약 | 문제 | 우리 대안 |
|------|------|----------|
| Web API 읽기 전용 | 프린트 전송 불가 | Local API 병행 |
| Web API 예열/충전 미반영 | IDLE로 표시됨 | Local API 연동 시 해결 |
| ~~공장 WiFi VPN 문제~~ | ~~VPN 라우팅 깨짐~~ | ✅ 해결 (3/26): 6000 서버에 WireGuard 클라이언트 설치 (Method B) |
| .form 파일 미지원 | STL만 지원 | `POST /load-form/` 구현 필요 |
| Form Wash/Cure API 없음 | 장비 제어 불가 | OpenMV 카메라 |
| Webhook 없음 | 실시간 푸시 불가 | 15초 폴링 |

---

## 16단계 공정 흐름

| # | 공정 | 담당 |
|---|------|------|
| ① | STL 파일 업로드 | 사용자 (웹/앱) |
| ② | 프린터로 작업 전송 | 백엔드 (Local API) |
| ③ | 3D 프린팅 | Form 4 (4대) |
| ④ | 프린팅 완료 감지 | 백엔드 (Web API 폴링) |
| ⑤~⑥ | 빌드플레이트 픽업 → 세척기 투입 | HCR-12 |
| ⑦ | 세척 완료 감지 | OpenMV #1, #2 |
| ⑧ | 경화기 투입 | HCR-12 |
| ⑨ | 경화 완료 감지 | OpenMV #3, #4 |
| ⑩~⑫ | 픽업 → 서포트 제거 → 후가공 | HCR-10L |
| ⑬ | YOLO 비전 검사 | Intel RealSense |
| ⑭~⑮ | 양품/불량 분류 → 적재 | HCR-10L |
| ⑯ | 완료 보고 | 백엔드 (알림) |

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| **백엔드** | Python 3.11+, FastAPI, httpx, pydantic-settings, SQLite + SQLAlchemy |
| **프론트엔드** | React 18 + TypeScript, Vite, Tailwind CSS 4, WebSocket |
| **인프라** | Docker, WireGuard VPN |
| **Phase 3~4** | pymodbus, Ultralytics YOLO, OpenMV AE3, Edge Impulse, Mosquitto MQTT |

---

## 완성 아키텍처 설계

**설계 문서**: `.claude/plans/staged-rolling-kite.md`

### 구현 순서
1. **인프라 기반**: PostgreSQL 마이그레이션, Docker Compose 확장, 이벤트 버스, React Router
2. **Phase 3**: Modbus 클라이언트 → 로봇 API → 로봇 UI
3. **Phase 4**: MQTT 클라이언트 → OpenMV 스크립트 → 카메라/비전 API → UI
4. **통합**: FSM 엔진 → 공정 관리 UI → SaaS tenant_id → 통합 테스트

---

## 참고 링크

### Formlabs
- Web API: https://support.formlabs.com/s/article/Formlabs-Web-API
- Local API: https://formlabs-dashboard-api-resources.s3.amazonaws.com/formlabs-local-api-latest.html
- Python: https://github.com/Formlabs/formlabs-api-python

### 기타
- 한화로보틱스: robot_inquiry@hanwha.com
- YOLO: https://github.com/ultralytics/ultralytics
- Intel RealSense: https://github.com/IntelRealSense/librealsense

---

## 환경 변수 (.env)

```bash
# Formlabs Web API
FORMLABS_CLIENT_ID=your_client_id
FORMLABS_CLIENT_SECRET=your_client_secret

# PreFormServer (공장 PC VPN)
PREFORM_SERVER_HOST=10.145.113.3
PREFORM_SERVER_PORT=44388

# 공장 PC 파일 수신
FILE_RECEIVER_HOST=10.145.113.3
FILE_RECEIVER_PORT=8089

# 폴링
POLLING_INTERVAL_SECONDS=15

# 사용자 로그인 (JWT) — 셋 다 비면 인증 OFF (로컬 개발용)
AUTH_USERNAME=admin
AUTH_PASSWORD_HASH=  # bcrypt 해시 (평문 X). 생성: python -c "import bcrypt; print(bcrypt.hashpw(b'pw', bcrypt.gensalt(rounds=12)).decode())"
JWT_SECRET=          # 서버별 랜덤 32바이트. 생성: python -c "import secrets; print(secrets.token_urlsafe(32))"
JWT_EXPIRE_DAYS=7
JWT_ABSOLUTE_MAX_DAYS=30
```

---

## 사용자 인증 (JWT 로그인)

5/6부터 JWT 기반 로그인 시스템 운영. **공통 1개 계정 + 7일 sliding refresh + 30일 절대 최대**.

| 항목 | 값 |
|------|-----|
| 사용자명 | `admin` |
| 비번 | macOS 키체인 "안전한 메모" `orinu Web Login 2026-05` 참조 |
| 토큰 만료 | 7일 (사용 시 자동 연장) |
| 절대 최대 | 30일 (이후 강제 재로그인) |

### 코드 구조
- `web-api/app/core/user_auth.py` — bcrypt + JWT 핵심 로직
- `web-api/app/core/jwt_middleware.py` — ASGI 미들웨어, `X-New-Token` 헤더로 sliding refresh
- `web-api/app/api/auth_routes.py` — `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, `POST /api/v1/auth/logout`
- `frontend/src/components/LoginPage.tsx` — 다크 테마 로그인 페이지
- `frontend/src/services/auth.ts` — 토큰 관리 + `authFetch` (모든 API 호출 통과)

### 로컬 개발
`.env`에 `AUTH_USERNAME` 또는 `AUTH_PASSWORD_HASH` 또는 `JWT_SECRET` 셋 중 하나라도 비면 **인증 자동 OFF**. 로컬 새로고침 자유.

### 회전 정책
- 분기별 (3/6/9/12월 1일)
- 즉시 회전 트리거: 직원 퇴사 / 노트북 분실 / 누출 의심
- 3개 서버 동기화 필수
- 상세: `memory/project_web_auth_security.md`

---

## 자동 배포 워크플로우 (5/6~)

태민님이 코드 변경 + git push 후:

```
태민님: "배포해줘"
저: scripts/deploy_servers.sh 실행
   → 6000 서버 (로컬) + 카카오 VM (SSH) 동시 배포
   → 부팅 검증 + 외부 접속 검증 (HTTP 401 expected)
태민님: 공장 PC AnyDesk → 관리자 cmd
   → cd /d D:\3D_printer_automation_0305\3D_printer_automation
   → deploy.bat
```

**옵션** (`scripts/deploy_servers.sh`):
- `--skip-deps` — 의존성 변경 없을 때
- `--skip-build` — 백엔드만 변경 시
- `--6000-only` / `--kakao-only` — 한 서버만

---

## 한솔코에버 협업 타임라인

- ✅ HW 설계변경 및 구축 (02-25~03-18): 바렐→스핀들, 재원텍+코에버
- ✅ SW 개발 (02-26~03-19): API 분석, 로봇/비전/3D프린팅 연동, 시퀀스 개발 — 김기원(퇴사), 이나라, 이예승
- ✅ 데모 시연 (03-20): 경기ITP-코에버 3자 최종 확인 완료
- ✅ 한솔 최종 시연 (03-27): 한솔 자체 진행
- ✅ 코드 머지 1차 (04-03): `hansol-dev` → main (`9c161dc`) — 김기원 주임 코드
- ✅ 코드 머지 2차 (04-16): `hansol-dev` → main (`e68c2b1`) — 이예승 사원, 프린터 할당 기능

---

## GitHub 협업 구조 (한솔코에버)

| 항목 | 내용 |
|------|------|
| 리포 | `m2222n/3D_printer_automation` (Private) |
| main 보호 | Require PR + Restrict deletions + Block force pushes |
| 오리누 작업 | `main` 브랜치 |
| 한솔 작업 | `hansol-dev` 브랜치 |
| 한솔 권한 | Write (Collaborator: ~~`justkiwon`~~ 퇴사, `eseung97` 이예승) |
| 리모트 | `origin` = orinu-ai, `personal` = m2222n |

---

## 마지막 업데이트

- **날짜**: 2026-05-06 (수, JWT 로그인 시스템 도입 + 공장 PC SSH key 전환 + 자동 배포 스크립트)

### 5/6 — 🔥 JWT 로그인 시스템 도입 + 공장 PC SSH key 전환

**배경**: 4/24 Cloudflare Tunnel 활성 후 `factory.flickdone.com`이 **외부 인증 없는 상태로 운영 중**이었던 사고 발견 (공장 PC `.env`에 BASIC_AUTH_* 변수 누락). 이번 작업으로 Basic Auth → JWT 로그인 전면 교체 + 3개 서버 통일.

**구현**:
- 백엔드: `web-api/app/core/user_auth.py` (bcrypt + JWT) + `jwt_middleware.py` (sliding refresh) + `app/api/auth_routes.py` (login/me/logout)
- 프론트: `frontend/src/components/LoginPage.tsx` (다크 테마 React 로그인 페이지) + `services/auth.ts` (토큰 관리 + authFetch)
- 7일 sliding refresh + 30일 절대 최대. 공용 1개 계정 (`admin` / `orinu2026!`).

**3개 서버 배포 완료** (외부 검증 6/6 PASS):
- 6000 서버 / 카카오 VM / 공장 PC `factory.flickdone.com`
- 모두 React 로그인 페이지 → 토큰 발급 → API 호출 → 7일 자동 유지

**부산물**:
- ✅ **공장 PC SSH key 전환** — 4/29 PAT 의존 제거. `factory-pc-orinu` Deploy key 등록
- ✅ **카카오 VM Deploy key 추가** — `kakao-vm-orinu` 등록 → git pull 가능 (이전엔 rsync로만)
- ✅ **자동 배포 스크립트** — `scripts/deploy_servers.sh` (6000 + 카카오 VM 동시 배포)

**미래 워크플로우**:
- 6000 + 카카오 VM = 자동 (`scripts/deploy_servers.sh`)
- 공장 PC = AnyDesk 관리자 cmd → `deploy.bat` 한 줄

**커밋**: `81033a6`(JWT) + `87bc587`(루트 reqs) + `d729868`(인코딩 fix) + `7a818a7`(deploy script). 상세는 `memory/project_web_auth_security.md`, CLAUDE.local.md W19 섹션.

**TODO**:
- [ ] 4/29 발급 m2222n PAT GitHub에서 폐기 (사용자 작업)
- [ ] 예승님께 새 로그인 안내 메시지 발송 (사용자 결정)

---

### 4/30 새벽 — 재부팅 자동복구 검증 + 공장 PC 배포 단순화 (deploy.bat smoke test 완료)
- **재부팅 자동복구 검증 ✅** — 공장 PC 물리 재부팅 → 외부 curl 검증. cloudflared + NSSM(OrinuMain) + web-api(8085) + PreFormServer(44388) + Cloud API 폴링 전체 자동 복구. 4/24 NSSM 등록 후 4/29 git pull로 추가된 의존성(aiomqtt) 포함 전체 스택 정상 부팅 확인
- **예승님 4/30 답변 정리** — 프리셋 생성/제거 + 자동화 탭 OK. 소스 수정 흐름은 로컬 → hansol-dev push로 안내. 현재 `SIMUL_MODE=true`는 예승님이 디버깅용으로 설정한 상태(git pull은 .env 안 건드림). 다음주 방문 시 실제 출력/로봇 E2E 테스트 예정
- **`deploy.bat` 도입 + smoke test 완료** ⭐ — 4/29 수동 9단계 → 1줄(`deploy.bat`). 5단계(git pull --ff-only / pip / npm build / nssm restart / health check) 각각 errorlevel abort로 라이브 보존. 공장 PC AnyDesk에서 GCM helper 설정 + Fast-forward pull + 관리자 cmd로 실행 → vite build + NSSM stop/start + HTTP 200 검증 + 외부 `factory.flickdone.com` 200 OK 검증 완료
- **⚠️ 미해결**: `git fetch` 시 인증창이 안 뜬 이유 미확정 (4/29 PAT 캐시 추정, 5월 말 만료 시 재검증 예정). 상세: `memory/project_deploy_bat.md` 미해결 의문 섹션

### 4/29 — 🔥 공장 PC 프리셋 API 500 → 원격(AnyDesk)으로 완전 해결
- **진짜 원인 (오전 추정과 다름)**: 공장 PC origin이 `justkiwon/3D_printer_automation` (퇴사자 fork) 가리킴 → 회사 `orinu-ai/3D_printer_automation` main과 **100커밋 차이** + git pull 후 새 의존성 `aiomqtt` 미설치로 web-api 부팅 실패
- **조치**: PAT로 origin URL 정정 → fast-forward pull (`1104a06` → `1272ddb`) → `pip install -r requirements.txt` → frontend rebuild → NSSM 재시작 (좀비 정리 포함)
- **검증**: 프리셋 API → HTTP 200 + JSON 정상 반환
- **함정 7가지**: AnyDesk 한국어 cmd 인코딩, Git for Windows CRLF phantom 13,682개, Hansol 작품 untracked, NSSM Services 좀비 vs Console 사용자 세션 구분, `nssm` PATH 미등록, NSSM이 자식 프로세스 stderr 못 잡는 문제, `requirements.txt` 어긋남
- **상세**: `memory/project_factory_pc_remote_recovery_0429.md`

### 4/24 주요 완료 항목 (이전 업데이트)

### 4/24 오전 완료 (Cloudflare Tunnel 기본 세팅)
1. **한솔 머지 3차 잔존 이슈 수정 ✅** — `bcb8e29` 커밋 (runtime.py:121 하드코딩 제거), origin + personal push 완료
2. **Cloudflare Tunnel `orinu-factory` 생성 ✅** — 터널 ID `b939f49b-e265-407d-b83f-247f7b4cb82c`
3. **공장 PC cloudflared 설치 + 서비스 RUNNING ✅** — Active replicas 1, Edge Location 서울(ICN)
4. **DNS CNAME 활성 ✅** — `factory.flickdone.com` → `b939f49b-...cfargotunnel.com`
5. **Route 매핑 ✅** — Service URL `http://localhost:8085` (초기 `https://` 입력 후 `http://`로 수정)

### 4/24 점심 전후 (`python main.py` 기동 + Page Rule 해결)
- 공장 PC 배포 경로 식별: **`D:\3D_printer_automation_0305\3D_printer_automation`** (예승님 답변)
- 환경 점검: Python 3.14.3, Node v24, **MariaDB 11.3 설치·자동시작 중** (4/24 오후 재조사에서 확인, 오전 "MySQL 미설치" 기록은 오해였음), `.venv` 이미 생성, `.env` 존재
- **`python main.py` 수동 기동 성공** — web-api 8085 LISTENING, sequence_service active (automation DB에 이력 정상 적재)
- 공장 PC 로컬: `curl http://127.0.0.1:8085/` → `<title>3D 프린터 자동화 시스템</title>` ✅
- **Cloudflare Page Rules 충돌 발견 + 해결 ✅**:
  - Rule #1 `*flickdone.com/*` → `orinu.org/$1` (301 Permanent Redirect) 발견
  - 누가 언제 왜 만들었는지 불명 → **Disable 처리** (Delete는 안전상 지양)
  - 검증: 6000 서버 `curl -I https://factory.flickdone.com/` → HTTP 200 + React HTML ✅

### 4/24 점심 후 일시 장애 (자연 복구)
- Mac 캐시 삭제 중 **AnyDesk + Cloudflare Tunnel 530 동시 끊김**
- 공장 PC 공인 IP ping 4/4 성공 → 공장 PC 자체 의심하고 공장 방문
- 공장 도착 시점에는 **이미 자연 복구** (AnyDesk 정상, 외부 접속 200 OK)
- 원인 특정 불가, 일시 장애로 결론

### 4/24 오후 공장 방문 완료 (NSSM 자동 시작 등록) ⭐
**목표**: `python main.py` 수동 실행 → Windows 서비스로 승격해서 재부팅/크래시 자동 복구 보장

1. **NSSM 2.24 다운로드 + 설치 ✅**
   - 공장 PC 브라우저 `https://nssm.cc/release/nssm-2.24.zip` → **503 Service Temporarily Unavailable**
   - **우회법**: cmd에서 `curl -L -o ...` 직접 다운로드 성공 (공장 ISP의 브라우저 경로 이슈 추정)
   - 최종 경로: `C:\nssm\nssm-2.24\win64\nssm.exe` (공식 빌드 331,264 bytes)

2. **OrinuMain Windows 서비스 등록 ✅**
   - `C:\nssm\nssm-2.24\win64\nssm.exe install OrinuMain` (관리자 cmd)
   - Path: `D:\3D_printer_automation_0305\3D_printer_automation\.venv\Scripts\python.exe`
   - Startup directory: `D:\3D_printer_automation_0305\3D_printer_automation`
   - Arguments: `main.py`
   - Startup type: Automatic
   - 로그: `D:\3D_printer_automation_0305\logs\orinu_stdout.log` / `orinu_stderr.log`

3. **자동 복구 검증 ✅**
   - `taskkill /F /PID <web-api_pid>` → 서비스 자동 재시작 → 새 PID로 8085 LISTENING 재확인
   - 외부 `curl https://factory.flickdone.com/` → HTTP 200 ✅
   - 결론: 공장 PC 재부팅/정전/크래시에도 휴가 중 자동 복구 보장

### NSSM 운영 노트 (트러블슈팅 중 배운 것)
- **`nssm` 명령은 PATH 미등록** → 항상 전체 경로 `C:\nssm\nssm-2.24\win64\nssm.exe` 사용
- **로그는 런처만 캡처** — `orinu_stderr.log`엔 `Starting web-api`, `All services started` 등 런처 출력만. web-api subprocess의 uvicorn 로그는 캡처 안 됨
- **재시작 후 초기화 15~20초** — uvicorn + sequence_service + DB + 프린터 Modbus 시도 때문에 즉시 netstat 찍으면 LISTENING 안 보임 → `timeout /t 20` 필수
- **python 좀비 처리** — 기동 실패 반복 시 python.exe 5~6개 떠있음. `taskkill /F /IM python.exe`로 싹 정리 후 재시작하면 해결
- **Frontend skip 정상** — `START_FRONTEND` 환경변수 없어서 Vite dev 안 띄움. web-api가 `frontend/dist/` 정적 서빙하므로 영향 없음

### 공장 PC 운영 명령어 (관리자 cmd)
```cmd
# 상태 확인
sc query OrinuMain                                  # STATE : 4 RUNNING 기대
sc query cloudflared                                # Tunnel 서비스 상태
netstat -ano | findstr LISTENING | findstr 8085    # 0.0.0.0:8085 LISTENING

# 재시작
C:\nssm\nssm-2.24\win64\nssm.exe restart OrinuMain

# 완전 정리 후 재시작 (좀비 발생 시)
C:\nssm\nssm-2.24\win64\nssm.exe stop OrinuMain
taskkill /F /IM python.exe
timeout /t 5
C:\nssm\nssm-2.24\win64\nssm.exe start OrinuMain
timeout /t 20
```

### 오늘 남은 작업 (4/24 퇴근 전)
- [x] 🚨 **Formlabs Client Secret Rotate** — Developer Portal Rotate 완료, 3곳 전부 반영 ✅
  - [x] 6000 서버 `~/3D_printer_automation/web-api/.env` — `api.formlabs.com HTTP/1.1 200 OK` 검증
  - [x] 카카오 VM `/home/ubuntu/3D_printer_automation/web-api/.env` — SSH `~/.ssh/kakao_key`로 접속, `systemctl --user restart formlabs-web` 후 `📊 4대 프린터 상태 조회 완료` 검증
  - [x] 공장 PC `D:\3D_printer_automation_0305\3D_printer_automation\web-api\.env` — AnyDesk notepad 편집 + `nssm restart OrinuMain` → RUNNING + 8085 LISTENING(PID 17276) + 외부 HTML 200
- [ ] 예승님께 최종 안내 메시지 (URL + 4/28 테스트 가능 범위)
- [ ] Cloudflare Backup Codes 생성 (여유되면)

### 공장 PC 재부팅 시 자동 시작되는 것 (4/24 완성 체계)
> 휴가 중 정전/재부팅에도 전원 ON만으로 운영 시스템 전체가 자동 복구됨.

| # | 이름 | 종류 | 포트 | 역할 |
|---|------|------|------|------|
| 1 | **cloudflared** | Windows 서비스 | - | Cloudflare Tunnel (`factory.flickdone.com` 외부 접속) |
| 2 | **OrinuMain** ⭐ | Windows 서비스 (NSSM) | 8085 | `python main.py` (web-api + sequence_service + frontend 정적 서빙) |
| 3 | **PreFormServer** | 시작 프로그램 바로가기 | 44388 | Formlabs Local API (프린트 작업 전송) |
| +a | file_receiver.py | 시작 프로그램 | 8089 | STL 파일 수신 |
| +a | AnyDesk | Windows 서비스 | - | 원격 접속 |

**NSSM (Non-Sucking Service Manager)**: `python main.py` 같은 일반 프로그램을 Windows 서비스로 포장해주는 오픈소스 도구. 재부팅 자동 시작 + 크래시 자동 재시작 + 로그 파일 저장. 설치 경로 `C:\nssm\nssm-2.24\win64\nssm.exe` (PATH 미등록, 항상 전체 경로 사용).

**재부팅 후 체크 (cmd)**:
```cmd
sc query cloudflared
sc query OrinuMain
netstat -ano | findstr LISTENING | findstr "8085 44388 8089"
curl http://127.0.0.1:8085/
```

**상세 복구 가이드**: `~/.claude/projects/-home-jtm/memory/reference_factory_pc_deployment_guide.md`의 "재부팅 후 자동 시작 체계" 섹션

---

## DB 아키텍처 현황 (4/24 확정)

### 서버별 DB 구성

| 서버 | DB | 용도 | 상태 |
|------|-----|------|------|
| **공장 PC** | **MariaDB 11.3** (port 3306) | sequence_service 자동화 로그 (`automation` DB) | ✅ 서비스 AUTO_START, 실행 중 |
| **공장 PC** | SQLite (`web-api/data/local.db`) | web-api 프리셋/알림/업로드 이력 | ✅ 동작 중 |
| **6000 서버** | SQLite | web-api 모니터링 전용 | ✅ |
| **카카오 VM** | SQLite | web-api 모니터링 전용 | ✅ |

### MariaDB (공장 PC) 상세

| 항목 | 값 |
|------|-----|
| 설치 경로 | `C:\Program Files\MariaDB 11.3\` |
| 설정 파일 | `C:\Program Files\MariaDB 11.3\data\my.ini` |
| Windows 서비스 | `MariaDB` (AUTO_START, NT SERVICE\MariaDB 계정) |
| 포트 | 3306 (`0.0.0.0:3306` LISTENING — 4/28에 `127.0.0.1`로 제한 예정) |
| 업무 DB | `automation` (한솔 sequence_service가 연결) |
| 시스템 DB | information_schema, mysql, performance_schema, sys |

### ⚠️ 문서 오류 정정
- 4/24 **오전 기록의 "MySQL 미설치"는 오해**. 실제는 MariaDB가 설치되어 있었으나 `where mysql`·`sc query MySQL80`만 확인하고 놓친 것
- 오해 이유: MariaDB 클라이언트(`mysql.exe`)가 PATH에 없었고, Windows 서비스 이름이 `MariaDB`로 등록 (MySQL/MySQL80 아님)
- 올바른 확인 방법: `netstat -ano | findstr :3306` → LISTENING PID 확인 → `tasklist /FI "PID eq <pid>"` → `mysqld.exe` 나오면 DB 있음

### 원격 DB 접근 (옵션 2c — 4/28 구현 예정)

**배경**: 4/23 회의에서 "설비제어 로컬 유지 + 원격 UI는 Cloudflare Tunnel 경유"로 합의 (옵션 2c). 예승님 4/24 질문 "클라우드에서 공장 DB 읽을 수 있냐?" 요구사항 충족 목적.

**기술적 가능성**: ✅ **가능**. Cloudflare Tunnel은 HTTP뿐 아니라 임의 TCP(MySQL wire protocol 포함) 운반 가능. 기존 `orinu-factory` 터널에 ingress 규칙 추가만 하면 됨.

**구조**:
```
카카오 VM ── cloudflared(127.0.0.1:3307) ──→ CF Edge(ICN) ──→ 공장 PC cloudflared ──→ MariaDB(127.0.0.1:3306)
```
- 카카오 VM에 cloudflared 프록시 추가 설치 필요 (HTTP과 달리 TCP는 Edge가 공개 포트 안 열어줌)
- Cloudflare Access Service Token으로 인증 (서버-서버 자동화용)
- MariaDB에 `remote_readonly` 계정 분리 + SELECT만 허용
- 실시간 제어(sequence_service)는 터널 경유 **절대 금지** — 공장 로컬 직결 유지, 터널은 **원격 조회/분석 전용**

**4/28 작업**: `memory/project_sequence_service_deployment.md`의 "옵션 2c 구체 구현 가이드" 참조. 예상 1.5~2시간.

**대표님 논의 필요**: 범위(읽기 전용만 vs 쓰기 권한도) + 보안 강화 수준 + Cloudflare Access 비용 (Free 플랜 Service Token 25개까지 무료)

### 🔒 보안 원칙 (절대 금지)

- ❌ MariaDB 3306을 공유기 포트포워딩으로 인터넷에 직접 노출
- ❌ Cloudflare Tunnel에 TCP ingress만 추가하고 Access 없이 방치
- ❌ sequence_service 같은 실시간 제어 서비스가 터널 경유 DB로 변경 (인터넷 장애 시 로봇 정지)

### Formlabs Credentials 관리 메모 (4/24 배운 것)
- Formlabs Developer Portal의 "Rotate Client Secret" 작업은 **Client ID도 같이 바뀜** (기존 ID는 즉시 무효화)
- 반영 장소: 서버별 `.env`의 **`FORMLABS_CLIENT_ID`, `FORMLABS_CLIENT_SECRET` 두 줄 모두** 교체
- 반영 누락 시 해당 서버는 Formlabs API 호출이 401로 실패하며 폴링 전체가 멈춤 — journalctl로 즉시 확인 가능
- 스크린샷/문서 공유 시 `.env` 파일은 모자이크 처리 필수 (공개 채널 절대 금지)

### 4/28 예승님 방문 시 / 이후
- ~~MySQL 설치~~ **✅ 이미 MariaDB 11.3 설치·실행 중 (4/24 확인)**. DB Back260305.sql 복원 여부는 `automation` DB 현재 데이터 검토 후 판단
- **옵션 2c 완성 — Cloudflare Tunnel TCP ingress 추가 (`factory-db.flickdone.com` → `tcp://localhost:3306`)** + Access Service Token 발급 + 카카오 VM에 cloudflared 프록시 설치 (상세: `memory/project_sequence_service_deployment.md` "옵션 2c 구체 구현 가이드")
- MariaDB 보안 강화: `my.ini`에 `bind-address=127.0.0.1` 추가 + 원격 조회 전용 계정(`remote_readonly`) 분리
- `git pull`로 소스 최신화 (예승님 공조, 공장 PC는 3/5 스냅샷 박제 상태)
- Basic Auth 또는 Cloudflare Zero Trust Access 추가
- 카카오 VM `.env` 호스트 변경 (`PREFORM_SERVER_HOST=factory.flickdone.com`)
- 6000 서버 웹 서비스 중지 여부 결정
- `orinu.org` 도메인 소유자/용도 대표님께 확인 (Page Rule #1 존재 이유)

### 상세 운영/트러블슈팅 레퍼런스
- [Cloudflare Tunnel 전체 설정 + NSSM 운영 명령어](../.claude/projects/-home-jtm/memory/project_cloudflare_tunnel.md)
- [공장 PC 배포 가이드](../.claude/projects/-home-jtm/memory/reference_factory_pc_deployment_guide.md)

## ⏰ 태민 휴가
- 4/27(월)~28(화) 휴가. 4/28 당일 예승님 현장 방문 예정.
- ✅ **NSSM 등록 + 자동 복구 검증 완료** — 휴가 중 공장 PC 재부팅/정전에도 안정 운용 가능

---

### 4/23 저녁 작업 요약 (이전 업데이트)

- **날짜**: 2026-04-23 (목, 공장 방문 + 저녁 작업 완료)
- **오늘 완료 작업 (4/23)**:
  1. **하드웨어 입고 3건 확인 ✅** — Basler 카메라(Blaze-112 + ace2), 산업용 PC(IPC-510), Cloudflare 권한 활성
  2. **예승+파트장(김주엽) 3자 회의 완료** — 14개 안건 논의, CLAUDE.local.md 상세 기록
  3. **한솔 머지 3차 완료** — `9f97f1e` (경화기 2→1대 축소, origin+personal push 완료)
  4. **4/24 대표님 회의자료 2종 작성** — [meeting_0424_ceo.md](docs/meeting_0424_ceo.md) 내부용 + [meeting_0424_ceo_pdf.md](docs/meeting_0424_ceo_pdf.md) 웹 Claude PDF 업로드용
  5. **Cloudflare Tunnel 실행 가이드 준비** — 내일(4/24) 마감 목표, 단계별 체크리스트
- **현재 상태 요약**:
  - **빈피킹 컨셉 미확정 — 대표님 4/24 논의**: 펼쳐서(A) / 차곡차곡(B) / 무작위 힙(C) 중 결정 필요
  - **Cloudflare Tunnel 방향 확정 (현장 합의)**: 설비제어는 로컬 유지 + 원격 UI는 Tunnel 경유 = 옵션 2c. 예승님 동의 ("안 되면 로컬로 내려도 OK")
  - **카메라 설치 방식 합의**: 로봇 암 장착(eye-in-hand) + Blaze-112 + ace2 동시 마운트. 브라켓은 3D 프린팅 vs 외부 가공 결정 필요
  - **이관 대기 항목** (한솔이 가이드/소스 제공):
    - 빈피킹 좌표 → 로봇 전송 인터페이스 (현재 Modbus 구조 유지 가능성 크나 확정 대기)
    - 바텀 비전 홀 검출 소스코드 (한솔 공유 예정)
  - **관찰 이슈**:
    - 스핀 3개 중 2개 ON/OFF 동시 작동 (하드웨어 제어 계통 공유 의심)
    - `runtime.py:121` cure_active_cmd 리셋 하드코딩 잔존 (예승님 패치 불완전, 후속 논의 필요)

- **내일(4/24) 일정**:
  - 오전: 대표님 논의 — 빈피킹 컨셉 + Cloudflare Tunnel 범위 + 브라켓 제작 방식 + sequence_service 배포 정책 + 경화기 축소 보고 범위 + IPC-510 스펙 + 스핀 이슈
  - 오후: **Cloudflare Tunnel 설정 마감** (대표님 범위 결정 직후 착수, 공장 PC cloudflared 설치)

### 4/22 오후 — 데모 리허설 피드백 반영 (서버↔Mac 양방향 작업)
- **Mac 리허설에서 크래시 2건 방어** (`ac0f283`, Mac 커밋)
  - `cloud_filter.remove_plane`: 포인트 < `plane_ransac_n`일 때 segment_plane() 크래시 → 원본 반환 + stats `plane_skipped` 마킹
  - `demo_live_recognition` capture 핸들러: 파이프라인 크래시 시 GUI 전체 종료 → try/except로 WARN 로그만
- **[B] ROI/depth 기본값 3개 정합성 이슈 → 옵션 1(Basler 기준) 채택** (`c3a8477`)
  - 기존: `DEFAULT_ROI z=0.005~0.20` / `depth_to_pointcloud depth_min=0.3` / `SyntheticSource depth=0.55~0.80` 세 값이 서로 다른 세팅 기준 → --synthetic은 ROI crop 후 포인트 0으로 RANSAC 크래시, --realsense도 ACCEPT 0 빈번
  - 해결: Basler 오버헤드(40~80cm) 기준으로 `DEFAULT_ROI z=0.30~1.00` 통일, `SyntheticSource`/`depth_to_pointcloud` 기본값 유지 → 3값 정합
  - D435 근접 테스트용 CLI 오버라이드 4개 추가: `--roi-z-min/-max`, `--depth-min/-max` (main_pipeline.py + demo_live_recognition.py 양쪽)
- **[C] 데모 UI 3건 개선** (`696860f`)
  - ACCEPT 뱃지: 좌상단 → 우상단, 폰트 0.9/th2 → 0.6/th1 (좌하 CAD 오버레이 가림 해소)
  - 셀 타이틀 폰트 0.55/th1 → 0.8/th2, title_h 32 → 38px (시연 중 포인터 가독성)
  - Filtered 라인에 kept% 병기 (예: `10,115 (3.3% kept, 23.4 ms)`)
- **[추가] synthetic 매칭 9.7s → 1.5s + Matches 테이블 재작성** (`b63f4bf`)
  - SyntheticSource noise σ 3 → 1: DBSCAN eps 8mm 안에서 노이즈가 별도 클러스터로 튀던 문제 → 36 클러스터 → 3 클러스터, L4 Matching 9240ms → 1158ms (8배 단축)
  - Matches 테이블을 고정 x 좌표 5컬럼(#, Part, Fit, RMSE(mm), Dec)로 재작성 (단일 f-string mono-font 가정 제거)
  - RMSE 단위 버그 수정: 값은 mm인데 표시는 "1.23m"로 오독되던 문제 → 헤더에 `(mm)` 명시, 값은 단위 기호 제거
- **Mac 검증 결과**: Clusters 3개, L4 1158ms, Total 1.5s, 테이블 정렬/RMSE 단위/3상태 색상 코딩 모두 정상 — 시연 준비 완료
- **6000 서버는 AVX2 미지원으로 Open3D 실행 불가** — 렌더 검증은 Mac에서만
- **커밋 요약 (오늘 총 6건)**:
  - `eb730ba` D435 버그 3개 (빈 pcd 법선, ROI 바닥 휴리스틱, top-K) — Mac 오전
  - `36469aa` D435 진단 헬퍼 스크립트 3종 — Mac 오전
  - `ac0f283` 리허설 크래시 방어 2건 (RANSAC/GUI) — Mac 리허설
  - `c3a8477` [B] ROI/depth 기본값 Basler 기준 통일 + CLI 오버라이드 — 서버
  - `696860f` [C] 뱃지·타이틀·Filtered% UI 개선 3건 — 서버
  - `b63f4bf` synthetic 9.7s→1.5s + Matches 테이블 재작성 — 서버

### 4/22 — D435 실물 브래킷 CAD 매칭 시도 + 버그 수정
- ✅ **실물 SLA 부품 2개 수령** (공장, 서포트 제거됨, H자 브래킷 형상, bracket_sen_1 추정)
- ✅ **Mac D435 full pipeline 실데이터 완주** — 이전까지는 Redwood/합성/일반사물만
- ✅ **버그 3개 발견 + 수정** (Mac, 커밋/푸시 필요):
  - `cloud_filter.py`: 빈 pcd 법선 추정 크래시 방어
  - `test_d435_full_pipeline.py`:
    - PointCloud 0-pts 가드 + depth 범위 진단 로그
    - `compute_auto_roi` 바닥 휴리스틱이 **탑다운 뷰에서 브래킷 상면을 잘라내는 버그** 수정 (z=카메라거리 혼동)
    - top-K 전체 표시 (기존은 rank==0만)
    - `--only` 키워드 옵션 — SizeFilter 우회, 카테고리 집중 매칭
- ✅ **진단 헬퍼 스크립트 3종 추가**: `run_bracket_retry.sh`, `check_saved_frame.sh`, `identify_bracket_live.py`
- ⚠️ **CAD 확정 불가 — 하드웨어 제약이 근본 원인**:
  - USB 짧음 → 카메라 20cm 고정이 한계
  - D435 640×480 최적 거리 28cm 미달 → depth unique 값 13개 (정상 30~50)
  - Z축 두께 50% 오차 (16mm → 7mm)
  - SizeFilter 탈락 + 3회 실행 3개 결과 (FGR/RANSAC seed 미고정)
  - bracket_sen_1 fitness 0.00~0.16 (FPFH 대응점 부족)
- 📝 **결론**: D435는 어차피 Basler 오기 전 임시 검증용 → 깊게 파지 않음. **파이프라인 버그 3개 + 진단 인프라**는 Basler 넘어가도 그대로 자산

### 4/21 — 도메인 확정 + D435 USB 케이블 테스트
- ✅ **도메인 확정**: `factory.flickdone.com` (대표님 flickdone.com 서브도메인 사용 승인)
  - 향후 flickdone.com을 제조공정 자동화 브랜드로 사용 예정
  - Cloudflare 계정 초대 대표님께 요청 완료 → 권한 대기 중
  - 파리드님 Cloudflare 권한 없음 → **태민님이 직접 진행** 예정
- ✅ **카카오 클라우드 IAM Admin 권한 확보** — VM/보안 그룹 직접 관리 가능
- ✅ **D435 USB 3.2 20Gbps 케이블 테스트** — 정상 인식 (S/N 420122070194, USB 3.2)
  - 대표님 구매, D435 자체 Gen 1(5Gbps) 한계이나 신호 품질 향상
  - RealSense Viewer (brew librealsense 2.57.7) — RGB+Depth+IR 4스트림 정상 확인

### 4/16 — 카카오 클라우드 VM 이전 + 한솔 머지 2차
- ✅ **한솔 머지 2차 완료** (`e68c2b1`) — 이예승 사원 `74584fb` cherry-pick. 자동화 CMD 프린터 할당 + .env.copy 추가
- ✅ **카카오 VM 세팅 완료** (내부 동작 확인):
  - rsync로 소스 전송 (.git 포함, 최신 `e68c2b1`)
  - Python 3.12.3 venv + 의존성 설치 완료
  - Node.js 18 설치, frontend dist 전송
  - systemd user service 등록 + enable + linger (자동 시작)
  - **localhost:8085 API 정상** — 프린터 4대 Cloud API 폴링 동작, 프론트엔드 HTML 서빙 확인
- ✅ **카카오 VM 외부 접속 성공** — `http://61.109.239.142:8085/` 정상 동작
  - 보안 그룹 서브넷 마스크 오류 → 파리드님 수정 후 해결
  - Cloud API 폴링 + 프론트엔드 서빙 + 프린터 4대 데이터 모두 정상
  - ufw inactive (방화벽 비활성), systemd 자동 시작 설정 완료
- ✅ **Basic Auth 구현** — 공인 IP 노출로 인한 보안 조치
  - Raw ASGI 미들웨어 (`basic_auth.py`): HTTP + WebSocket 모두 보호
  - `.env`에서 `BASIC_AUTH_USERNAME` / `BASIC_AUTH_PASSWORD` 설정 (비우면 비활성화)
  - 6000 서버 + 카카오 VM 양쪽 적용 완료, 테스트 PASS
  - TODO: 로그인 페이지 + JWT 토큰 방식으로 업그레이드 (나중에)
- **공장 PC 연결 방침 (4/17 결정)**: 도메인 확정 후 **Cloudflare Tunnel**로 연결. 임시 포트포워딩은 안 함.
  - 상용화 목표 + 현장 관리자 채용 예정 → 확장 가능한 방식 채택
  - 도메인 대기 중 (대표님이 새 도메인 구매 후 알려주실 예정)
  - 그 사이 프린터 제어가 필요하면 6000 서버(VPN 경유)로 사용
- **한솔 예승님 확인**: sequence_service는 공장 PC(현장)에서 실행 — 로컬 MySQL로 자동화 시퀀스 로그 관리

### 4/14 — HCR-10L 로봇 코드 정비 + D435 Full Pipeline PASS
- ✅ `grasp_database.yaml`에 HCR-10L 로봇 스펙 섹션 추가 (TCP 오프셋, 관절 제한, 작업 영역, 안전 파라미터)
- ✅ `grasp_planner.py`에 `validate_pick()` 안전 검증 로직 추가 (작업 영역/Z충돌/힘 제한)
- ✅ `modbus_server.py`에 오일러 컨벤션(ZYX) 명시 + 피킹 사이클 문서화 + `wait_for_done()` 추가
- ✅ `hand_eye_calibration.py`에 `set_tcp_offset()` + `load_tcp_offset_from_yaml()` 추가
- ✅ **D435 Full Pipeline (L1~L5) 테스트 2회 PASS** — 일반 사물, 2회 모두 ACCEPT 0 (오탐 없음). RMSE 3mm 임계값이 핵심 안전장치
- ⚠️ TCP 오프셋, 작업 영역, 오일러 컨벤션 = TBD (그리퍼 장착 + 빈 배치 후 설정)

### 4/13 완료
- ✅ D435 라이브 연동 — USB 3.2, pyrealsense2 v2.57.7 소스빌드, 프레임 저장/로드
- ✅ D435 실데이터 L1~L3 — 일반 사물로 파이프라인 검증 (11클러스터, 0.29s)
- ✅ E2E 실패 케이스 시각화 — `--save-viz` PNG 자동 저장 (대표님 요청)
- ✅ eye-in-hand 캘리브레이션 — 시뮬 PASS (회전 0.28°, 이동 0.57mm)

### 다음 작업
- 🟡 **Cloudflare Tunnel 설정** — 계정 초대 받으면 즉시 진행 (`factory.flickdone.com`)
- 🟡 **실물 SLA 부품 확보** → D435로 오버헤드(~50cm) 촬영 → CAD 매칭 ACCEPT 검증
- 🟡 **[한솔 협업]** 이예승 사원 — sequence_service 공장 PC 배포
- 🔄 **카메라 입고 대기 (5월)** → Colored ICP + 실제 핸드-아이 캘리브레이션 (2세트) + multi-view 재촬영

### 대기 중
- ⏳ **Cloudflare 계정 초대** (대표님) → Tunnel 설정 → 공장 PC 연결 + 6000 서버 웹 서비스 중지
- ⬜ Basic Auth → 로그인 페이지 + JWT 업그레이드 (나중에)
- ⬜ MaixCAM 장비 모니터링 PoC (빈피킹 우선, 여유 시)
- ⬜ GitHub deploy key 등록 — 카카오 VM에서 직접 git pull 가능하도록

### 서버 운영 현황 (4/21)
| 서버 | URL | 역할 | 상태 |
|------|-----|------|------|
| **카카오 VM** | `http://61.109.239.142:8085/` | 모니터링 (Cloud API) | ✅ 운영 중 (Basic Auth) |
| **6000 서버** | `http://106.244.6.242:8085/` | 모니터링 + 프린터 제어 (VPN) | ✅ 병행 운영 |
| **6000 서버** | SSH | 개발 환경 (Claude Code, git) | ✅ |
| **Mac** | 로컬 | 빈피킹 개발 (Open3D) | ✅ |
| **공장 PC** | AnyDesk | PreFormServer + file_receiver + sequence_service | ✅ |
