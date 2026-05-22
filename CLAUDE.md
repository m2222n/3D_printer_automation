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

## ⭐ 빈피킹 프로젝트 북극성 (North Star) — 모든 의사결정의 최상위 기준

> **2026-05-21 사용자 명시**: "우리의 목적은 학습이 잘 되어서 카메라로 잘 인식해서 로봇이 결국 빈피킹을 잘하는거니까, 성공적인 빈피킹 프로젝트가 되도록 안내해줘. 이 내용은 가장 중요한 내용이지 메모하고 있어."

```
학습이 잘 됨  →  카메라가 잘 인식  →  로봇이 빈피킹을 잘 수행
```

**모든 작업 시작 전 자문**: "이 작업이 카메라 인식 잘 되고 로봇 빈피킹 잘 되는 데 기여하나?"

**중간 산출물은 다 수단**: mAP 수치, annotation 양, 모델 크기, 코드 라인 수 → 모두 목적이 아닌 수단

상세 (Tier 1/2/3 분류 + 함정 5가지 + 진행률 표): `memory/project_binpicking_north_star_0521.md`

---

## ⭐ 빈피킹 일정 재정렬 (2026-05-22 대표님 통화)

**핵심**: 빈피킹 실 시연 = **가을 (9~10월)** 협력사 페이스. 그동안 우리 = 학습 + 카메라 완성도.

### 단계별 일정 (재정렬)
| 단계 | 목표 | 마일스톤 |
|------|------|--------|
| A. 학습 | v2/v3 완성 + 7클래스 통합 + 도메인 매칭 | 5~7월 |
| B. 카메라 인식 | mAP50 0.95+, 실전 occlusion 검증, 라이브 30fps | 6~8월 |
| C. 좌표 출력 | 6요소 YAML/JSON + 한솔 인터페이스 합의 | 6월 초 |
| D. 로봇 E2E | YOLO → Modbus → HCR-10L | **가을 (9~10월)** |
| E. 실연동 | 공장 빈에서 실 피킹 | **가을 (9~10월)** |

### 우선순위 변경
- **P0 (빈피킹)**: 학습 + 카메라 개발 집중 (실 로봇 시연 약속 X)
- **P1 (전공정)**: 그리퍼 교체 (한솔과 조만간 회의, 별도 트랙)

### 함정 회피 (5/22 신규)
"가을 페이스니까 천천히" 자만 X — 시간 여유 = A/B/C 완성도 끝까지 끌어올리는 시간

상세: `memory/project_binpicking_timeline_realignment_0522.md`

---

## ⭐ 빈피킹 AI 프레임워크 결정 (2026-05-22)

**결정**: PyTorch + Ultralytics (TensorFlow 안 씀)

**파이프라인**:
```
[학습]  AICA A100 (PyTorch 2.1 + CUDA 11.8 + Ultralytics 8.4.51)
   ↓ best.pt
[변환]  ONNX (산업 표준, yolo export format=onnx)
   ↓ best.onnx
[배포]  IPC-510 (NVIDIA GPU, ONNXRuntime-GPU)
   ↓ 추론
[출력]  6요소 YAML/JSON (x, y, z, edge, angle, label) — `detect_and_output.py`
   ↓
[통신]  한솔 시스템 → Modbus → HCR-10L
```

**TF 안 쓰는 이유 (대표님 보고 답변)**:
1. YOLOv8/v11 = PyTorch 전용 (한솔 권고와 일치)
2. 산업 표준 = PyTorch → ONNX → 어디서나 배포
3. AICA + 한솔 + 우리 코드 = 모두 PyTorch 진영

**미확정 (다음 단계)**:
- IPC-510 정확한 GPU 모델 확인 (5/29~ 셋업 시)
- v2 학습 결과 분석 (5/23 토 또는 5/26 화)
- ONNX 변환 + 한솔 인터페이스 합의 (6월 초)

상세 (대표님 추가 질문 답변 + 다른 옵션 비교): `memory/project_yolo_framework_decision.md` + `memory/project_ai_deployment_landscape.md`

---

## 대표님 피드백 (핵심 결정사항)

> 시간 순이 아닌 **주제별 결정 흐름**으로 정리. 구식 결정도 "왜 정하고 왜 바뀌었는지" 보존.

### 1. 개발 방향성 (2025.01~2026.02)

**자체 개발 병행 결정 (2025.01.28~30)**
- 한솔 의존도 낮추기 위해 자체 Web API 방식 병행 개발 + 모바일 모니터링 강조
- 목표: 설 전 API 구축 완료 → ✅ Phase 1 완료

**공장 PC 설치 + SaaS 방향 (2026.02.04)**
- 공장 PC 설치 확정 (Linux 의도였으나 실제는 Windows로 진행됨)
- SaaS 플랫폼 구축 예정
- 세척기/경화기 완료 감지 = OpenMV 카메라 (02-06 확정) → **2026.04.14에 MaixCAM으로 전환** (마일스톤 표 참조)

**2/12 데모 후 PreForm 동등 구현 지시**
- 슬라이스 미리보기 / 예열 / 프린트 시간 / 일시정지 + 4대 독립 컨테이너 + 탭 구분
- 결과: ✅ Phase 2 5탭 UI 완성 (2/27 기준)
- 서버: 5090 운영(폐기 예정) + 8085 개발 → 5090 폐기 후 카카오 VM으로 이전 (2/26 결정)

### 2. 한솔코에버 협업 구조 변경

**소스코드 공유 결정 (2026.02.26)**
- 원래 2/24 미팅에서 "소스코드 공유 X, 가이드라인만"으로 결정 → **2/26 변경: 소스코드 공유**
- 이유: 한솔 작업 효율 + Phase 전환(인수인계 후 OpenMV 개발) 일정 단축
- AICA A100: 한솔 3월간 1대 필요 → 근형님 전달 완료

**협업 담당자 변경 흐름**
- ~~김기원 주임 (`justkiwon`) + 이나라 주임~~ — 김기원 PR #3 제출(3/24) 후 `hansol-dev` 브랜치 전환(3/25, `591b95a`)
- **2026-04-03 김기원 주임 퇴사** — 코드 docs 폴더 역할별 요약 보유. 직접 지원 불가, 구조/플로우 문의는 가능
- **2026-04-29 사고**: 공장 PC origin이 `justkiwon/3D_printer_automation` (퇴사자 fork) 가리켜 100커밋 차이 발생 → 원격 복구 진행
- **현재 협업 담당자**: 이예승 사원 (한솔코에버, GitHub: `eseung97@gmail.com`, 연락처: 010-4946-3610)

**한솔 머지 이력** (전체: `memory/project_hansol_merge_issues.md`)
| 회차 | 일자 | 커밋 | 내용 | 비고 |
|------|------|------|------|------|
| 1차 | 4/3 | `9c161dc` | 김기원 주임 코드 (sequence_service / AutomationPage / automation_db.py) | 인코딩 깨짐 복원 |
| 2차 | 4/16 | `e68c2b1` | 자동화 CMD 프린터 할당 콤보박스 + 공용 큐 버그 수정 | App.tsx mojibake 차단 |
| 3차 | 4/23 | `9f97f1e` | 경화기 2→1대 축소 (Cure 2 비활성화) | 인코딩 깨끗 / `runtime.py:121` 후속 패치 미커밋 |
| 4차 | 5/6 | `b9164d9` | 시뮬 토글 + 프린터 별명 매핑 | — |
| 5차 | 5/6 | `9fd365a` | `cell_state.simul_mode` 컬럼 자동 마이그레이션 (4차 누락분 보강) | 3개 서버 배포 완료 |

### 3. 빈피킹 (Phase 5) 방향 결정

**3D+RGB 카메라 조합 결정 (2026.04.03)**
- Blaze-112(ToF) 단독 vs ace2(RGB) 조합 → **조합** 결정
- STL 수집 결과 (4/6): 55개 다운 → 중복 제거 → bbox 분석 → **29종** 확정 (목록 자체는 미확정, 킵고잉)

**카메라 배치 — 4/10 1차 결정 → 4/23 한솔 회의 재합의**
- 4/10 대표님 피드백: "1대 고정(eye-to-hand) + 1대 로봇암(eye-in-hand)" + 시각화 요청 (실패 케이스 이미지 첨부)
- 4/23 한솔 3자 회의 (김주엽 파트장 + 이예승): **eye-in-hand에 Blaze + ace2 2대 동시 마운트**로 합의 (대표님과 일치)
- 5/6 회의에서 카메라 브라켓 확정: 코에버 설계 → 오리누 3D 출력 → 검증 후 철제 가공

**빈피킹 좌표 — 6DoF → 4DoF 단순화 (2026.05.06 한솔 회의)**
- 이전: 6DoF 오일러 ZYX 가정으로 다면 처리하려고 했음
- 변경: **X, Y, Z, Theta (4DoF)** + 다면은 자세 분리(A자세/B자세) + 리그립으로 해결
- 블로커: 한화 로보틱스 별도 라이브러리/패키지 = 한솔 이예승 ASAP 확인. 답 받기 전 좌표 출력 코드 확정 금지

**대표님 5/6 빈피킹 개인 지시 4가지** ⭐ — `memory/project_binpicking_ceo_directive_0506.md`
> 로봇 장착은 추후로 미루더라도 인식 자체를 먼저 확실히

1. **Basler 카메라 로컬 테스트 우선** — IPC-510/로봇 셋업 기다리지 말 것 → 5/8 진행 중 (어댑터 도착 대기)
2. **공장 실물 부품 다각도 촬영 + 학습** — CAD-only FPFH/ICP 한계, 실데이터 학습 필요. 부품 1종당 수백 장
3. **X, Y 각도(뒤집기) 데이터 고민** ⭐
   - 안정 자세 enumeration (CAD bbox + COM)
   - 자세별 그래스프 가능 여부 → grasp_database.yaml 자세별 확장
   - regrasp 시퀀스 정의
   - 학습 라벨링 형식 (부품 ID + 자세 클래스 + 6DoF pose)
   - **코드 짜기 전 명세 초안 → 대표님 align**
4. **예승님 연락** — (a) 빈피킹 좌표 명세 (좌표계/단위/회전/그리퍼/시퀀스) (b) 바텀비전 홀 검출 소스코드

**5/6 한솔 3자 회의 추가 안건** — 상세: `memory/project_meeting_0506_hansol.md`
- 다면 인식 정식 안건화 (리그립 스테이션 vs 시퀀스 분할 A/B자세)
- Formlabs API 무인 운전 불가 — 공식 확인. 출력 종료 후 수동 터치 체크리스트 필수
- 그리퍼 교체 요청 (한솔) — 잔여 레진 제거 어려움
- 3D 프린터 하단 파손 270만원 분담 협의 중
- 삼성전자 ~2억 규모 하반기 지원사업 참여 준비
- 카카오톡 단톡방 운영 (5/7 입장 완료)

### 4. HCR-10L 로봇 연동 (2026.04.14 교육 1회차)

- **한화 HCR 개발 특성**: 두산/현대와 달리 **펜던트(Rodi) 중심 개발**. 외부 PC는 Modbus 레지스터 간접 제어
- 비전PC가 Modbus 레지스터에 피킹 좌표 쓰기 → 펜던트 프로그램이 읽어서 모션 실행
- **사용자 사용 가능 레지스터: 130~255** (문서상 128~이나 실사용 130번부터)
- **좌표계**: Base(로봇 바닥 기준) vs TCP(그리퍼 끝단 기준)
- **TCP 좌표 Modbus 읽기**: Register 400~405 (1/10mm, 1/10deg, 16bit 정수)
- **TBD**: TCP 오프셋, 작업 영역, 오일러 컨벤션 (그리퍼 장착 + 빈 배치 후 실측)
- 자료: `PLC_Cobot_Modbus_Guide.pdf` (34p, 예제 3건)
- 4/15 Modbus 재설계: FLOAT32(40001~) → **INT16(130~140 비전PC→로봇 / 150~151 로봇→비전PC)** (`a13b5ce`)
- 상세: `memory/reference_hcr_user_education.md`

### 5. 산업용 PC (IPC-510) 카메라 구성 (2026.04.10 / 4/23 입고)

- **카메라 최대 6대 구성**: Bottom Vision 1대 + 빈피킹 2대(Blaze-112+ace2) + 3D프린터/경화기 모니터링 1~2대 + 양손 로봇(추후) 1대
- **스펙 우려**: GPU 5060 + RAM 8GB → 6대 동시 처리 버거울 수 있음
- **대안**: 젯슨 나노로 분산 가능성
- **현재 (5/8)**: 4/23 입고 완료, 셋업 미시작. HCR-10L 빈피킹 전용 (4/29 합의). HCR-12는 공장 PC 잔류
- 상세: `memory/project_robot_pc_assignment.md`

### 6. Phase 4 — OpenMV → MaixCAM 전환 (2026.04.14)

- 원래 OpenMV AE3로 세척기/경화기 완료 감지 (2026.02.06 확정)
- 4/14 대표님 지시로 MaixCAM 전환 — RISC-V + 1 TOPS NPU + 4MP, Cloud 없이 온디바이스 AI
- 보유 장비: MaixCAM 1대 + LicheeRV Nano 2대
- 우선순위: 빈피킹 우선, MaixCAM은 여유 시 PoC
- 역사: `memory/project_openmv_image_capture.md` (3/16 시도 → 4/14 전환)

---

## Phase별 개발 계획 (확정)

| Phase | 항목 | 우선순위 | 상태 (2026-05-08) |
|-------|------|----------|------|
| **Phase 1** | Web API 모니터링 | 🔴 URGENT | ✅ 완료 |
| **Phase 2** | Local API 원격 제어 + 프론트엔드 UI | 🔴 URGENT | ✅ 완료 (5탭 UI + JWT 인증 + 3개 서버 운영) |
| **Phase 3** | HCR 로봇 연동 | 🟡 HIGH | ✅ 한솔 머지 5차 완료. 다음주 예승님 방문 시 실 출력 + 로봇 E2E 테스트 |
| **Phase 4** | MaixCAM 장비 모니터링 | 🟡 HIGH | ⬜ 빈피킹 후순위. 보유 장비(MaixCAM 1대 + LicheeRV Nano 2대) PoC 대기 |
| **Phase 5** | 3D 빈피킹 비전 시스템 | 🔴 URGENT | 🔄 트랙 2 (YOLO+Roboflow) **5/22 빅데이**: Part6/7 50장 (누적 394장 7클래스) + Roboflow v2 5parts + **AICA 5모델 학습 14:45 시작** (YOLOv8n/8m/11s/11m/11l). **18:08 시점 결과**: YOLOv8n ✅ mAP50 **0.990** / YOLOv8m ✅ mAP50 0.975 / YOLOv11s 진행 중 / 종료 **자정 전 예상**. **좌표 6요소 출력 코드 완성** (`detect_and_output.py` 582 lines + AICA dry-run 검증, 대표님 5/18 피드백 종결). **PyTorch + Ultralytics + ONNX → IPC-510** 결정 명문화. **🔥 5/22 저녁 대표님 통화: 빈피킹 실 시연 = 가을(9~10월) 협력사 페이스. 그동안 우리 = 학습+카메라 완성도 (북극성 단계 A/B/C 집중). 전공정 그리퍼 교체는 한솔 조만간 회의** — `project_binpicking_timeline_realignment_0522.md` |

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

### 운영 인프라 (현재 = 2026-05-08)

| 서버 | URL | 인증 | 역할 | 상태 |
|------|-----|------|------|------|
| **공장 PC** | `https://factory.flickdone.com/` (Cloudflare Tunnel) | JWT | 운영 (실제 프린터 제어 + sequence_service + frontend) | ✅ NSSM OrinuMain 자동 시작 |
| **카카오 VM** | `http://61.109.239.142:8085/` | JWT | 운영 (모니터링 / SaaS) | ✅ systemd 자동 시작 |
| **6000 서버** | `http://106.244.6.242:8085/` | JWT | 개발 + 모니터링 병행 (개발 환경 본진) | ✅ systemd 자동 시작 |

**로그인 (모든 서버 공통)**: `admin` / `orinu2026!` (분기별 회전, 다음 2026-09-01)

**진화 흐름**:
- ~~5090 VM 운영~~ (2/12) → ~~카카오 VM 외부 접속 + Basic Auth~~ (4/16) → 카카오 + 공장 PC Cloudflare Tunnel + JWT (현재)
- ~~3/26 6000 서버 WireGuard Method B 설치~~ → ~~4/24 Cloudflare Tunnel 도입~~ → 현재 VPN은 백업 경로로만 유지
- 도메인 변경: ~~`lab.flickdone.com`~~ (3/18) → **`factory.flickdone.com`** (4/21 확정)

### 6000 서버 VPN 정보 (백업 경로, 현재 운영 의존도 낮음)

| 항목 | 값 |
|------|-----|
| VPN IP | 10.145.113.8/24 |
| 인터페이스 | wg0 |
| conf 파일 | `/etc/wireguard/wg0.conf` (키 정보, 커밋 금지) |
| Peer Endpoint | 106.244.6.242:56461 (= orinu.iptime.org) |
| AllowedIPs | 10.145.113.0/24 (192.168.100.0/24는 3/18 제거 — 로봇 충돌 해결) |
| 자동 시작 | `sudo systemctl enable --now wg-quick@wg0` |

> Method B 채택 (서버에 WG 직접 설치). Method A(공유기 라우팅)는 실패.

### 공장 PC 정보 (운영 본진)

| 항목 | 값 |
|------|-----|
| Windows 사용자 | `devfl` |
| 외부 접속 | `https://factory.flickdone.com/` (Cloudflare Tunnel `orinu-factory`) |
| VPN IP | 10.145.113.3 (백업) |
| AnyDesk | 원격 접속용 |
| 배포 경로 | `D:\3D_printer_automation_0305\3D_printer_automation` |
| Python | 3.14.3 / Node v24 |
| 배포 방법 | `deploy.bat` (관리자 cmd, 4/30 도입) |
| PreFormServer | `C:\PreFormServer\PreFormServer.exe -p 44388` (v3.55.0.606, 시작 프로그램 등록) |
| PreForm 앱 | `C:\Program Files\Formlabs\PreForm\3.57.0.622\PreForm.exe` (별도) |
| file_receiver | 포트 8089 → `C:\STL_Files` (시작 프로그램) |
| MariaDB | 11.3 (port 3306, 자동 시작) |
| NSSM 경로 | `C:\nssm\nssm-2.24\win64\nssm.exe` (PATH 미등록, 전체 경로 사용) |

> ⚠️ PreFormServer는 `-p 44388` 옵션 필수. 옵션 없이 실행하면 바로 종료됨.
> 자동 시작 체계 / 재부팅 후 체크 / NSSM 명령은 "마지막 업데이트 → 운영 인프라 핵심 정보" 섹션 참조.

---

## Phase 3: HCR 로봇 연동 ✅ 머지 5차 완료, 다음주 E2E 테스트 예정

- **프로토콜**: Modbus TCP (포트 502), pymodbus 3.x
- **로봇**:
  - HCR-12 (빌드플레이트 교체, 세척기 투입) — 공장 PC 연결 (현재)
  - HCR-10L (후가공, 제품 이송, 빈피킹) — IPC-510 이전 예정 (4/29 합의)
- **한솔코에버 협업**: `hansol-dev` 브랜치 → 머지 5차까지 완료 (`9c161dc` / `e68c2b1` / `9f97f1e` / `b9164d9` / `9fd365a`)
- **3/27 한솔 자체 최종 시연 완료**
- **다음주 예승님 방문**: 실 출력 + 로봇 E2E 테스트 (시뮬 토글로 SIMUL_MODE=false)
- **HCR-10L Modbus 레지스터** (4/15 INT16 재설계, `a13b5ce`):
  - 비전PC → 로봇: 130~140
  - 로봇 → 비전PC: 150~151
  - 로봇 내장: 400~405(TCP 좌표) / 600(상태) / 700~702(명령)
  - 인코딩: INT16 (1/10mm, 1/10deg, 16bit 정수)

---

## Phase 4: 장비 모니터링 (MaixCAM, ~~OpenMV~~ 대체) ⬜ 빈피킹 후순위

> 4/14 대표님 지시로 OpenMV → MaixCAM 전환. 이전 OpenMV 설계는 `memory/project_openmv_image_capture.md`에 역사로 보존.

### 용도
- **세척기/경화기 완료 감지** — Form Wash/Cure는 API 미지원이라 카메라 기반 감지 필요 (2026.02.06 확정)
- **부품 식별 + 불량 검출** — Phase 5 빈피킹 카메라(Basler)와 별도, 추후 검토

### 카메라 배치 (4대 예정)
| 위치 | 감지 내용 |
|------|----------|
| 세척기 1, 2번 전면 | 세척 중/완료 |
| 경화기 1, 2번 전면 | 경화 중/완료 |

### 기술 스택 (2026.04.14 이후)
- **Sipeed MaixCAM**: RISC-V SG2002 + 1 TOPS NPU + 4MP 터치 스크린
- **온디바이스 AI**: Cloud 없이 현장 독립 동작 (find_blobs() / YOLO)
- **통신**: WiFi 6 → MQTT (paho-mqtt 내장) + Modbus TCP/RTU 내장
- **학습**: MaixHub (무료 사진→학습→QR 배포)
- **보유 장비**: MaixCAM 1대 + LicheeRV Nano 2대 (4/6 수령)

> 통신 아키텍처는 OpenMV 시기와 동일: `카메라 → MQTT → Mosquitto → FastAPI → HCR 로봇(Modbus)`. MQTT E2E는 3/12 검증 완료.

상세: `memory/project_maixcam_monitoring.md`

---

## Phase 5: 3D 빈피킹 비전 시스템 🔄 인프라 완성 → 5/15 본 캡처 진입

> **문서**: ORINU-DEV-2026-002 (구본경 대표, 2026-03-18)
> **개발 환경**: Mac (Intel) + venv binpick (Python 3.12 + Open3D 0.19.0). 6000 서버는 Open3D 불가 (AVX2 미지원)
> **파이프라인**: L1 영상취득 → L2 전처리 → L3 DBSCAN분할 → L4 FPFH+RANSAC+ICP → L5 그래스프 → L6 Modbus
> **🎯 6/2 마감**: KAIST 3단계 부트캠프 회사 데이터 프로젝트 시작 — 그 전까지 학습 데이터셋 v1 (~1,200~2,400장) 확보

### 현재 진행 상태 (2026-05-20)

| 단계 | 상태 |
|------|------|
| W0~W2 학습 (논문 3편 + 튜토리얼 11개 + 실전 코드 3개, 6,149줄) | ✅ 완료 (3/23) |
| W3+ L1~L6 파이프라인 + 그래스프 DB 29종 + E2E 시나리오 | ✅ 완료 (4/6~10) |
| Modbus INT16 재설계 + Colored ICP + Basler 듀얼 캡처 모듈 | ✅ 완료 (4/15) |
| RealSense D435 라이브 + Full Pipeline PASS | ✅ 완료 (4/13~14) |
| 카메라 입고 (Blaze-112 + ace2) | ✅ 4/23 입고 / 5/8 사무실 운반 |
| **Mac Blaze 풀 작동** (pypylon 단독, IPC-510 대기 불필요) | ✅ 5/12 (commit 7e28df9 외 5건) |
| **사전 디벨롭 코드** (test_basler_live + pose_enumerator + auto_label) | ✅ 5/11 (~1,900줄) |
| **학습 데이터 라벨 신뢰도 인프라** (스키마 확장 + 대칭 그룹 + 검증 매뉴얼 + SOP 보강) | ✅ 5/13 (commit f9ec525 + dc8d0bf) |
| **5/15 본 캡처 인프라** (intrinsics sanity + capture wrapper + viewer 가드 + runbook + smoke test + .gitignore + 1pager v2.4) | ✅ 5/14 (commit 5개) |
| **5/15 공장 방문 + 한글 fix + Phase 2 E2E + ACE2 케이블 인수 + 부트캠프 주제 확정** | ✅ 5/15 |
| **5/18 트랙 1 P5 보류 → 트랙 2 (Roboflow + YOLOv8n) 전환 + AICA A100 부활 + 한솔 코드 인계** | ✅ 5/18 — YOLOv8n mAP50 0.988 (단일환경, 누수 의심) |
| **5/19 Roboflow 178장 + 협력사 통합 메일 + 5/20 작업 계획** | ✅ 5/19 |
| **5/20 ACE2 셋업 진단 — 어댑터/통신/코드 OK, C-mount 렌즈 미장착** (commit `09bdb33` live_viewer_ace2.py) | ✅ 5/20 — 한솔 보유 렌즈 인수 대기 |
| **5/20 한솔 좌표 명세 답변 수신 — YOLOv11s/m 권고 + 6요소 (x,y,z,edge,angle,label) 명세** | ✅ 5/20 — 우리 v2 코드 변경 결정 |
| **5/20 v2 5모델 비교 학습 인프라 완성** (yolov8n/m + yolo11s/m/l, commit `9b68c14`) + 공장 촬영 전환 가이드 (`docs/factory_capture_20260520.md` commit `ee332b9`) | ✅ 5/20 오후 |
| **5/20 저녁 공장 촬영 완료 — 핸드폰 200장+** (한화 협동로봇 + 흰 작업대 후보 1순위, 미확정) — **2개 조합 C(5,2)=10쌍 전수 + 3개 조합 C(5,3)=10조합 전수** + 5종 단일 + 빈/박스 | ✅ 5/20 저녁 — 5/21 Mac 업로드 예정 |
| 5/21 Mac 업로드 → Roboflow batch `20260520_factory_*` → annotation → manual split v2 → AICA 5모델 비교 학습 | ⏳ 5/21~ |
| 5종 풀 데이터셋 (~1,200~2,400장) | ⏳ 5/22~6/1 (사무실 가용 5일) |
| ACE2 RGB 인수 (한솔 C-mount 렌즈) + RGB+Depth 통합 출력 | ⏳ 5/22~ |
| eye-in-hand 캘리브레이션 (2세트) + Colored ICP 실연동 | ⏳ 6월 이후 (그리퍼 장착 후) |
| X/Y 각도 데이터 명세 (대표님 5/6 지시 3번) | ✅ **1pager + pose_validation_protocol + stable_poses.yaml 검증 매뉴얼 완성** (align 대기) |
| **한솔 좌표 명세 (대표님 5/18 피드백)** | ✅ 5/20 — 6요소 명세 수신 + v2 모델 변경 결정 |

### 핵심 성과 수치

**W3+ 실제 STL 29종 기반 E2E** (4/6~10, Mac):
| 지표 | 결과 | 목표 | 판정 |
|------|------|------|------|
| 인식률 (easy, 5종) | **100%** (5/5) | 85% | ✅ |
| 인식률 (crowded, 10종) | **90%** (9/10) | 80% | ✅ |
| 인식률 (hard, 5종) | **60%** (3/5) | 85% | ⚠️ FPFH 한계 → Colored ICP 도입 |
| RMSE | **1.0~1.5mm** | 3mm | ✅ |
| 매칭 시간 (OBB SizeFilter) | **0.4~0.6초** | 2.0초 | ✅ 3~5배 여유 |
| L1~L6 파이프라인 | **전체 구현 완료** | — | ✅ |
| L5 그래스프 DB | **29종 완성** | 29종 | ✅ |
| 4/22 데모 리허설 synthetic | **9.7s → 1.5s** (8배 단축) | — | ✅ |

### 레진별 파라미터 (참고)

| 레진 | voxel | Robust kernel | 비고 |
|------|-------|--------------|------|
| Grey/White | 2mm | Tukey 1mm | 표준 |
| Clear | 3~4mm | SOR + 멀티스케일 | 반투명 → ToF 노이즈 큼 |
| Flexible | 2mm | Huber 1.5mm | 변형 허용 |

### 코드 위치 (구현 완료)

`bin_picking/` 하위:
- `tutorials/01~11` (4,247줄, ✅ 전체 PASS)
- `src/recognition/` — cad_library / size_filter / pose_estimator
- `src/preprocessing/cloud_filter.py` — L2 전처리 (레진별 프리셋)
- `src/segmentation/dbscan_segmenter.py` — L3
- `src/grasping/` — grasp_planner + `grasp_database.yaml` (29종)
- `src/communication/modbus_server.py` — L6 (pymodbus 3.x, INT16)
- `src/acquisition/` — depth_to_pointcloud / realsense_capture / **basler_capture** / hand_eye_calibration
- `src/main_pipeline.py` — L1~L6 통합
- `tests/test_e2e_redwood.py` + `tests/test_e2e_cad_matching.py`

상세 파일 목록 / 줄 수 / 역할: `memory/project_binpicking.md` + `memory/project_binpicking_e2e_history.md`

### 남은 개발 작업

| 작업 | 블로커 | 예상 시점 |
|------|--------|----------|
| Mac 라이브 검증 (Blaze 부팅 OK / pylon 설치 / depth 스트림) | 어댑터 도착 (5/9 토요일) | 5/10~5/12 |
| 코드 수정 (BLAZE_112 fx/fy 460→416/188, ACE2 모델명 a2A2448) | 라이브 검증 | 5/10~ |
| 실물 SLA 부품 ACCEPT 검증 | 라이브 + 부품 | 5월 중 |
| X/Y 각도 데이터 명세 초안 ⭐ | 없음 (지금 가능) | 다음주 align 전 |
| 실물 부품 다각도 촬영 데이터셋 | 라이브 + 명세 align | 5월 중~후반 |
| eye-in-hand 캘리브레이션 (2세트) | 카메라 + 로봇 | 카메라 입고 후 |
| Colored ICP 실연동 | RGB 데이터 | 라이브 + ace2 |
| multi-view 재촬영 파이프라인 | 카메라 + 로봇 | 6~7월 |

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
- ✅ 머지 1차 (04-03, `9c161dc`): 김기원 주임 코드 통합 (sequence_service / AutomationPage / automation_db.py)
- ✅ 머지 2차 (04-16, `e68c2b1`): 이예승 사원 — 자동화 CMD 프린터 할당
- ✅ 머지 3차 (04-23, `9f97f1e`): 이예승 사원 — 경화기 2→1대 축소 (Cure 2 비활성화)
- ✅ 머지 4차 (05-06, `b9164d9`): 이예승 사원 — 시뮬 토글 + 프린터 별명 매핑
- ✅ 머지 5차 (05-06, `9fd365a`): 이예승 사원 — `cell_state.simul_mode` 컬럼 자동 마이그레이션 (4차 누락분)
- ⏳ 다음주 예승님 방문: 실 출력 + 로봇 E2E 테스트 (시뮬 토글 OFF)

상세: `memory/project_hansol_merge_issues.md`, `memory/project_meeting_0423_hansol.md`, `memory/project_meeting_0506_hansol.md`

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

> 일자별 작업 이력은 **`CLAUDE.local.md`** 참조. 이 섹션은 **프로젝트 마일스톤 + 핵심 의사결정 + 현재 진행**만 보관.

### 마지막 업데이트 일자: 2026-05-20 (사무실 — ACE2 셋업 진단 + 한솔 좌표 명세 답변 수신 + v2 YOLOv11 결정)

### 마일스톤 (시간 순)

| 시기 | 마일스톤 | 결과 / 메모리 참조 |
|------|---------|-------------------|
| 2026-01 | Phase 1 Web API 모니터링 착수 | ✅ 완료 |
| 2026-02 | Phase 2 Local API + 프론트 UI / 5090 VM 운영 | ✅ 완료 (5090은 폐기, 카카오로 전환) |
| 2026-02-12 | 대표님 데모 성공 → PreForm 동등 구현 지시 | ✅ 5탭 UI + 알림벨 완료 |
| 2026-02-26 | 소스코드 공유 결정 + Phase 전환 | 🔄 한솔 협업 시작 |
| 2026-03 (W11~W13) | Phase 4 (OpenMV→MaixCAM) + 한솔 PR + WireGuard | 🔄 MaixCAM 후순위 |
| 2026-03-27 | 한솔코에버 최종 시연 | ✅ 한솔 자체 진행 |
| 2026-04-03 | 한솔 머지 1차 (`9c161dc`) — 김기원 코드 통합 | ✅ — `memory/project_hansol_merge_issues.md` |
| 2026-04-06~10 | 빈피킹 W3+ 파이프라인 완성 (L1~L6 + 그래스프 DB 29종) | ✅ — `memory/project_binpicking.md` + `memory/project_binpicking_e2e_history.md` |
| 2026-04-13~14 | RealSense D435 라이브 연동 + Full Pipeline PASS | ✅ — `memory/project_realsense_d435.md` |
| 2026-04-14 | HCR-10L 로봇 교육 1회차 (펜던트 + Modbus TCP) | ✅ — `memory/reference_hcr_user_education.md` |
| 2026-04-15 | Modbus INT16 재설계 + Colored ICP + Basler 듀얼 캡처 모듈 | ✅ — 카메라 입고 전 SW 마무리 |
| 2026-04-16 | 한솔 머지 2차 (`e68c2b1`) + 카카오 VM 외부 접속 + Basic Auth | ✅ — `memory/project_kakao_vm_migration.md` |
| 2026-04-21 | 도메인 확정 `factory.flickdone.com` | ✅ |
| 2026-04-22 | 데모 리허설 피드백 반영 (synthetic 9.7s→1.5s, 크래시 방어) | ✅ 커밋 6건 |
| 2026-04-23 | Basler 입고 + IPC-510 입고 + 한솔 3자 회의 + 머지 3차 (`9f97f1e`) | ✅ — `memory/project_meeting_0423_hansol.md` |
| 2026-04-24 | Cloudflare Tunnel 구축 + NSSM OrinuMain 등록 + DB(MariaDB) 재조사 + Formlabs Secret Rotate | ✅ — `memory/project_cloudflare_tunnel.md` |
| 2026-04-29 | 🔥 공장 PC 원격 복구 (origin URL 정정 + aiomqtt 누락) | ✅ — `memory/project_factory_pc_remote_recovery_0429.md` |
| 2026-04-29 | KAIST 부트캠프 합격 (4/30~7/9) | ✅ — `memory/project_kaist_bootcamp.md` |
| 2026-04-30 | `deploy.bat` 도입 + smoke test + 재부팅 자동복구 검증 | ✅ — `memory/project_deploy_bat.md` |
| 2026-05-06 | JWT 로그인 도입 + 한솔 머지 4·5차 + 공장 PC 응답 영구 해결 (12시간, 11커밋) | ✅ — `memory/project_web_auth_security.md` |
| 2026-05-06 | 한솔 3자 회의 (4DoF / 다면 인식 / 한화 패키지) + 대표님 빈피킹 개인 지시 4가지 | ✅ — `memory/project_meeting_0506_hansol.md` + `memory/project_binpicking_ceo_directive_0506.md` |
| 2026-05-08 | Basler 박스 개봉 + Mac 사무실 셋업 + 어댑터 발주 결정 (ipTIME U1G-C) | ✅ 5/11 — 어댑터 화요일 도착 예정이나 수요일 재택 → 금요일 수령으로 수렴 |
| 2026-05-11 | 바텀비전 인수 완료 (Flicdern_v3) + 인터페이스 명세 추출 + 5종 깊게 모드 결정 + 어댑터 도착 전 사전 디벨롭 계획 | ✅ 완료 — `memory/project_bottom_vision_handover_done.md`, `project_binpicking_5parts_strategy.md`, `project_week_plan_0511.md` |
| 2026-05-11 | **사전 디벨롭 전략 A (코드 몰빵) 완료** — 코드 신규 3 (test_basler_live 678 + pose_enumerator 412 + auto_label 815) + 코드 수정 5 (ACE2 a2A2448-23gcBAS / BLAZE fx 417 fy 188) + 문서 3 (1pager v2 + SOP + 바텀비전 인터페이스) + 설정 2 (5종/29종 yaml) + 메모리 4. 5종 실측 발견 (② 단순/① 대칭/④ 단위 의심) | ✅ 완료 — `memory/project_binpicking_predev_codes_0511.md` |
| 2026-05-11 (오후) | **부품 5종 사진 + 실측 + 1pager v2.1** — 핸드폰 사진 15장 + **P3 캘리퍼스 56mm = bracket_sen_1 확정** (단위 의심 해소). 레진 Grey 통일 + 무광 표면 확인. P5 main_body 거의 확정 | ✅ 완료 |
| 2026-05-11 (오후) | **🎉 어댑터 ipTIME U1G-C 조기 도착** (예상 5/15 → 5/11, 4일 빠름). 박스 사양 OK (USB 3.0 + 기가비트 + macOS 10.6+). 즉시 Step 1~3 검증 PASS (USB 5Gb/s + en8 1000baseT + IP 고정) | ✅ |
| 2026-05-12 | **🎉 Mac Blaze 풀 작동 검증 완료** — pylon Suite 26.04 설치 → IP Configurator 발견 → Wi-Fi 충돌 발견 → 192.168.20/24 영구 분리 → pylon Viewer 미지원 발견 → **pypylon 단독 풀 작동 워크어라운드** (Range component + Mono16). commit 7e28df9 (basler_capture.py +73/-20) push. 핵심 발견: ① Blaze 실 해상도 848×480 (매뉴얼 640 오류) ② macOS Blaze Supplementary 불필요 (pypylon으로 OK) ③ EnumerateDevices 미동작 → BASLER_BLAZE_IP fallback ④ Wi-Fi 충돌 192.168.20/24 분리. test_basler_live.py --live --save --pipeline 풀 PASS. **IPC-510 대기 3주 불필요** | ✅ — `memory/project_basler_office_setup_0508.md` § 5/12 |
| 2026-05-12 | **문서 동기화 commit 3fa9e10** (origin + personal dual push, +98/-5) — 1pager v2.3 (BLAZE 848 + 리스크 #15/#16 + 5/12 의사결정) + SOP (macOS 운영 노트 + BASLER_BLAZE_IP + 트러블슈팅 4개) + Push 정책 단순화 (모든 commit dual = 사용자 기존 패턴) | ✅ — Mac/6000 양쪽 최신 동기화 |
| 2026-05-12 (저녁) | **🎉 라이브 뷰어 commit 0a34b72** (Mac, live_viewer_basler.py +179줄) — pylon Viewer macOS Blaze 미지원 회피용 cv2 + pypylon 단독 인터랙티브 뷰어. 키: ESC/q/s/c/r/+/-. FPS 20.1, depth median 835mm, JET 컬러맵 정상. 사용자 시각 확인 "오 잘되네". **5/12 인프라 단계 완전 종료** — 빈피킹 워크플로우 100% Mac 단독 가능 확정. 이제부터 사용자 부품 배치 + 본 캡처 페이스 | ✅ |
| 2026-05-12 (퇴근 전) | **일정 결정 — 카메라 사무실 보관, 5/15 금 본 작업 시작** — 2.5kg 이동 부담 + 카메라 충격 위험 회피. 수 5/13 재택은 가벼운 작업만 (ACE2 단톡, 예승님 카톡, 1pager align 메시지 초안). 5/15 금 사무실 종일 P5 main_body 첫 시범 + auto_label 실 데이터 검증 | ✅ |
| 2026-05-13 (수, 재택) | **학습 데이터 라벨 신뢰도 인프라** — 외부 커뮤니케이션 3건 발송 보류 (사용자 결정). commit 2개 dual push: `f9ec525` (pose_enumerator v1.1 / stable_poses 5종+29종 재생성 / auto_label 대칭 그룹 + canonicalize_pose_id + simulate PASS) + `dc8d0bf` (pose_validation_protocol.md 신규 = 5/15 첫 30분 부품 던지기 매뉴얼 / SOP v1→v1.1 = § 1.3 조명 valid % + § 2.1 L4 강제 + § 4.1 흔들림 + § 5.1 REVIEW 큐 처리). **6/2 KAIST 3단계 부트캠프 회사 데이터 프로젝트 마감 도입** (W22, 사무실 가용 4~5일 = 5/15·5/18·5/22·5/25·5/29·6/1) — 5종 ~1,200~2,400장 목표, 주제 결정 W21 (5/25~) | ✅ — `docs/binpicking_pose_validation_protocol.md` + SOP v1.1 + `project_week_plan_0511.md` 재조정 |
| 2026-05-14 (목, 재택) | **5/15 본 캡처 인프라 완성** — 5 commits 단위로 분리 진행. ① `chore(gitignore)`: captures + dataset_v* + pose_validation_photos* ignore (5/15 commit 사고 방지) ② `feat(basler)`: INTRINSICS_VERSION 상수 + BaslerIntrinsics.version (캘리브 추적) ③ `feat(auto_label)`: intrinsics_version + has_rgb 라벨 추적 (depth-only vs RGB-D 구분) ④ `feat(binpicking)`: check_intrinsics_planar (A4 평면 RMS sanity) + capture_session (yaw sweep wrapper, 진행 카운터 + 중단/재개) + live_viewer 가드 색상 (valid % 70/50% 임계) ⑤ `docs(binpicking)`: runbook 단일 페이지 + friday_smoke_test.sh (5분 sanity) + 1pager v2.4 (§ 0 6/2 마감 + § 5.2 차원 축소 1,200장 옵션 + § 8 #17 silent bias / #18 domain gap + § 14 체크리스트). 시나리오 A 채택 (5/15 depth-only, ACE2는 5/18~ 추가) | ✅ commit 5개 + dual push — 인프라 100% |
| 2026-05-15 (금, 공장) | **공장 방문 — 예승님 만남 + 한솔 브라켓 출력 + 한글 파일명 fix 종료 + Phase 2 E2E 검증** ① ACE2 전원 케이블 한솔 보유분 인수 ② 추가 어댑터 1개 필요 발견 → ipTIME U1G-C 즉시 발주 ③ **예승님 YOLO + Roboflow 제안 채택** — 트랙 1(6DoF) 유지하면서 트랙 2(YOLO) 병행 ④ 🔴→✅ **한글 파일명 fix commit `06e68b4`** — X-Filename ASCII 위반 → RFC 5987 percent-encoding. 3개 서버 동기화 + 공장 직접 검증 ⑤ ✅ **Phase 2 E2E 풀 패스 검증** — 우리 앱으로 STL → 슬라이스 → 프린터 전송 → 실 부품 형성 (`4.Senser_2_dog.stl` 사진 검증) ⑥ 🔥 **출력 실패 진짜 원인 발견** = 레진 탱크 바닥 잔여물 (FEP 굳음, "옛날부터 있던" 물리 운영 이슈, 우리 앱 무관) ⑦ **운영 의문 정정**: Form 4 Local API는 confirm 단계 원래 없음 (5/6 한솔 회의록 "수동 터치"는 출력 종료 후 얘기) ⑧ **시간 차이 미스터리** — PreForm 1h44m vs 우리 앱 4h26m (.form 올려도 4h12m, 우리 앱이 재슬라이스). layer_thickness 기본값 불일치 가설 + .form 워크플로우 패치 working tree에 있음 (미커밋) ⑨ **5개 부품 사전 촬영** — 23+장 × 4종 + 5장 (P5 main_body 가설 폐기, 5/11 P1~P5 라벨은 추정값) ⑩ **부트캠프 주제 = 빈피킹 + 비전 AI** 사용자 명시 ⑪ 일정 정정: 화/목 KAIST → 월/수/금 사무실, 가용 7일 (5/18·20·22·25·27·29·6/1) → 6/1 마감, 6/2 부트캠프 시작 | 🆕 `project_binpicking_yolo_track` + `project_ace2_adapter_reorder_0515` + `project_factory_print_korean_filename_bug_0515` + `project_phase2_e2e_complete_0515` + `project_shrewdstork_cartridge_slow_0515` + `project_factory_photos_0515` + `feedback_excessive_questions` |
| **2026-05-18 (월, 사무실)** | **트랙 2 Roboflow v1 + YOLO 학습 완성 + 한솔 빈피킹 코드 인계 + AICA A100 부활** ① Mac Claude Code 릴레이 12 commit pull + smoke test 13/14 PASS ② **Intrinsics 확정**: 848×480 / fx 553 / cx 424 / `estimated_v2_20260513` ③ **A4 sanity 2회 FAIL** — Blaze FOV 75° + 30cm fundamental 불가 (시야 가로 46cm vs A4 21cm = 45% 최대) ④ **P5 파일럿 환경 제약으로 보류** — P5 < 5cm, Blaze 단독 어려움, ACE2 RGB 필요. 사무실 valid % 4~8% ⑤ **트랙 2 우선 전환** ⑥ **Mac Claude Bash false negative 발견** — venv activate 후 PATH 캐싱 / 우회법 3가지 ⑦ **Roboflow 셋업**: Public plan + Project `parts-5class-v1` + 보안 익명화 (`part_1~5`) ⑧ **116장 annotation 완주** (P1=25/P2=26/P3=23/P4=24/P5=18) ⑨ **Version v1**: 278장 (Train 243 + Valid 23 + Test 12), Aug 3x ⑩ **AICA A100 부활** (근형님 컨테이너 재생성) — 6000→AICA ssh key 등록, 환경 구축 (PyTorch 2.1+CUDA 12.8, ultralytics, opencv-headless, numpy<2), 함정 해결 (`/dev/shm 64MB → workers=0 cache=ram`) ⑪ **YOLOv8n 학습 완료** — 150 epochs / **10분 22초** / **mAP50 0.988 / mAP50-95 0.836**. 클래스별 mAP50 ≥ 0.962. 약점: part_2 Recall 0.656 ⑫ 결과 회수 `bin_picking/yolo_track/runs/v1-yolov8n-0719/` (11MB) ⑬ **한솔 이예승 빈피킹 코드 인계** — `bin_picking.zip` 4파일 783줄 (`realsense_pure_python` + `handeye_calibration` + `T_gripper2camera.npy` z=-212mm 검증 PASS + `hanwha_bin_picking` 11단계 시퀀스). 보관 `~/hansol_handover/` (git 추적 X), 통합 전략 C 채택 → `bin_picking/yolo_track/`에 어댑테이션, 예승님 회신 완료 ⑭ 코드 git commit: CLAUDE.md만 (3f3220b) | 🆕 `project_p5_pilot_blocked_0518` + `feedback_mac_claude_bash_caching` + `project_roboflow_v1_setup_0518` + `project_hansol_bin_picking_handover_0518` + `reference_aica_a100` |
| **2026-05-18 (월, 저녁 후반)** | **대표님 보고 발송 + 좌표 명세 피드백 + 5/19 작성 자산 준비** ① **보고 자료 정리** — `docs/ceo_report_20260518_source_material.md` (Basler YOLO 공식 입장 조사 + YOLOv8 선택 5가지 근거) ② **웹 Claude 보고서 작성** — `ORINU-BINPICKING-REPORT-2026-0518` 16페이지 PDF (아키텍처 다이어그램 + 완료/미완료 + YOLO 근거 + 5/20 다음 단계) ③ **대표님 보고 발송 완료** ④ 🔥 **대표님 피드백**: "한솔에서 달라고 했던 좌표들 x/y/z 좌표인지 뭔지 그거 먼저 물어보고 파악하고 인지하고 일을 해" — 5/6 4대 지시 중 좌표 명세 요청 미해결 지적 ⑤ **5/19 액션**: 예승님께 정식 명세 5가지 질문 메일 (좌표계 기준점 / 회전 표현 / 단위 / 그리퍼 기준점 / 시퀀스 책임) ⑥ **5/19 작성 자산 준비** — `bin_picking/yolo_track/camera/basler_wrapper.py` (~220줄) + `bin_picking/yolo_track/pipeline/bin_picking_main.py` (~360줄) Phase 2 임계 2파일 (5/22 통합 시연 코드 baseline) ⑦ **1pager v2.4 → v2.5** (§ 8 리스크 #19~23 추가: A4 fundamental 불가 / valid % / 데이터 누수 / Public 노출 / best vs last + § 10 의사결정 5/18 8행 추가) ⑧ **5/20 사무실 체크리스트** 작성 (`docs/office_checklist_20260520.md`) ⑨ **추가 사진 촬영** (회사 환경, A4 흰 배경): Part_1~3까지 진행, Part_4/5/멀티 객체는 5/20 이월 | 🆕 `project_ceo_feedback_0518` |
| **2026-05-19 (화, KAIST 교육 짬)** | **Roboflow 컨벤션 확정 + 5/18 분 62장 annotation + 협력사 통합 메일 발송** ① **Roboflow 명명 컨벤션 확정**: Class/Tag = `PartN` (PascalCase 통일), Batch = `{YYYYMMDD}_partN` (일자=batch 작업/통합한 날) ② **5/15 batch rename**: `Part_N_initial` → `20260519_partN` (5개) ③ **5/18 분 62장 신규 업로드 + annotation 완료** (Part1=17 / Part2=15 / Part3=18 / Part5=12) → 누적 **178장** ④ **5/20 작업 옵션 B 채택**: Part4 + 멀티 객체까지 통합 후 v2 학습 (manual split 데이터 누수 검증 활용) ⑤ **멀티 객체 촬영 전략**: 9배치 × 3각도 = 27장 (효율 leverage: 부품 고정 + 카메라 각도 / 같은 배치 부품 회전) ⑥ **Occlusion 박스 규칙 확정**: 0~70% 추정 박스 / 70~90% 보이는 영역 / 90%+ 건너뜀 ⑦ ✅ **협력사 통합 메일 발송 완료** — 대표님 5/18 피드백 이행. 톤: 짧게 핵심만 + 솔직 표현. 좌표는 5가지 정식 질문 직접 안 던지고 "어떻게 진행하는 게 좋을지" 의견 요청. 회신 대기 → 코드 잠정 처리 ⑧ 미커밋/미푸시 없음 (외부 SaaS + 메일 작업, 로컬 코드 변경 X) | 🆕 `project_binpicking_0520_office_plan` + 갱신 `project_roboflow_v1_setup_0518` + `project_ceo_feedback_0518` |
| **2026-05-20 (수, 사무실, 오전~오후)** | **ACE2 셋업 진단 + 한솔 좌표 명세 답변 수신** ① 🆕 **ACE2 단독 셋업 시도** — 2차 ipTIME U1G-C 어댑터 + Mac en8 192.168.20.1/24 + ACE2 static 192.168.20.20/24 + ping 0.7ms ② **pylon IP Configurator 발견**: a2A2448-23gcBAS S/N 41881328 + 첫 프레임 캡처 성공 (BayerRG8 2448×2048 uint8) ③ **`live_viewer_ace2.py` 신규 작성 + commit `09bdb33`** (232줄, BayerRG8 디모자이크 + GigE 패킷 튜닝 + Focus score 오버레이) origin + personal dual push ④ 🔥 **ACE2 광학 진단 — 렌즈 미장착 확정** — DARK mean 39.4 (Exp 100000us) / BRIGHT mean 212.8 (Exp 26us) / OBJECT 형상 없음. 사진 분석: C-mount 마운트만 있고 빨간 센서 노출. **5/8 메모리 "ACE2 렌즈 미장착, 한솔 보유" 그대로 유지** — 5/15 인수 시 명시적 기록 없음 ⑤ 🆕 **ACE2 ↔ Blaze L자 듀얼 마운트 확인** (5/6 회의 합의 "eye-in-hand 듀얼" 실물 구조) ⑥ 🆕 **GigE 튜닝 발견**: ipTIME U1G-C MTU 9000 거부 (Mac sudo invalid) → 어댑터 max packet 8192 보고하나 Mac MTU 1500 한계. ACE2 5MP 안정 캡처는 해상도 절반(1224×1024) + GevSCPD 2000 권장 ⑦ ⭐ **한솔 좌표 명세 답변 수신** (5/19 통합 메일 회신) — 예승님 답변 3가지: (a) 단일환경 누수 검증은 우리 책임 (b) **YOLOv8 → YOLOv11 + n → m/l 권고** (AICA A100 충분) (c) **좌표 6요소 필요: x,y(2D픽셀) + z(Blaze depth) + edge(외각선) + angle(회전) + label**. "Pointcloud 데이터 받아서 로봇 움직임" ⑧ **5/20 v2 학습 모델 변경 결정**: `yolov8n.pt` → `yolov11s.pt` 또는 `yolov11m.pt` (detection 우선, segmentation은 v3 별도) ⑨ **대표님 5/18 피드백 이행 완료** — 좌표 명세 명확화 + 우리 코드 변경 결정 ⑩ **미확정 5항목** (좌표계 기준점/단위/PCD vs dict/각도 정의/edge 형식) — 5/22~5/29 또는 ACE2 렌즈 인수 시 추가 확인 ⑪ 사용자 결정 대기: 한솔 단톡 ACE2 C-mount 렌즈 보유 확인 메시지 시점 자율 | 🆕 `project_ace2_lensless_diagnosis_0520` + `project_hansol_coord_spec_0520` + 갱신 `project_ceo_feedback_0518` + `project_binpicking_yolo_track` + `project_binpicking_0520_office_plan` + `MEMORY.md` |

### 핵심 의사결정 (이유 + 결과 보존)

#### 운영 서버 — 5090 폐기 → 카카오 VM 이전 (2026-02-26)
- **배경**: 5090 VM 한계 + VPN-로봇 네트워크 충돌
- **결정**: 운영을 카카오 클라우드로 이전 (대표님 지시)
- **결과**: 4/16 카카오 VM 외부 접속 정상, Basic Auth 적용. 4/24 Cloudflare Tunnel 도입으로 공장 PC가 외부 접속 단일 진입점이 됨

#### 프린터 제어 경로 — VPN(Method B) → Cloudflare Tunnel
- **배경**: WireGuard VPN으로 6000↔공장 연결 → 도메인 확정 + 상용화 대비 + VPN 의존도 감소 필요
- **결정**: 4/21 도메인 `factory.flickdone.com` 확정 → 4/24 Cloudflare Tunnel `orinu-factory` 구축 → 공장 PC NSSM OrinuMain 자동 시작 등록
- **결과**: 외부 HTTPS 200 운영, 재부팅/정전 자동 복구. VPN은 개발/백업용으로 유지 (6000 서버 `10.145.113.8`)
- 상세: `memory/project_cloudflare_tunnel.md`, `memory/reference_factory_pc_deployment_guide.md`

#### 인증 방식 — Basic Auth → JWT 로그인 (2026-05-06)
- **배경**: 4/24 Cloudflare Tunnel 활성화 후 공장 PC `.env`에 BASIC_AUTH_* 변수 누락 사고 (외부 인증 없는 상태로 운영)
- **결정**: JWT 토큰 + React 로그인 페이지 + 7일 sliding refresh + 30일 절대 최대
- **결과**: 3개 서버(6000/카카오/공장) 동기화. `admin` / `orinu2026!`. 분기별 회전 (다음 2026-09-01)
- 상세: `memory/project_web_auth_security.md`

#### 공장 PC 응답 일관성 — `.env` 가짜 알림 자격증명 영구 fix (2026-05-06)
- **증상**: `factory.flickdone.com` 1회차 빠르고 이후 timeout, Cloudflare 524
- **진짜 원인**: `.env`의 가짜 알림 자격증명(SMTP/Slack/FCM 6개)이 매 폴링마다 5초 timeout 누적 → web-api 응답 막힘
- **결정**: `.env` 6개 비우기 → 코드가 `not_configured`로 즉시 skip, `.env.example`도 빈 값 + 사고 이력 주석
- **결과**: 외부 10번 연속 401+0.2초

#### 공장 PC 배포 — 수동 9단계 → `deploy.bat` 1줄 (2026-04-30)
- **배경**: 4/29 원격 복구 시 수동 9단계 절차 + 인코딩 깨진 머지가 라이브 직행할 위험
- **결정**: `deploy.bat` 5단계(git pull / pip / npm build / nssm restart / health check) 각 errorlevel abort. GitHub Actions runner는 라이브 직행 위험으로 기각
- **결과**: 4/30 smoke test 완료 (vite build + NSSM 재시작 + HTTP 200). 5/6에 좀비 정리 로직 추가
- 상세: `memory/project_deploy_bat.md`

#### DB 아키텍처 — MariaDB 11.3 (공장 PC) + SQLite (web-api)
- **배경**: 4/24 오전 "MySQL 미설치" 잘못 판단 → 오후 재조사 시 MariaDB 11.3이 자동시작 중이고 `automation` DB가 sequence_service 로그 적재 중
- **현재**: 공장 PC = MariaDB 11.3(port 3306, 자동화 로그) + SQLite(web-api 프리셋/알림). 6000/카카오 = SQLite 모니터링 전용
- **올바른 확인 방법**: `netstat :3306` → `tasklist` PID → `mysqld.exe` 확인
- **옵션 2c (원격 DB 접근)**: Cloudflare Tunnel TCP ingress + 카카오 VM cloudflared 프록시 + Access Service Token. 5월 후반 구현 예정. 실시간 제어는 절대 터널 경유 금지
- 상세: `memory/project_sequence_service_deployment.md`

#### Phase 4 — OpenMV → MaixCAM 전환 (2026-04-14)
- **배경**: OpenMV AE3로 세척기/경화기 완료 감지 검토 중 → MaixCAM이 성능 우위 (RISC-V + 1 TOPS NPU, 4MP)
- **결정**: 대표님 지시로 OpenMV 제외, MaixCAM으로 전환. Cloud 없이 온디바이스 AI
- **현재**: 빈피킹(Phase 5) 우선, MaixCAM은 여유 시 PoC. 보유 장비 = MaixCAM 1대 + LicheeRV Nano 2대
- 상세: `memory/project_maixcam_monitoring.md`, `memory/project_openmv_image_capture.md` (역사)

#### 빈피킹 카메라 배치 — eye-in-hand 2대 동시 마운트 (2026-04-23 한솔 회의)
- **배경**: 4/10 대표님 피드백 = "1대 고정 + 1대 로봇암(eye-in-hand)" 검토
- **결정**: 4/23 한솔 회의에서 **eye-in-hand + Blaze-112(ToF) + ace2(RGB) 2대 동시 마운트** 합의 (한솔 김주엽 파트장 + 대표님 일치)
- **브라켓**: 코에버 설계 → 오리누 3D 출력 → 검증 후 철제 가공 (5/6 회의 재확인)

#### 빈피킹 좌표 — 6DoF Euler ZYX → 4DoF X,Y,Z,Theta (2026-05-06 한솔 회의)
- **배경**: 빈 안 부품의 다면 처리를 좌표 차원으로 풀려고 하니 복잡
- **결정**: 좌표는 4DoF(X,Y,Z,Theta)로 단순화. 다면 처리는 **자세 분리(A자세/B자세) + 리그립**으로 해결
- **블로커**: 한화 로보틱스 별도 라이브러리/패키지 = 한솔 이예승 ASAP 확인 (답 받기 전 좌표 출력 코드 확정 금지)

#### 한솔 협업 담당자 변경
- **2/24~3/24**: 김기원 주임(`justkiwon`) — PR #3 제출 후 `hansol-dev` 브랜치 전환
- **4/3 퇴사 확인**: 김기원 주임 한솔코에버 퇴사. 직접 지원 불가, 구조/플로우 문의는 가능. **공장 PC origin이 퇴사자 fork 가리켜 4/29 원격 복구 사고로 이어짐**
- **현재**: 이예승 사원 (한솔코에버, GitHub: `eseung97@gmail.com`) — 4/16 머지 2차, 4/23 머지 3차, 5/6 머지 4·5차

---

### 5/8 진행 상세 (현재 진행 중인 작업)

#### 1. Basler 박스 개봉 + 부품 식별 (오전, 공장)

- **카메라 본체 식별 + S/N**:
  - Blaze-112 (ToF, depth): S/N 40737830, MAC 00:30:53:37:BB:6E, 2025-11 독일 제조
  - ace2 (RGB): **a2A2448-23gcBAS** (우리 코드 가정 a2A2590-22gcPRO와 다름!), S/N 41881328, mounting bracket 결합
- **매뉴얼 7장 핵심**:
  - Blaze-112 24VDC 고정 (PoE 아님, 21V 미만 손상 위험)
  - FOV 75°×104° → 코드 fx=fy=460 가정 잘못, 정정 fx≈416/fy≈188
  - mounting bracket 통합 174 × 80.6 × 73mm (코에버 브래킷 설계 치수)
- **케이블 정답 4종** (라벨 인쇄 모델명 우선 신뢰): DS240020(24V/2A) + M12-8P-PWR-Supply-10M + GigE-Cable-10M-R + M12-8P-FJ45-10M-R(예비)
- **사용 분류**: 12V 세트(LOADUS EQ-4212Fctc + M8/6P-PWR)는 5/8 오전엔 NG로 분류됐으나 **저녁에 ace2 전용 전원으로 정정**
- 상세: `memory/project_basler_unboxing_0508.md`, `memory/reference_basler_blaze_112.md`

#### 2. 사무실 Mac 셋업 + AMCA017 어댑터 사양 미달 발견 (오후)

- **카메라 부팅 성공 ✅**: STATUS LED 녹색 깜빡 + ETHERNET LED 빨강 (매뉴얼 정상 패턴)
- **ace2 추가 발견**: 본체에 RJ45 직결 박혀있음 → M12 변환 불필요 (일반 LAN 케이블 OK)
- **AMCA017 USB-C 허브 사양 미달 확인**:
  - `system_profiler` → USB 2.0 HUB (480Mbps, Vendor wch.cn)
  - `ifconfig en6` → `media: 100baseTX <full-duplex>` (100Mbps 한계)
  - 박스 표기(USB 3.0 + 10/100/1000) vs 실제(USB 2.0 + 10/100) 불일치
  - Blaze GigE Vision은 1Gbps 필수 → 어댑터 신규 구매 필요

#### 3. ace2 12V 부품 운반 + 한솔 답변 + 어댑터 발주 결정 (저녁)

- **ace2 12V 전원 부품**: 5/8 오전 NG로 분류했던 `LOADUS EQ-4212Fctc` + `M8/6P-PWR` = **ace2 전용 전원**으로 정정. 공장 재방문 운반 완료
- **한솔 단톡 답변** (김주엽 과장):
  - ace2 C-mount 렌즈 + 이더넷 케이블 = 한솔 측 보유 (추가 구매 불필요, 인수 예정)
  - "렌즈 2개" 의미 추가 확인 필요 (ace2 1대 vs 2대)
- **어댑터 발주 결정**: **ipTIME U1G-C × 1개** (USB 3.0 5Gbps + Realtek RTL8153, EFM 정품, 약 1.5~2만원)
  - 탈락: TP-Link UE300C(Sonoma 미지원 보고) / Belkin F2CU040(2019 MBP 크래시 사례) / Anker A83410(Sonoma drop 사례) / Sonnet Solo2.5G(직구 1주일+) / UGREEN CM275(오버엔지니어링)
  - 1개만 발주 이유: ace2 부품 한솔 보유 → 추가 어댑터는 ace2 셋업 시점 별도 발주
- **결제 요청 메시지 작성 완료** (팀장님 제출용)

#### ⭐ 어댑터 도착 후 검증/셋업 절차 (8단계, 반드시 순서대로)

| # | 행동 | 검증 명령 / 기대 결과 |
|---|------|---------------------|
| 1 | 박스 개봉 + Mac에 꽂기 | `system_profiler SPUSBDataType \| grep -B 2 -A 8 "RTL\|U1G\|Realtek"` → `Speed: Up to 5 Gb/s` |
| 2 | 이더넷 link 확인 | `ifconfig en6 \| grep media` → `1000baseT <full-duplex>` |
| 2-1 | (link 안 잡힘 시) 드라이버 설치 | iptime.com → U1G-C macOS 드라이버 → 시스템 환경설정 보안 허용 → 재부팅 |
| 3 | 카메라 데이터 케이블 연결 | Blaze ETHERNET → GigE-Cable-10M-R → 어댑터 RJ45 → Mac USB-C |
| 4 | link 재확인 | `ifconfig en6 \| grep media` → 1000baseT 유지 |
| 5 | Mac 이더넷 IP 고정 | 시스템환경설정 → 네트워크 → IPv4 수동 → 192.168.10.1 / 255.255.255.0 |
| 6 | pylon 설치 | Basler 사이트 → pylon Camera Software Suite (macOS Intel) + Blaze Supplementary Package, `pip install pypylon` |
| 7 | 카메라 검색 | pylon IP Configurator → Blaze-112 (S/N 40737830, MAC 00:30:53:37:BB:6E) 자동 검색 → IP 192.168.10.10 할당 |
| 8 | 라이브 depth | pylon Viewer 또는 blaze Viewer → Blaze 선택 → 스트림 시작 → depth 영상 확인 |

검증 실패 시:
- `Up to 480 Mb/s` 또는 `100baseTX` → 쿠팡 즉시 환불 → UGREEN CM275(RTL8156) 등 재검토
- 인터페이스 안 잡힘 → ipTIME 사이트 macOS 드라이버 설치

#### 코드 수정 항목 (라이브 검증 후)

`bin_picking/src/acquisition/basler_capture.py`:
- `BLAZE_112_SPEC` fx/fy: 현재 fx=fy=460 → 정정 fx≈416, fy≈188 (FOV 75°×104° 기준)
- `ACE2_5MP_SPEC` 모델명: a2A2590-22gcPRO → **a2A2448-23gcBAS**

#### 5/8 마무리 시점 상태

- ✅ 카메라 2대 보유, 케이블 4종 + 12V 부품 모두 사무실 보관
- ✅ Blaze 부팅 검증 / ace2 RJ45 직결 확인
- ✅ 한솔 단톡 답변 수신 (ace2 부품 보유)
- 🔴 BLOCKER: 어댑터 도착 대기 (토요일 예정)
- ⏳ 다음주 월요일: 어댑터 도착 검증 → pylon 설치 → 라이브 depth → 코드 수정

#### 참고 메모리
- `memory/project_basler_office_setup_0508.md` ⭐ (어댑터 결정 + 도착 후 8단계 검증/셋업 절차)
- `memory/project_basler_unboxing_0508.md` (ace2 12V 정정 + 한솔 보유 확정)
- `memory/reference_basler_blaze_112.md` (하드웨어 레퍼런스)
- `memory/project_binpicking_ceo_directive_0506.md` (5/6 대표님 지시)

---

### 운영 인프라 핵심 정보 (재확인용)

#### AICA A100 GPU (비전 학습용, 5/18 부활)

| 항목 | 값 |
|------|---|
| 호스트 | `114.110.133.5:2222` (`root` / `vt2603!`) |
| GPU | NVIDIA A100-SXM4-80GB × 1 |
| 환경 | PyTorch 2.1.0 + CUDA 12.8, conda `/opt/conda` (Python 3.10) |
| 작업 디렉토리 | `/workspace` (49TB NFS, 컨테이너 재시작 시 보존) |
| 6000 인증 | ssh ed25519 key 등록 (무비번 접속) |
| 학습 함정 | `/dev/shm 64MB` → `workers=0 cache=ram` 필수 / `python` PATH 미설정 → `/opt/conda/bin/python` |
| 5/18 첫 학습 | YOLOv8n parts-5class-v1: 150 epochs / **10분 22초** / **mAP50 0.988** |

상세: `memory/reference_aica_a100.md` — 접속 / ssh key 4단계 등록 / 환경 구축 / 학습 운영 / 함정 7가지 / 컨테이너 재생성 시 절차

#### 공장 PC 자동 시작 체계 (4/24 완성)

> 공장 PC 재부팅/정전 시 전원 ON만으로 운영 시스템 자동 복구.

| # | 이름 | 종류 | 포트 | 역할 |
|---|------|------|------|------|
| 1 | **cloudflared** | Windows 서비스 | - | Cloudflare Tunnel (`factory.flickdone.com`) |
| 2 | **OrinuMain** ⭐ | Windows 서비스 (NSSM) | 8085 | `python main.py` (web-api + sequence_service + frontend) |
| 3 | **PreFormServer** | 시작 프로그램 | 44388 | Formlabs Local API |
| +a | file_receiver.py | 시작 프로그램 | 8089 | STL 파일 수신 |
| +a | AnyDesk | Windows 서비스 | - | 원격 접속 |

**재부팅 후 체크 (관리자 cmd)**:
```cmd
sc query cloudflared
sc query OrinuMain
netstat -ano | findstr LISTENING | findstr "8085 44388 8089"
curl http://127.0.0.1:8085/
```

**NSSM 운영 명령** (전체 경로 `C:\nssm\nssm-2.24\win64\nssm.exe` 사용, PATH 미등록):
```cmd
# 재시작
C:\nssm\nssm-2.24\win64\nssm.exe restart OrinuMain

# 완전 정리 후 재시작 (좀비 발생 시)
C:\nssm\nssm-2.24\win64\nssm.exe stop OrinuMain
taskkill /F /IM python.exe
timeout /t 5
C:\nssm\nssm-2.24\win64\nssm.exe start OrinuMain
timeout /t 20  # 초기화 15~20초 필수
```

**참고**: `memory/project_cloudflare_tunnel.md`, `memory/reference_factory_pc_deployment_guide.md`, `memory/project_deploy_bat.md`

#### DB 아키텍처 (4/24 확정)

| 서버 | DB | 용도 |
|------|-----|------|
| 공장 PC | **MariaDB 11.3** (port 3306, AUTO_START) | sequence_service `automation` DB |
| 공장 PC | SQLite (`web-api/data/local.db`) | web-api 프리셋/알림/업로드 |
| 6000 / 카카오 VM | SQLite | web-api 모니터링 전용 |

**MariaDB 위치**: `C:\Program Files\MariaDB 11.3\` / 설정 `data\my.ini` / Windows 서비스 이름 `MariaDB`. 5월 후반 옵션 2c(원격 조회) 구현 시 `bind-address=127.0.0.1` + `remote_readonly` 계정 분리 예정.

**🔒 절대 금지**:
- MariaDB 3306을 공유기 포트포워딩으로 인터넷 직접 노출
- Cloudflare Tunnel TCP ingress + Access 미적용 방치
- sequence_service가 터널 경유 DB로 변경 (인터넷 장애 시 로봇 정지)

#### Formlabs Credentials Rotate 주의 (4/24 학습)

- "Rotate Client Secret" 시 **Client ID도 같이 바뀜** → 두 줄 모두 교체
- 반영 누락 시 해당 서버 Formlabs 401 → 폴링 전체 멈춤
- 스크린샷/문서 공유 시 `.env` 모자이크 필수

#### 한솔 협업 — 미해결/대기

- ⚠️ `runtime.py:121` 4/24 후속 패치 (`{1: None, 2: None}` → `{1: None}`) 미커밋 상태
- ⏳ 4/30 미해결 의문: `git fetch` 인증창 안 뜬 이유 (PAT 캐시 추정, 5월 말 PAT 만료 시 재검증) — `memory/project_deploy_bat.md`
- ⏳ "렌즈 2개" 의미 한솔 추가 확인 (5/8 단톡)
- ⏳ 한화 로보틱스 별도 라이브러리/패키지 확인 (5/6 회의 액션, 한솔 이예승 ASAP)
- ⏳ 빈피킹 카메라 브라켓 설계 (5/6 회의 액션, 한솔 이예승 ASAP)
