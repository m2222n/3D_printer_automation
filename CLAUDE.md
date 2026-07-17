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
- **로그·리포트** — IRIS 보고, 사업보고서, 외부 제출 파일
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

## ⭐ 대표님 6/18 신규 방향성 — 3D 프린팅 SaaS 플랫폼 + 후공정 모니터링 + ERP (제품화)

> **2026-06-18 대표님 녹음 지시**: 현 시스템(3D프린터 모니터링 + 작업지시)을 앞뒤로 확장해 **타 기업에 판매 가능한 제품**으로 키워라.

세 축으로 확장:
1. **① 앞단 — 고객 셀프 주문 홈페이지**: 고객이 모델 파일 업로드 → **자동 견적** → **PG 결제** → 결제 시 **자동으로 작업 큐 투입**(우리가 출력 시작 누르는 것까지 자동) → 완료 시 **담당자 알림**(카카오톡/SMS/우리 앱 푸시) → 픽업. ⭐ **이 시스템 자체를 타 기업에 판매**(멀티테넌트 제품화).
2. **② 뒷단 — 후공정 작업 카운팅 모니터링**(현재 전무): 공장 모니터에 "어떤 파츠 / 어떤 가공 / 총 몇 개 중 몇 개째" 실시간 표시. ⭐ **로봇과 통신**(동일 작업 몇 번째인지) — 기존 HCR Modbus 자산 연계.
3. **③ ERP**: 원재료(SLA 레진 / FDM 필라멘트) **입고·사용량·잔여·발주 알림** 관리. 6/1 ERP 참고영상 2개(`memory/project_ceo_terminology_study_0601.md`) 기반 학습.

**진행 방식 (대표님 명시)**: **개발 기획을 Claude와 정리 → 대표님께 먼저 보여드리고 검토** → 실개발은 그 후 별도 결정. **바이브 코딩**으로 개발. (코드 짜기 전 명세 → 대표님 align = 5/6 방식과 동일)

⚠️ 현 주업무(빈피킹 + KAIST, ~7/9)와 **별개 트랙**. 6/18 시점 = **기획만 먼저**(실개발 미착수). 6/1 제조용어 프레임(현 웹=MES / 로봇=ATS)과 정합: ①상거래 프론트 + ②MES 확장 + ③ERP 계층 추가.

⭐ **6/29(월) 착수**: 대표님이 6/26 "다음주 월요일에 이 건으로 얘기하자" → 출근 직후 논의 + 3축 기획 초안 작성 착수 약속.

✅ **6/29 기획 초안 작성 완료**: `docs/SaaS_플랫폼_기획초안_0629.md`(MD) + `docs/saas_plan_0629.html`(PDF용). 방향=비전+로드맵, 1순위=① 주문 홈페이지. ⭐**핵심 발견=기존 자산이 3축에 거의 다 매핑**(알림 sender 추상화·Formlabs 견적원천·레진잔량 보유, 결제만 신규). 외부연동 1순위=포트원/솔라피/trimesh. ⚠️행정심사(PG·알림톡)가 코딩보다 오래걸림→선신청 권장.

⭐⭐ **7/7 대표님 회의 = 기획 고도화 지시 (본업 P0, 9월말 지원사업 마감)**: 6/29 초안이 "너무 포괄적"→**정식 기획서**로. ①현 개발현황 정리 ②**타사/FDM 프린터 범용화**(API 있으면 API·없으면 오픈소스 슬라이서, FDM은 오픈소스 잘 나와 난이도 낮음) ③주문·관리 시스템 ④⭐**ERP/MES/ATS로 발전하려면 어떤 기능 필요한지="이거부터"**(1순위). +한솔 로봇교육 재요청. → ✅ **기능정의 문서** `docs/MES_ERP_ATS_기능정의_0710.md`(현황§1·3계층 필요기능§2·프린터 범용화 어댑터§3·주문관리§4·대표님 결정 7가지§5). ✅ **현 앱 정직 현황**(코드 전수조사)=SLA 전용 소형 MES+로봇 ATS(7탭), 3축(주문·ERP·카운팅)은 코드 0건. ✅ 앱 상태점검=3서버 200·PreFormServer connected·프린터 NOT READY(실물출력 시연은 탱크 필요). ✅ **대표님 보고용 HTML 문서**=`/data/jtm/synth_out/factory_system_report.html`(현 앱 설명+앞으로 방향 4파트, sim2real 스타일·PDF버튼, 내부용). 보고용 문서 표준형식→`memory/feedback_report_doc_format.md`. ✅ **코드 리팩터링 완료 = 프린터 어댑터 토대**(`memory/project_printer_adapter_refactor_0710.md`): Formlabs 전용→`PrinterAdapter` Protocol 격리(`web-api/app/adapters/`), 테스트 0→27개 신설(⚠️PrinterSummary 5필드=로봇 계약 동결), 죽은코드(local-api·basic_auth) 정리, `PRINTER_VENDOR` config 스위치. FDM 추가 시 어댑터+factory elif만. 런타임 0 변경(실구동 검증). main 머지(`2a6d69a`)·dual push 완료. **✅ 3개 서버 전부 배포·검증 완료**(6000·카카오VM·공장PC, web-api·JWT·CMD DB등록 정상). ⚠️공장PC 시뮬 CMD는 프린터 4대 OFFLINE(전원·탱크 없음)으로 미진행=리팩터링 무관 물리이슈. ✅ **7/10 대표님 보고 3개 문서(PDF) 제출**(내부용, 대표님만)=①빈피킹 비전 AI 성과 보고(KAIST 우수상 검증·위치0.91/종류0.85/종합0.684) ②sim2real 학습 리포트(11섹션 상세) ③3D 프린터 자동화 현황&확장 방향(SaaS 7/7 지시 답). 배경=대표님 "그동안 공장개발 못 하고 KAIST 교육 들었으니 성과 달라". ⏭️ **월요일(7/13) 대표님 회의에서 SaaS 방향 확정**(3축 우선순위·9월범위·1순위·판매모델·견적단가)→착수. 회의 전=회신 미정.

상세: `memory/project_saas_platform_directive_0618.md` + `memory/project_ceo_saas_directive_0707.md` + `memory/project_current_app_status_0710.md` + `memory/project_printer_adapter_refactor_0710.md`

---

## ⭐ KAIST 빈피킹 자산 → 회사 depth_track 편입 (2026-07-13)

> **2026-07-13 태민님 지시**: KAIST 6주 성과(우수상)를 회사 빈피킹 성과로 만들자. **조교 모델 포함 전부 회사 자산**. 목표 4개(지원사업 데모·실제 로봇 피킹 E2E·성능 향상·정식 이식), 방법 불문·성과가 기준.

- **위치**: `bin_picking/depth_track/` — 기존 `yolo_track/`(RGB YOLO)과 **대등한 두 번째 인식 트랙**. depth_track = Blaze ToF depth 단독 + CAD codebook 매칭(색·재질 무관, CAD만 있으면 데이터 수집 없이 학습).
- **방식**: 원본 `~/kaist_project` **불변** + 복사 편입. 구조 = `model/`(조교 depth-only 모델, import 유지) + `mentoring_new/`(학습·평가 진입점) + `synth/`(합성 생성 BlenderProc) + `scripts/`(Blaze 촬영·라벨링) + `visual_hull/` + `data/`(6000 상주 심볼릭 링크).
- **최종 성능**: 27종 실측 test100 **F1 0.684**(위치 0.88/종류 0.85). ✅ **A100서 실제 재현 검증**(`scripts/reproduce_f1_0684.sh`): 재현 0.683649 = 발표 0.683649, 차이 0.000000. best.pt 4개 온전.
- **편입 규칙**: 코드만 git(dual push=한솔 미러 OK, 보안정리 완료: 점자→대상부품·A100 IP→`$GPU_HOST` 환경변수·실사문서 gitignore) / 대용량 데이터·체크포인트는 6000 상주·`data/` 심볼릭·git 제외.
- ✅ **GPU 전략(대표님 7/13 지시)**: 개발 GPU = **A100**(임대 넉넉, 재현·재학습·성능실험) / 배포 최종 타깃 = **NVIDIA Thor**(Jetson Thor 엣지 AI, 대표님 예정) / **IPC-510 = 공장 하드웨어 세팅만**(태민님 GPU 배포 대상 아님, 대표님·현장 영역). ⭐ **태민님 역할 = 빈피킹 "개발" 집중**(하드웨어·배포 인프라는 대표님). 모델 작아(batch2·320×576·67MB) Thor 엣지 추론 적합 예상(ONNX/TensorRT 경로). 6000엔 GPU 없음(합성생성·보관 전용).
- **성능 향상**: ✅ TTA(실측 추가 없이, `scripts/eval_tta.py`)=다중스케일 결합 F1 0.6907(+0.007, recall↑). "공짜 소폭"이고 종류식별 병목은 미해결. **핵심 교훈(sim2real)**: 합성 aug 강화는 천장(F1 0.203)→성능 열쇠는 실측 소량 fine-tune(0.203→0.45→0.684), lr이 지렛대. 남은 병목=센서 물리(대칭·표면패턴)→**큰 향상은 실측 데이터·RGB 융합·고해상 depth 필요**.

상세: `memory/project_depth_track_integration_0713.md` + `bin_picking/depth_track/README.md`

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

## ⭐ 전체 프로젝트 그림 — 전공정/후공정 분리 (2026-05-26)

**시연 순서 (대표님 방향성)**:
1. **전공정 시연 1순위** = 한솔코에버 그리퍼 교체 (빌드플레이트 픽업) → 출력→세척→경화 E2E
2. **후공정 시연 2순위** = 빈피킹 (가을 9~10월, 협력사 페이스)

**우리 6~8월 미션**: 학습 모델 도메인 일반화 — "수치 자랑"이 아니라 "진짜 현장에서 통하는 모델"

| 공정 | 장비 | 우리 책임 |
|------|------|---------|
| 전공정 | 3D 프린터 4대 (Form 4) + 세척기 2대 + 경화기 | 데이터 수집 + 불량/완료 감지 모델 |
| 후공정 | 빈피킹 비전 + HCR-10L 협동로봇 | 카메라 인식 + 6요소 좌표 출력 |

## ⭐ 데이터 수집 카메라 전략 (2026-05-26)

**핵심**: 데이터 수집 = 핸드폰, 운영 = 전용 카메라. 빈피킹 v2가 검증한 패턴 그대로 전공정에도 적용.

| 단계 | 카메라 | 이유 |
|------|--------|------|
| **데이터 수집 (Phase A)** | **핸드폰** | 다각도/다거리/다조명 즉시 다양화, 빈피킹 v2 mAP 0.99 검증, KAIST 팀원 4명 동시 분담 |
| **운영 — 세척기/경화기** | MaixCAM ($40~50/대, 1 TOPS NPU + WiFi 6 + MQTT) | 온디바이스 추론, 24시간 무인 |
| **운영 — 프린터 4대 timelapse** | 외부 USB/IP 카메라 + 라즈베리파이 4세트 (~$300) — 권고 | 1~4시간 timelapse 화질 우위 |
| **운영 — 빈피킹** | Basler Blaze + ace2 (eye-in-hand) | depth + RGB 동시 |
| **학습 finetune (Phase B)** | MaixCAM 시점 100장씩 추가 | 도메인 갭 깸 |

**5/26 사용자 지시**: 전공정 학습 데이터도 **바로** 모아야 함. 후공정/전공정 병행 수집. 5/30 사무실부터 핸드폰으로 세척기/경화기 LED 상태 시작.

상세 (필요 데이터 분량, 시나리오, 메타데이터 스키마, KAIST 연결 액션): `memory/project_data_collection_long_term.md`

---

## ⭐ Notion 마스터 페이지 — Robot Arm Factory (2026-05-26 전면 갱신)

> ⚠️ **2026-06-09 회사 업무관리 체계 개편됨** — 대시보드 2개 분리(🗓️ 일정 / 📝 업무일지), 매일 일일 업무일지 자동생성, 이슈관리=Hub orinu. **새 워크플로우 = `CLAUDE.local.md` § 업무관리 워크플로우** (일일 양식·주간 간소화 규칙). 아래 Robot Arm Factory 페이지는 프로젝트 개요용으로 유지.

**위치**: `notion.so/orinu/Robot-Arm-Factory-60d973ebb99942c8852017d39d58e6f6`
- 부모: orinu HQ > Physical AI Engineering Hub
- 5/26 MCP 복구 + 일괄 갱신 완료

**구성**:
- 본문 callout 8섹션: 전체 프로젝트 구조 / Hardware / Phase 별 현황 / 후공정 빈피킹 학습 진척 / 데이터 수집 전략 / KAIST / 향후 로드맵 / Operational
- Plans & Roadmap DB: 9 rows (Phase 1~3 완료 + 전공정 그리퍼/시연 + 후공정 학습/카메라/좌표/시연)
- Tasks DB: 20 rows (5/26~28 P0 6건 + 5/29 P0/P1 6건 + 6월~ 백로그 8건)
- Issues & Risks DB: 10 rows (도메인 갭 High + Part5 정체 + ACE2 + IPC-510 + 등)

**명명 규칙 (사용자 5/26 결정)**:
- ✅ Notion = **"한솔코에버"** 실명 OK
- ❌ GitHub/README/외부 출력물 = "협력사" 유지 (보안 원칙 그대로)
- 메모리/CLAUDE.md = 자유

**Notion MCP 연결**:
- VSCode `claude.ai Notion` MCP 활성
- 401 떨어지면 `claude.ai/directory/connectors/...` 에서 "연결 해제" → "연결" 재시도 (VSCode Disable/Enable만으론 안 됨)
- 상세: `memory/project_notion_mcp_setup_pending.md`

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
- 3D 프린터 하단 파손 270만원 분담 협의 중 (⚠️ **6/15 추가 발견**: Form 5대 중 3대 광학 판(LCD/LPU 윈도우) 균열 → 출력 불가, 멀쩡한 2대(ShrewdStork+Gecko)만 가용. 대표님/예승님 보고 필요 = 이 파손 이력과 묶일 수 있음 → `memory/project_factory_work_0615.md`)
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

| Phase | 항목 | 우선순위 | 상태 (2026-05-26) |
|-------|------|----------|------|
| **Phase 1** | Web API 모니터링 | 🔴 URGENT | ✅ 완료 |
| **Phase 2** | Local API 원격 제어 + 프론트엔드 UI | 🔴 URGENT | ✅ 완료 (5탭 UI + JWT 인증 + 3개 서버 운영) |
| **Phase 3** | HCR 로봇 연동 | 🟡 HIGH | ✅ 한솔 머지 5차 완료. 다음주 예승님 방문 시 실 출력 + 로봇 E2E 테스트 |
| **Phase 4** | 장비 모니터링 (세척+건조 중심) | 🟡 HIGH | ⭐⭐ **7/16 대표님 회의로 범위 재정의**([[ceo-meeting-0716]]): 로봇 자동화=**프린터+세척+건조**(건조 신규), **경화기는 자동화·Vision 대상 완전 제외**(ROI 안 나오면 사람이). 카메라=**OpenMV N6 전환**(AE3 폐기, 대표님 발주). 세척기 **idle/complete=빌드플레이트 유무** 확정. ⭐⭐**모델 방향전환=완료/대기는 OCR 아닌 영상분류**(idle/complete=형상 문제, running만 OCR/카운트다운). **7/16 진행**: MaixCAM 세척기 재촬영·크롭·분류→**분류 PoC 실행 완료**=같은세션 resnet18 F1 0.982(7종 비교 최고)지만 ⚠️**cross-session(다른날 테스트) 0.34~0.70 폭락=배경외우기, 지금 데이터로 실공정 배포 불가**. 데이터 진단=전처리(7/14통짜vs7/16크롭)+양(세션2개뿐) 둘 다 부족. 실공정 지표=cross-session macro-F1+per-class recall. 필요=여러세션 재촬영+crop통일. (태민님 지시 4=모델다돌려최고·데이터진단·최고모델기억·실공정지표) ⭐⭐**7/17 = 최고모델 resnet18 정식 학습·저장(이번주 마무리, best.pt=A100 wash_model_0717) + 분류모델 방향 뒤집힘**: 돌린 8개(수제특징5+딥러닝3) 결과가 알려준 것=①병목은 모델 아닌 데이터(모델 더 돌리기 무의미) ②cross-session만 진실 ③딥러닝이 얕은모델 대비 3%p뿐=문제 단순(상태3개=이진질문2개 뚜껑닫힘/플레이트유무) ④실패는 항상 idle→running(배경 붙잡음) ⑤전처리 섞이면 손해. **결론=분류모델 공정사용 애매→룰베이스+OCR 하이브리드**(running=OCR·카운팅 / idle↔complete=룰베이스 1차·분류 백업 2차, 팀 내 빛반사 룰기반 방향과 일치). **7/14~15 분석**: rapidocr 우승, OpenMV 완료판독 불가·MaixCAM급 필요, 완료판단=타이머(완료 IO 없음)→Vision 용도=검증+카운팅. 세척기 룰기반(빛반사) 가능성. 상세 `memory/project_ceo_meeting_0716.md`+`project_vision_state_detection_0715.md`+`project_hwaseong_support_program_0716.md` |
| **Phase 5** | 3D 빈피킹 비전 시스템 | 🔴 URGENT | ✅ 트랙 2 v2 **5모델 학습 + 분석 완료** (5/22 시작 → 자정 전 종료 → 5/26 분석). **🥇 yolov8n mAP50 0.9939 / 🥈 yolo11s 0.9910 / 🥉 yolov8m 0.9899**. Part2 회복 **v1 0.656 → v2 yolo11s 0.958 (+30%p)** ⭐. Part5 0.909 정체 = v3 보강 필요. 우승 후보 = yolov8n(6.3MB) or yolo11s(19.2MB), 5/27 ONNX + 도메인 갭 후 최종. 좌표 6요소 출력 코드 + PyTorch → ONNX → IPC-510 결정 완료. **🔥 5/22 대표님 통화: 빈피킹 = 가을(9~10월) 협력사 페이스, 우리 = 학습+카메라 완성도** — `project_yolo_v2_training_results_0522.md` + `project_binpicking_timeline_realignment_0522.md` |

### v2 5모델 비교 결과 (5/26 시점) ⭐

| Rank | Model | Params | mAP50 | mAP50-95 | Precision | Recall | best.pt |
|------|-------|--------|-------|----------|-----------|--------|---------|
| 🥇 1 | **yolov8n** | 3.2M | **0.9939** | 0.7458 | 0.991 | 0.978 | 6.3MB |
| 🥈 2 | yolo11s | 9.5M | 0.9910 | 0.7446 | 0.964 | 0.979 | 19.2MB |
| 🥉 3 | yolov8m | 25.9M | 0.9899 | 0.7255 | 0.972 | 0.947 | 52.1MB |
| 4 | yolo11m | 20.1M | 0.9868 | 0.7225 | 0.982 | 0.929 | 40.5MB |
| 5 | yolo11l | 25.3M | 0.9842 | 0.7363 | 0.967 | 0.916 | 51.2MB |

**핵심 발견**: 가장 작은 yolov8n이 1등 — 데이터셋 작아서(946 aug) 큰 모델 과적합 경향. **Part2 Recall +30%p 회복** (5/20 공장 멀티 촬영 효과 입증). **Part5 0.909 정체** = v3 보강 필요. 상세 5×5 클래스별 표 + 다음 액션 → `memory/project_yolo_v2_training_results_0522.md`

### v3 학습 계획 (5/27 수립) ⭐

> 사명: **"외운 모델(0.99)" → "현장에서 통하는 모델"** (도메인 일반화 + Part5 약점 해소). 계획서: `bin_picking/yolo_track/V3_TRAINING_PLAN.md`

v2의 두 약점을 v3가 푼다:
1. **Part5 Recall 0.909 정체** (5모델 전부 동일 = 데이터 문제) → Part5 단일/멀티 보강 50~80장 + 클래스 균형
2. **도메인 갭 미검증** (valid도 train과 같은 환경) → 다른환경 100~150장

⭐ **도메인 갭 hold-out 전략** (가장 중요): 5/29 다른환경 촬영분의 30%(30~40장)를 **학습에 절대 미투입** → v2 두 모델(yolov8n vs yolo11s) inference로 **우승 모델 정직하게 확정** + 도메인갭 개선 측정. Roboflow `20260529_holdout_*` 별도 batch, export 제외 (누수 방지 = 생명).

모델 후보: v2 5개 → **v3는 yolov8n + yolo11s 2개 집중** (데이터 작아 큰모델 과적합 교훈). 7클래스(Part6/7 통합) vs 5클래스는 5/29 촬영량 보고 현장 판단. 성공 기준: Part5 Recall 0.95+ / hold-out mAP50 0.90+ / 우승 1개 확정 + ONNX 변환.

**5/27 재택 작업**: 한솔 6요소 YAML 샘플(`sample_output_6elements.yaml`) + 카톡 확정본(성과공유+방향확인 톤, 미발송) + v3 계획서 작성. **ONNX·도메인갭은 보류** (6000 GPU없음+디스크99% / 평가셋 없음 → 5/29 사무실 IPC-510). — `memory/project_binpicking_overview.md` + `bin_picking/yolo_track/V3_TRAINING_PLAN.md`

---

## 📍 주요 버그 fix 2건 (5/29 JWT / 6/1 Formlabs) + 재발 방지 룰

> 일자별 진척 상세는 메모리. 여기엔 **재발 방지 룰**(아키텍처 차원 영구 규칙)만 보존.

**1. JWT 회귀 버그**(5/29, `db6adcf`) — 5/6 JWT 도입 시 sequence_service 클라이언트 Authorization 누락 → 운영 모드 web-api 401 → CMD 픽업 실패. fix=`web-api/app/core/jwt_middleware.py` loopback 면제 → [[jwt-sequence-service-bug-0529]]
**2. Formlabs status stale 버그**(6/1, `044ddb7`) — Cloud API가 이전 `current_print_run.status=FINISHED` 유지, `ready_to_print`만 갱신 → 우리 웹 stuck. fix=`formlabs_client.py` `FINISHED+ready_to_print=READY`→IDLE → [[formlabs-status-stale-bug-0601]]

### 🔐 재발 방지 룰 (두 사고 공통 = 외부 API/내부 호출자 동기화)
- **web-api 인증/미들웨어/응답 스키마 변경 시** 내부 호출 클라이언트 같이 확인: `sequence_service/app/cell/printer_interface.py`, `factory-pc/file_receiver.py`, 향후 추가분
- **외부 API 응답 단일 필드 의존 금지** — stale 가능성 의심, 다른 필드 cross-check, reference client(PreForm 등) 동작과 비교
- **큰 변경/배포 후 검증 루틴**: ① `tasklist|findstr python.exe` 3개+ ② `curl .../local/health`→ok ③ **시뮬 CMD 1회 끝까지**(PRINT_FINISHED→ROBOT_REQ) ④ 로그 401/500 확인. ⚠️ git pull은 안전, **NSSM restart + 운영 모드 첫 진입**이 위험 → [[deployment-verification-routine]]

### 📋 Notion DB 작성 규율 (6/1 사용자 지시, 영구)
- 시작일자 명시 / Priority P0~P3 / **Status 정확히**(예정=To Do / 진행중=In Progress / 완료=Done). 회사 자산+외부 가시성이라 정확성 핵심 → [[notion-task-status-discipline]]

### ⭐ 대표님 빈피킹 2시나리오 (6/1) + 개발 전략
- **① 정렬형**(occlusion 약함) **먼저** YOLO bbox/seg+4DoF로 E2E → **② 적재형**(occlusion 심함)은 seg+depth+grasp로 단계 확장 → [[binpicking-two-scenarios-0601]]
- 본인 생존 전략(지시 아님): **빈피킹 = 회사 ↔ KAIST 연계 개발** (1인+화/목 부재, 두 트랙 한 작업으로) → [[feedback-binpicking-kaist-linkage]]

### 한솔 머지 6·7차 — ✅ 공장 배포 완료
- 6차 `310087d`(시뮬 동결 fix, 6/4) / 7차 `5288396`(robot.py 실 TCP I/O, 6/8). ⚠️ 예승님 커밋은 **personal/hansol-dev**에 올라옴 → 머지 시 personal 먼저 확인 → [[hansol-merge-issues]]

---

## ⚠️ 대표님 5/28 4대 지시 + 5/29 후속 갱신

상세: `memory/project_ceo_directives_0528.md`

1. **외부 시연 일정** — ✅ **5/29 오후 통화로 6/1 (월) 15:00 그대로 확정**. (5/29 오전 한 차례 "연기, 6/2 또는 6/5" 흐름 있었으나 오후 재확정.) **시연 범위 = 펜던트 시뮬레이션 + 웹에서 출력 거는 것까지** (5/29 오후 대표님 추가 지시). **시연 본질 = 로봇 펜던트 모션 시연** (실제 출력 X, 5/28 예승님 답변 그대로).
2. **5/28 예승님 답변으로 시나리오 정정** — 정태민 "감 안 옴" → 예승님 본인 권장 "1회로 위험" → **추가 교육 진행 결정**. **5/29 오후 예승님 공장 방문 + 펜던트 시연 전 과정 직접 설명 완료** = 추가 교육 사실상 달성. 5/29 저녁 본인 직접 리허설 진행.
3. **한솔코에버 협업 = 유지 방향** — 5/29 흐름(오전 1시간 30분 통화 + 오후 공장 직접 방문 + JWT fix 공동 검증 + 펜던트 시연 설명)으로 협업 실질 심화. 5/29 사용자 지시: 종료 관련 표현 앞으로 항상 제외 (`memory/feedback_hansol_termination_phrase.md`). 5/28 잠정 보류 항목은 협업 유지 전제로 진행 모드.
4. **ACE2 C-mount 렌즈 8mm + 12mm 둘 다 자체 구매** — 대표님 직접 결재. 5/8 김주엽 과장 "현장 보유" → 5/15 미수령 → 5/20 미장착 확정 → 자체 구매 결정. **렌즈 결정 측정 = 불필요 (둘 다 구매)** 하지만 본업 작동거리·KAIST 라이브 데모 일정 안전마진용으로 측정 가치 남음. → ✅ **6/15 8mm(C23-0824-5M)+12mm(C23-1224-5M) 둘 다 입고 완료**. 설명서 스펙·렌즈 선택 분석(8mm 유력)·KAIST 검증=ACE2 결정 → `memory/project_ace2_camera.md` § 6/15

### 5/28 잠정 보류 항목 → 5/29 진행 모드 전환 (협업 유지 전제)

| 항목 | 5/28 잠정 조치 | 5/29 갱신 |
|------|----------|----------|
| 한솔 카톡 6요소 메시지 | 발송 보류 (로컬 보관) | 종료 가설과 무관, 내용 outdated 가능성 별도 판단 |
| 그리퍼 교체 회의 (한솔과) | 회의 보류 | 진행 모드 |
| 6요소 좌표 명세 미확정 5항목 | 자체 결정 전환 옵션 검토 | 한솔과 자연스럽게 합의 |
| 한솔 인계 코드 4파일 | 이미 인수, 활용 OK | 그대로 OK |
| 로봇 교육 | 종료 시 그 전에 1회 더 요청 옵션 | 5/29 예승님 공장 방문 = 사실상 추가 교육 |
| sequence_service 머지 | 종료 시 추후 X | 진행 모드 (다음 안정 재택일 PR) |

## ⭐ ACE2 C-mount 렌즈 — eye-in-hand 확정 + 후보 좁히기 (5/28)

⭐ **eye-in-hand 확정** (5/28 사용자 정보) — 로봇암에 브라켓 달아서 카메라가 움직이며 빈 부품 촬영·인식. 5/6 회의 합의 구조 재확인.

상세 보고서: `bin_picking/ACE2_LENS_REPORT_0528.md` (5/29 측정 후 최종 확정)

**카메라 사양 정정** (Basler 공식 페이지 5/28 재확인):
- 모델: ace 2 **a2A2448-23gcBAS** (color, GigE)
- 센서: **Sony IMX547** (기존 코드 IMX392·메모리 IMX264 모두 오류)
- 광학 포맷: **1/1.8"** (6.71×5.61mm, 대각 8.75mm)
- 픽셀 피치: **2.74µm** (기존 코드 3.45µm 가정 오류)
- 해상도: 5MP (2448×2048), C-mount

**호환 시리즈 정리**:
| 시리즈 | 최대 센서 | 우리(1/1.8") 호환 |
|--------|----------|------------------|
| C125 | 1/2" | ❌ 비네팅 우려 |
| **C23** | **2/3"** | ✅ 완전 커버 |

**후보 4종 (5/28 검증 완료, 4개 모두 우리 카메라 호환 ✅)**:
- 일반 12mm **C23-1224-5M** : https://www.baslerweb.com/ko-kr/shop/basler-lens-c23-1224-5m-f12mm/
- 일반 8mm **C23-0824-5M** : https://www.baslerweb.com/ko-kr/shop/basler-lens-c23-0824-5m-f8mm/
- Premium 12mm **C23-1224-5M-P** : https://www.baslerweb.com/en/shop/lens-c23-1224-5m-p-f12mm/
- Premium 8mm **C23-0824-5M-P** : https://www.baslerweb.com/en/shop/lens-c23-0824-5m-p-f8mm/

**Premium(-P) vs 일반 차이**: 메탈 하우징 + 조리개/초점 잠금 나사 + 더 정밀한 광학 (왜곡·비네팅 적음). 인식 정확도 약간 유리하나 더 비쌈. 일반도 충분히 사용 가능.

**5/28 대표님 결정**: **8mm + 12mm 둘 다 구매** (고정 위치 변경 대비). 등급(일반 vs Premium)은 대표님 검토 중. **발주는 대표님이 직접** 진행.

**구매처**: 알트시스템(한국 디스트리뷰터) 또는 Basler 한국 공식(`baslerweb.com/ko-kr/`)

**5/29 현장 측정 — 발주 결정과 별개로 v3 학습/캘리브용 여전히 필요**:
- 빈 외형 (가로·세로·**깊이**) / 빈 작업대 높이 / 부품 적재 상태
- **로봇 그리퍼 TCP ↔ 빈 윗면 거리 (최단/최장)** ⭐ — 카메라 실 작동거리
- 그리퍼-카메라 브라켓 실측 (도착 시)
- 알고 있는 기하: 한솔 코드 검증값 = 카메라 광학 중심이 그리퍼 플랜지 위쪽 **~212mm** (우리 그리퍼 교체 후 재측정)

**코드 정정 (입고 후)** — `bin_picking/src/acquisition/basler_capture.py` `ACE2_5MP_SPEC`:
- `"sensor": "Sony IMX392"` → `"Sony IMX547"`
- `"pixel_pitch_um": 3.45` → `2.74`
- `fx`, `fy` 재계산 (선택된 초점거리 / 2.74µm)

---

## 🎓 KAIST 부트캠프 3단계 6주 프로젝트 (6/2~7/9) ⭐⭐

> ✅ **종료(2026-07-09, 🏆우수상·수료).** 최종 결과 = depth-only 부품 인식·식별, 27종 test100 **F1 0.684**(위치 0.88/종류 0.85). sim2real 여정(합성 5% 붕괴→real fine-tune→0.684→학습 종료=병목 센서 물리)·최종 발표·후속(논문 AAAI-27·특허·PoC) 전부 → **`memory/project_kaist_final_presentation_0709.md` + `memory/project_digital_twin_synth_data_research_0609.md`**. 아래 섹션은 **6/5~6/8 시점 역사 기록**(Visual Hull baseline 등)이며 이후 지도학습+합성데이터로 방향 재정의됨.

> **⭐ 방향이 두 번 더 전환됨** — 6/2 미팅(CAD 각도 데이터셋+다객체)에서 다시 **6/5 미팅 = 실루엣 기반 3D 복원→부품 판별**로 대전환. 아래 6/2/5/28~29 정의는 역사. **최신 기준 = `memory/project_kaist_meeting_0605.md` + `memory/project_kaist_visualhull_baseline_0608.md`**.

### 📍 6/5~6/8 최신 기준 ⭐⭐⭐ (Visual Hull baseline 구현 완료)

- **6/5 2차 미팅 = 방향 대전환**: 캡처 vs CAD 렌더 품질격차 발단 → ⭐ **실루엣 → 3D 복원 → 부품 판별** 알고리즘으로 목표 재정의. 1순위 baseline = **Visual Hull(Shape-from-Silhouette)**. 우리 강점 = 렌더 포즈 알고 GT STL 보유 → 어려운 포즈추정 스킵 + IoU/Chamfer 정량비교. 한계 = 내부 오목면 복원 불가. 인식 2안(SAM+YOLO det / YOLO seg), 3D↔2D 비교법 = 조교 추가 리서치 → `memory/project_kaist_meeting_0605.md`
- **6/8 Visual Hull baseline 구현 완료** ⭐ — `~/kaist_project/` (KAIST repo 단일). **28부품 전체 완주 정량표**: IoU mean **0.589** / gt_in_hull mean **0.989** / Chamfer mean 2.85mm. 발표 스토리 = 볼록·단순 잘됨(IoU 0.8+) vs 오목·길쭉 hull 부풂(infl 4.0) IoU 낮음 → Visual Hull 한계 정직하게 증명. (OOM 함정: contains 청크화로 58GB→8GB) → `memory/project_kaist_visualhull_baseline_0608.md`
- **6/9(화) 13:00 1차 중간발표** — PPT 6/8 23:59 제출, 발표자 1명. 28부품 분포표 = 발표 핵심
- **⭐ 빈피킹 직결 방향 (6/8 결정)**: Visual Hull은 기반 역량엔 도움이나 '로봇이 집는 것'엔 간접적(합성·부품1개·40뷰 못찍음) → **KAIST 안에서 빈피킹 쪽으로 당김**. Visual Hull=GT/검증 도구 재배치, 무게중심을 실카메라 부품 인식(YOLO seg/SAM)+mesh↔CAD 매칭으로. 6/9 발표 끝 "빈피킹 연결" 슬라이드 + 조교 제안 → 2주차 반영 → `memory/feedback_kaist_binpicking_pull_0608.md`
- **⭐⭐ 6/9 1차 발표 피드백 = 방향 재조정** (상세 `memory/project_kaist_feedback_0609.md`): embedding(제로샷 retrieval)은 죽지 않되 **순서가 바뀜**. 교수님 = ① 제로샷보다 **사전정의 28부품 지도학습 먼저**(YOLO object detection) ② **CAD에서 depth map 추출**, 하나하나 입력 ③ **test set을 실사진으로**, 학습도 최대한 실사 ④ **Blaze=depth / ACE2=seg** 모달리티 분담(depth-only가 더 나을수도) ⑤ CAD 다각도+**배경 실사 합성** ⑥ 실제 빈피킹 출력 = **6DoF pose estimation**. 조교 = 인력 없음 → **합성데이터(디지털 트윈/도메인 랜덤화)가 현실적**(실제 그림자·질감, 배경 실사 합성), **CAD 연동 물리엔진(Isaac Sim/Omniverse) 알아볼 것**, 조명·질감 후보정 가능, YOLO개량·3D인코더·latent align도 방법. **⭐ 카톡 과제 = CAD/사진 → 3D 디지털 트윈 + 중력 적재 시뮬로 합성데이터 생성**(경로 A=CAD→USD→PhysX 1순위 / B=Photogrammetry·NeRF·3DGS). **다음 미팅 6/19(목)15:30, 그때까지 바쁠 것**
- **⭐ 6/9 당일 합성데이터 PoC 1~4단계 착수·완료** (KAIST 2주차 = 카톡 과제 실행): 조사 결론 **BlenderProc**로 6000에 설치(venv·Blender·출력 전부 `/data/jtm/`) → 우리 STL 빈 **중력 낙하 적재** → **RGB+depth+instance seg+6DoF pose 자동 라벨** 출력 검증 → 부품 배치·카메라 튜닝(8부품 occlusion 적재, 물리 함정 3개 해결). **카메라·실물 0, 코드만으로 라벨 생성** = 조교 "인력 부족→합성" 동기 실현. ⚠️ **6000=GPU없는 VM→렌더 CPU만 / A100=학습 전용(RT코어 없어 렌더 부적합)**. 용량 무제약(scene 0.48MB·/data 847G). 5단계(28부품 대량)~6단계(A100 학습)는 6/10~ → `memory/project_digital_twin_synth_data_research_0609.md`
- **✅ 6/10 5단계 밤샘 배치 완주·검증 = 완벽 성공**: **dataset_v1 2000/2000장**(6/9 12:32~6/10 01:40 ≈13h CPU), **빈 장면 0건**(6/9 디버깅 3개 fix 전수 통과 입증), 에러 0건, visible 평균 8.12개(2~14)=occlusion 다양성, 용량 872MB. hdf5 키=colors/depth(m)/instance·category seg/pose JSON → **Blaze=depth/ACE2=seg + YOLO 라벨 + 6DoF pose GT 코드 자동생성**. 4패널 PNG 육안 검증 통과(품질 우수, 빈 벽 단색만 미세점). **미팅(6/19) 시연용 2000장 PNG 추출**(`preview_all/`). KAIST repo 커밋 `2500bbe`(⚠️6/9 PoC 코드가 세션 끊김으로 미커밋이던 것 확보) → `memory/project_digital_twin_synth_data_research_0609.md` § 6/10
- **✅ 6/10 오후 = 도메인 랜덤화(v2) + Depth 전략 결정** (커밋 `b9dc666`): ⚠️**학습은 6/19 미팅 전까지 보류=데이터 품질 우선**(사용자 지시). 일정정정=6/11 정규수업+6/19 팀미팅 둘 다. (1) **도메인 랜덤화**: 실제 빈 배경 미확정(대표님 확인 필요)→"모르는 배경 논의 무의미"→배경 수백종 랜덤화로 형상 학습. `gen_one_v2.py`(CC0 텍스처 370+종·재질·다광원), v2 300장 가동. (2) **Depth Map 심층**: z=depth=한솔 6요소 필수(없으면 빈피킹 불성립). 합성 depth=완벽매끈=비현실→`depth_noise.py`로 Blaze ToF 노이즈 주입(numpy만). (3) ⭐**활용 전략=depth-only 1차→RGB 라벨 합류(④) 최종**: 배경 모름→depth가 색·배경 무관·형상만=갭 최소 + Blaze 1대 완결 + 교수님 "depth-only 나을수도" 추천. (4) **v2 300장 완주**(빈장면0·visible 7.77·28부품 균형1.5배) + dataset_v2_noisy 후처리 + **미팅 발표자료 4폴더**(`meeting_0611/`: 단색/랜덤화/비교/depth) 커밋 `211ad53`. ⭐**조교 평가기준=데이터셋 품질** → "좋은 데이터셋" 정의 미팅서 직접 확인이 다음 핵심. **학습은 미팅 후**
- **✅ 6/11(목) 15:30 KAIST 미팅 완료 = 목표 재정의 + 방향 지시** ⭐⭐ — 합성데이터 v1/v2/noisy + `meeting_0611/` 4폴더 발표. **목표 재정의("데이터셋 다 만들고 고민")**: ① 모델 = 기성 YOLO(쉬움) or **2D→3D 복원 직접 개발**(도전, 3D 좌표 해석) ② ⭐⭐ **부품 = 회색 단색**(알록달록→색으로 판별 위험 / ⚠️6/10 부품색 랜덤화와 상충 → 배경만 랜덤·부품은 회색 고정) ③ ⭐ **28부품 3D 좌표값 추출 가능 확인**(실루엣X, CAD raw 코드로 될 듯, 안되면 조교 헬프·시작 전 말씀) ④ **GitHub 리포 조교 공유** ⑤ **실물 빈피킹 데이터셋 촬영**(없는 부품 출력 + 10~15개 무작위 + **100장**, **조명 중요**) ⑥ v2 더 사실적으로 + 학습 전략. **샘플 나오는 대로 조교 공유**. **학습 보류 유지**("데이터 다 만들고 고민") → `memory/project_digital_twin_synth_data_research_0609.md` § 6/11 미팅. 다음 미팅 일정 미정
- **✅ 6/12(금, 민방위 휴무) = v3 합성데이터 신설(회색+배경확정) + 기존 3셋 PNG 추출** ⭐ — 6/11 미팅 ①(부품 회색 단색) 반영. `gen_one_v3.py`/`run_batch_v3.sh` 신설(v2 보존): **부품 회색 단색 고정**(색 판별 방지, v2 색 랜덤화 폐기) + **배경 2종 scene랜덤**(사용자 결정 "박스=투명벽/책상=벽제거", 실제 빈피킹 2시나리오 정합) = **투명 플라스틱 박스=적재형**(얇은 투명벽, 부품 8~15개 촘촘 쌓임) / **흰색 책상=정렬형**(벽제거+큰 흰평면 0.75m, 부품 4~8개 드문드문). ⭐**1차 검증 후 Claude 냉정 피드백→시나리오 분리 보강**(1차는 두 배경 적재패턴 동일→무의미, 부품수/낙하범위/높이 배경별 분기로 적재형↔정렬형 구분). **v3 2000장 배치 setsid 가동**(`dataset_v3`, ~6~7h). 기존 v1/v2/v2_noisy 4패널 PNG 6000장 추출(`png_export/`, 사용자 맥북 바탕화면 다운→Drive). 디버깅 5건(Blender4.2 `Transmission`→`Transmission Weight` / 흰책상 depth 45%inf=평면<화각→평면확대 / 투명박스 벽30mm→6mm / seg벽색칠=instance정상·category=0정확 / 정렬형 흩뿌림 과다 visible↓). **v3 2000장 완주**(빈장면 3건/2000) + 4셋 PNG 8000장 추출 + 샘플 160장 → **GitHub 푸시 2건**(`9ccb977` v3코드 + `efe48de` README 합성데이터 섹션·synth/ 안내, 조교 코드리뷰용) + Drive/단톡 공유 + **회사 주간보고서 작성**(Notion, 한 주 성과 묶음). 오늘 할 일 5개 중 4개 완료(IRIS만 남음) → `memory/project_digital_twin_synth_data_research_0609.md` § 6/12
- **✅ 6/15(월) = 조교 피드백 3건 처리 + 현장 촬영 착수** ⭐ — (1) **GitHub 404 → KAIST repo PUBLIC 전환**: 조교 접근 불가(Private+collaborator 본인만). 전수 보안 점검(추적파일27+커밋10+README+PPT context=회사정보/credentials/IP/실명 0건) 후 `gh repo edit --visibility public`. 교육 기간 Public OK(사용자 결정). STL은 .gitignore 제외 유지. (2) **raw CAD = 원본 STL 28개 확정·Drive 공유**(STEP 원본 시스템에 없음=6/4 변환 후 미보관). (3) **팀원 contour 시도 폐기 방향**: 조교 "contour는 겹친 물체 전부 하나로 봄→구분 불가, 다른 방식"(Recall 0.41). 우리 합성데이터 GT(instance seg+pose) 있으니 검출 불필요=YOLO-seg 학습이 정답(6/11 ①과 일치). (4) 🏭 **실물 빈피킹 촬영 착수**(6/11 ⑤): 출력 먼저 걸고→있는 부품 촬영(빈 10~15개 적재+조명 다양화+핸드폰, 100장 분산), 15:00 교육 때 작동거리(TCP↔빈) 측정 동반. ⏭️ **다음 = 27부품 3D 좌표 추출 가능성**(수 6/17 재택, 시작 전 조교 보고) → `memory/project_digital_twin_synth_data_research_0609.md` § 6/15
- **⭐⭐ 대표님 6/15: 빈피킹 배경 = 단색** ("뭐가 됐건 단색", 색 미정) — 🔥 6/10 도메인 랜덤화 대전제("배경 모름→랜덤화") 뒤집힘. 운영 배경을 단색으로 통제→배경 랜덤화 불필요, 실제와 같은 단색 학습=도메인 갭 최소(좋은 소식·단순화). v1(단색)이 실제에 근접. **색 미정→배경색 파라미터화**(하드코딩 금지), 회색 부품 대비색(흰/파랑) 권고. v3 배경 2종도 단색 기조로 재정렬 필요 → `memory/project_digital_twin_synth_data_research_0609.md` § 6/15
- **⭐⭐⭐ 6/16(화) KAIST 미팅 = 조교 모델 아키텍처 확정 + 최우선 과제 = 2D 인코더 학습용 numpy 데이터셋** (최신 기준) — 조교님이 **3D 인코더(CAD→pointcloud, 부품을 패치로 나눠 표면 관계성 학습; 입력=우리 STL 28개) + 2D 인코더(DepthMap+label+기울기 메타)를 latent space에서 복원**하는 모델을 **직접 개발**. 우리 역할 = 2D 인코더 학습용 raw 데이터 준비(드리면 조교가 모델 제작). **내 최우선(1순위) = 2D 인코더 numpy 1000장**: 이미지 뽑기 전 raw numpy / label별 마스크 따로 / 한 장 = 마스크+메타(CAD 도면상 기울기)+label / **배경 없애고 depth map**. 신규 생성기 `~/kaist_project/synth/gen_one_2denc.py`(v3 기반 + per-instance 자세 추출 + 배경 NaN 마스킹 + numpy 저장). 저장스펙(사용자 확정)=scene 전체 npz + 부품별 crop npz **둘 다** / 기울기 = quat(wxyz)+euler(ZYX deg) **둘 다**(STL canonical→물리 후 현재자세) / 배경 = 부품픽셀만 남기고 전부 NaN(물리적재는 유지). ✅5장 검증 통과(왕복오차0·배경NaN93%·17/28클래스) → 5장샘플 Drive 업로드+조교 카톡 컨펌요청(회전컨벤션·저장단위·해상도512·NaN) → 🔄1000장 배치 가동(장당 ≈12.3s, 전체 ≈3.5h). **2순위=Depth 카메라 실촬영 10장 / 3순위=Detection 방식 고민(컨베이어 탐지?). 다음 미팅=금 6/19(추정), 데이터셋 최대한 빨리** → `memory/project_digital_twin_synth_data_research_0609.md` § 6/16
- **⭐⭐⭐ 6/19~6/26 = 모델 명문화 → 코드 통합·A100 구동 → 학습 1사이클 완주 → 2차 발표 → 실증 본촬영** (최신 기준) — **6/19 미팅**: 모델 명문화(3D=**PointNet++** arXiv1706.02413 / 2D=VQ-VAE의 VQ, DepthMap만·RGB X·Point뿌리기), 내 ToDo=실증 100장+OpenDataset 3종+Baseline 비교, ⭐논문(TripleAI 다음달말 공저)+특허→대표님 보고, 보고서 도구분담(KAIST=웹Claude). **6/23**: 조교 코드 수신=`github.com/LimHaksoo/Mentoring`(=**CADENCE 파이프라인**=**DETR/Mask2Former계열 depth-only detector + CAD VQ head**) → `~/kaist_project/model/` 통합(`INTEGRATION.md`)+리뷰(`docs/조교_코드리뷰_0623.md`) + **A100 직접 구동**(3D encoder 식별 1.00 + codebook). **학습 병목=`_boxes_from_mask`의 `torch.where` 박스추출(scene당 5.8초)→numpy 투영 최적화(400배, 결과 동일, 모델 불변)**. + OpenDataset=BOP ITODD+IC-BIN 다운 + Blaze 카메라 연결(GigE TL+IP직접, Intensity off)+시험촬영. **6/24**: ✅**detector 학습 완주**(warmup30→joint100→eval, joint best ep84) + **test(100scene/850객체)=recall 1.00 / class 0.804 / CAD 0.798 / mask 0.855 / box 0.682**(depth만 입력) + Zoom 피드백(figure 논문화·⚠️비교 맹점=비교모델 없음→비교테이블·본촬영 가이드) + PPT 15장·대본 최종. **6/25**: 🎓**2차 중간발표 완료**, ⭐Q&A 핵심=PointCloud 질문(2D DepthMap/3D CAD point modality 비대칭 → 향후 depth K-역투영 통일=다음 멘토링 안건). **6/26**: 📷**실증 본촬영 100장 완료**(3그룹×9종 g1=34/g2=33/g3=33, `scripts/blaze_capture_100.py`, raw 848×480 uint16 mm, Mac `~/Desktop/blaze_capture100/`) → 드라이브+6000 전송(`/data/jtm/synth_out/real_capture100/`)+조교 포맷 컨펌 발송→답변 대기. ✅일일/주간보고/IRIS 연구노트 작성 완료. **6/29**: ✅실증 100장 품질점검+그룹정답지 확정(`real_capture100_group_labels.json`)+✅**labelme instance 라벨링 100/100 완료**(SAM2/AI-Box, JSON `labelme_json/` 100개)+논문2편 리서치. **⭐⭐⭐ 7/1 조교 실증 포맷 피드백 = 배경 0 + 0-1 정규화 확정**: ① 배경 싹 다 0으로 밀고 부품만 Normalization 0-1 스케일링(그림=빈 벽/배경물체가 가까운 depth로 섞여 0-1시 부품이 0으로 눌림→배경 제거로 방지, ⬅️우리 labelme mask가 배경 띠 제거 결정적 도구) ② 레이블 확보 확인=✅labelme mask+cid로 evaluation 충족 ③ 학습 시 경계 뭉개는 aug=조교 담당·대기. **⭐측정=합성 부품 depth 0.34~0.43m vs 실측 0.7~3.2m 거의 안 겹침**(교수님 normalize 우려 데이터 확인, 0-1 정규화가 갭 흡수). ✅변환기 수정(`labelme_to_synthformat.py` BG=0+0-1, `NORM_MODE` per_scene|fixed 파라미터화). 미팅서 스케일 기준 확정 후 재변환. **⭐⭐⭐ 7/1 오후 = 교수님 지시 "학습 전 단일 부품 정합성 검증" 실행 → 실측 depth 절대값 약 3.5배 스케일 오류 발견(데이터는 살아있음)**: 조교 파이프라인(`depth_preprocess.py`) 정독=입력단에서 이미 median-subtract robust 정규화(배경 NaN/0 무관 valid=depth>0)→조교 "배경 0"=mask 밖 전부 배경 처리(우리 라벨이 해결). 검증스크립트 `probe_sim2real_matching.py`로 부품1종(main_body) 실측 vs 합성 비교 → **실측 저장 depth 2.8~3.1m인데 CAD실제크기↔픽셀크기 역산=실제 0.8~1.0m**(태민님 "팔 뻗은 정도"와 일치)→**약 3.5배 고정배율 오류**. ⭐**재촬영 불필요**=고정배율 나눗셈복원+정규화 자동상쇄+라벨링100장 스케일무관 100%유효. 의심원인=`blaze_capture_100.py`가 `OperatingMode=ShortRange`/`Scan3dCoordinateScale` 노드 "실패해도 조용히 넘어가게" 설정→미적용. ⏭️①정규화 배율흡수 증명 ②합성 cam_h 0.4~1.0m 스윕 재생성 ③100장변환+평가. 산출 `docs/sim2real_probe_0701/`. 안건문서 `docs/미팅안건_교수님_0701.md`+공유문서 `docs/실증데이터셋_조교공유_0701.md` → `memory/project_digital_twin_synth_data_research_0609.md` §6/23~7/1 (item22~23), `project_basler_setup_history.md` 재연결노하우
- **⭐⭐⭐ 7/2~7/6 = sim2real 도메인 갭 규명 → cam_h 스윕으로 실측 5%→39.6% → 요인분리 6판 재학습 → csblur(엣지블러 light)가 승리축** (최신 기준) — **7/2**: 실측 100장 첫 평가=class acc **5%**(합성 80.4%→붕괴, sim2real 갭이 하필 우리 차별점 CAD codebook 식별에서 터짐). ⭐프로젝트 KPI 그 자체 실패로 규정. cam_h 0.4~1.0m 스윕 재생성. **7/3 미팅(조교 임학수)**: class acc 3지시(①회색조 ②정규화 ③엣지블러)+F1 지표 채택(0.85=사용가능)+실거리 45~50cm. cam_h 스윕 재학습=**실측 5%→39.6%(8배)**=**스케일(카메라 거리) 갭이 진범** 확증. **7/4**: cam_near(45~57cm)로 좁히면 역효과(39.6%→12.5%, 부품 과대)→**부품 픽셀크기 정합=진짜 성능축 확증**(실측594px / camsweep688px=39.6% / camnear1530px=12.5%). **미팅 안건 요인분리(ablation) 6판 병렬 재학습 launch**(baseline=camsweep 39.6%, 각 판 딱 한 변수만). **7/6 6판 전부 완주 결과**: **🥇csblur(엣지블러 light 1mm)가 유일하게 baseline 초과=실측 F1 0.185→0.203**(mask IoU 0.809·합성 F1 0.380 둘 다 최고, 조교 "경계 뭉개기" 방향 맞음·약한 강도가 핵심). csnorm(정규화)0.171=**"조교 `robust_normalize`가 입력단서 이미 흡수" 가설 확증**(음성결과=발표근거) / csblurheavy class 41.9%로 최고나 mask IoU↓로 F1 0.157 / camfit(580px)0.125=크기축 종료 / med 0.116(강도=light 최적). ✅**팀 카톡 공유 완료**. ⭐교훈=진단상 관찰(크기별 표)≠개입실험 결과(스케일↔노이즈 가설 2번 뒤집힘, 실험이 진실). ⏭️**승리축 csblur 위에 하이퍼파라미터(lr/epoch) 튜닝**으로 0.203서 더 짜내기 / baseline 3종 비교테이블=조교 코드 오면 같이 / 목표=**7/9(목) 최종발표**. ⚠️결과취합 함정=`cd /workspace/cadence &&` 필수(상대경로) → `memory/project_digital_twin_synth_data_research_0609.md` §7/2~7/6, CLAUDE.local §7/2~7/6
- **⭐⭐⭐ 7/6~7/7 = real fine-tune 대전환으로 실측 F1 0.203→0.818(test40) → 조교 test100 지시로 정식 재평가 진행** (최신 기준) — **7/6**: 조교·팀원 공통 처방=**합성 aug 그만, real fine-tune**(csblur best.pt→실측 labelme 라벨 fine-tune). real 30장=**0.45**(합성0.203의 2배), 신규100장 촬영·라벨링→200장(side제거X). ⭐⭐**병목 완전 규명(발표 핵심)**=per-scene CSV **위치F1 0.891(완벽) vs 종류정확도 0.613**, 혼동 전부 **좌우/앞뒤 대칭쌍**=depth-only 정보 근본한계. **7/7 오전**: 밤샘 7판 요인분리(csblur→real 200장 fine-tune, 변수 하나씩)=**🥇 G(lr1e-4·50ep) 0.799 목표 0.7 돌파**, ⭐**진짜 지렛대=lr**(3e-5/1e-4/1e-5=0.63/0.80/0.65). **7/7 오후**: **LMN 완주=L(lr1e-4·80ep) F1 0.818=test40 최고**(M 2e-4=0.802·N heavy=0.740→lr1e-4·csblur·80ep 최적 확정). ✅**eval 그리드서치 16조합=threshold 무영향**(최고 0.8203, +0.002)=병목은 종류 식별력(음성결과). ⭐⭐**조교 지시=split 4:1:5 test100 재평가**("test40 부족, 0.75만 넘어도 좋음")+hyperparameter searching 계속+논문은 few-shot editing pseudo→real. → **test100 재-split(train80/val18/test102 층화·누수0) + 재학습 3판 무인 launch**(밤 11:30 KST 완주 예상, ⚠️test40 0.818보다 낮게 나올 것·목표 0.75). ⏭️결과·기록·HTML갱신·23클래스 대칭쌍병합 학습 검토 / 내일 아침 PPT 병행 / **발표 스토리=0.05붕괴→합성aug 0.203→real fine-tune 0.45→lr·데이터로 0.818→test100 정식조건, 병목=대칭쌍 종류혼동** → `memory/project_digital_twin_synth_data_research_0609.md` §7/6~7/7, CLAUDE.local §7/6~7/7
- **⭐⭐⭐ 7/8 (수) 새벽 = test100 정식조건 재학습(0.684) + 23클래스 대칭쌍 병합 학습으로 F1 최대화(밤샘 무인)** (최신 기준) — 태민님 지시=수단불문 아침10시(KST)까지 학습 F1 최대화. **✅ test100(조교 4:1:5, train80/val18/test102) 재학습=최고 0.684**(lr1e-4·80ep, ⚠️**test40의 0.818보다 낮음=예상됨**, train 140→80·test 40→102, train80이라 과적합). **⚠️L 0.818 vs test100 0.684=다른 시험지**, 조교가 test100 요구했으니 **발표 메인=test100 정식수치**, 0.818은 "데이터늘면 오른다" 근거로만(최종지표 태민님 내일 결정). **✅ eval 그리드서치 16조합=threshold 무영향**(최고 0.8203·+0.002·mask 무영향)=병목은 종류 식별력 재확인(음성결과). **⭐⭐ 23클래스 대칭쌍 병합 학습(병목 직격)**: 병목=대칭쌍(l↔r·front↔back) 종류혼동인데 위치는 완벽(0.91)→**4쌍 같은 부품으로 학습**(27→23)해 혼동손실 제거→0.684→**0.75+ 기대**. 명분=depth-only 좌우대칭 원리상 구분불가+빈피킹 동일취급. memory bank·npz remap 완료(⚠️category_id 1-based 오프셋)·head 자동skip 검증·1ep 완주 확인→**3판 무인 launch(`run_23cls.sh`, ~5h, 아침 6시 KST경 완주)**. lr 27클래스 4판은 1판만 돌다 23클래스 우선순위로 중단. ⏭️아침=결과확인·기록·HTML갱신·발표지표 태민님과 결정·PPT 착수 → `memory/project_digital_twin_synth_data_research_0609.md` §7/8, CLAUDE.local §7/8
- **⭐⭐⭐ 7/8 오전~저녁 = 병합 4쌍 전수검증(1쌍만 정당)·26cls 정직 재학습(0.669)·학습 종료 + PPT v6 완성 → 🏆 7/9 최종발표 우수상·수료 (KAIST 종료)** (최신 기준) — **7/8**: 23cls eval 버그 규명·재eval 0.750, 태민님 CAD 이미지로 **병합 4쌍 전수검증=roll_cover 1쌍만 정당(3쌍은 크기근본차→depth 구분가능)**→23cls(부당) 발표 제외. **⭐종류혼동 3유형**=A축대칭(병합)/B표면패턴(RGB)/C입체돌기(고해상). roll_cover 1쌍만 **26cls 정직 재학습=P(순수) 0.669**(27cls 0.684 못 넘음)→**학습 완전 종료**(lr·epoch·해상도·threshold·병합·loss·aug 전부 천장=병목은 학습 아닌 센서 물리). ⚠️A100 컨테이너 재생성(근형님, /dev/shm 64MB→16GB)+환경복구(numpy 1.26.4·opencv headless). **PPT v6(15장) 완성**(웹Claude). **⭐ 7/9 13:00 최종발표 = 우수상·수료**(킨스타워, 주재걸 교수님). 메인 지표=27종 test100 F1 0.684(위치0.88/종류0.85). 팀=정태민(팀장)·김재균·양재춘·이경범+임학수(조교). **7/10 코드 3곳 백업**: KAIST 팀repo push+README최신화 / 6000 백업(`/data/jtm/a100_backup_0710/` 코드+체크포인트4개 259MB) / 회사repo `kaist_backup/` dual push(⚠️한솔미러 나가는 회사정보 docs 제거). ⏭️후속(태민님 일정)=논문공저·특허·PoC / **본업 복귀** → `memory/kaist_final_presentation_0709.md`, CLAUDE.local §7/9~7/10
- **⭐ 6/17(수, 재택) = 부품 최종 27종 확정 + 2D 인코더 1000장 27종 재생성 + 3D 좌표 추출 probe** — (세션 중단 후 복구 점검: 27종 수정·재생성 지시가 어디까지 됐는지 실파일 점검 = 둘 다 완료). **① 부품 최종 = 27종 확정**: 원본 STL 28종 − `10_guide_paper_roll_l`(bbox 236mm, Form4 빌드볼륨 초과 → 실물 출력 영구불가) = 27종. STL 폴더 `~/kaist_render/stl/`=27개(제외분 `stl_excluded_10/` 보존), 생성기 전부 `glob("*.stl")`이라 폴더 정리만으로 자동 반영. README·메모리 전부 27 정정. **② 2D 인코더 1000장 = 27종 재생성 완료**(6/17 08:47): `/data/jtm/synth_out/dataset_2denc/`(npz 1000+crops 8181, 129M, label 1..27). 패키지 `/tmp/2denc_dataset_1000scenes_27parts.tar.gz`(98M). 5장샘플 포맷 **컨펌 미수신** → 학습 착수 가능하도록 우선 1000장 맥북 Desktop scp→Drive 업로드(컨펌 오면 동일포맷 재추출 ≈3.5h). **③ 3D 좌표 추출 probe + 조교 사전보고 준비 완료**(6/11 ②): `synth/probe_3d_coords.py` → 27/27 watertight(COM·주축·안정자세 추출 OK). 정규화 산출 `coords_27parts.json`(27개: COM world mm + 주축 quat wxyz + canonical bbox + 키포인트 14개 + grasp 폭). **수치 전수 검증 = 초안 일치**: 키포인트 14개(전부) / grasp 최소폭<40mm 25/27 / COM offset>50mm 22/27(max 1009mm). 사전보고 초안 `docs/조교_3D좌표_사전보고_0617.md`(보안 OK). **조교 확인 2개**: ① "3D좌표"=키포인트/6DoF pose/grasp 6요소 중 무엇 ② COM 원점 정규화가 3D인코더 pointcloud와 정합되는지. JSON 공유는 답변 후. → ⏳ 멘트 발송 후 답변 대기 → `memory/project_digital_twin_synth_data_research_0609.md` § 6/17
- **(역사) 6/9 발표 전 방향 = 2D/3D embedding latent alignment**: 조교 제시 = 2D·3D embedder 공유 latent space contrastive align(ULIP/CLIP2Point) → 28 CAD 임베딩 nearest-neighbor retrieval. eye-in-hand 1뷰 + 도메인 갭 흡수. 교수님 Q&A = CAD GT depth map 활용(Blaze ToF 동일 modality). → 6/9 피드백으로 supervised+합성 뒤(5순위)로 재배치 → `memory/project_kaist_meeting_0605.md`
- **⚠️ Push 분리 규칙 (6/8 재강조 + 6/25 보강)**: 회사=dual push / KAIST(`~/kaist_project`)=KAIST repo 단일에만, 회사 내용 절대 금지(KAIST=PUBLIC). ⭐**6/25 추가**: KAIST 코드는 **회사 repo에도 단방향 백업**(7/9 후 빈피킹 본업 연계 자산) = 회사 repo 하위 폴더 복사→dual push 권장(git remote 섞기 X). 역방향(회사→KAIST)은 여전히 금지 → `memory/feedback_push_target_separation.md`

### 📍 6/2 첫 미팅 결과 (역사 — 6/5에 재전환됨)

- **일정**: 다음 미팅 = 금 6/5 13:00 / **1차 중간발표 = 화 6/9 13:00**(주제·데이터, PPT 6/8 제출) / **2차 중간발표 = 목 6/25 16:00**(모델링·결과) / 6주 타임라인 = 1주 데이터셋구축·계획 → 2주 확정 → 3주 전처리 → 4주 학습·검증. 발표 상세 → `memory/project_kaist_midterm_presentations.md`
- **조교 피드백**: 이상치/불량 탐지 = 시급X·쉬움 → **부트캠프 후에도 가져갈 어려운 주제 권장** / 데이터셋 = 다양하되 패턴 비슷, 단색 정면 → 배경 다양화
- **확정 방향**: ⭐ **CAD 도면 모델로 전 parts 데이터셋 구축** (각도 회전 렌더링, 없으면 open dataset) + ⭐⭐ **단일 부품 학습 → 다량 객체 인식/분류** (조교 개인 리서치·피드백 약속 = 적재형 빈피킹 직결). 목표 = **실제 빈피킹에서 유효하게 동작하는 인식 모델**
- **대표님 보고 (6/2) → ✅ 6/4 답변 수령**: **CAD(STEP) 공유 완료** + **화·금 일정 승인** ("화금 해도 됩니다") + 격려
- ✅ **6/5 금 13:00 충돌 해소** — 화·금 승인으로 금=KAIST 고정, 예승님 메시지 불필요 (사용자 판단)
- ✅ **6/4 KAIST 1주차 데이터셋 완성** — CAD→STL 28개→자동 렌더 **1,120장**(28부품×40각도, 정면시점·정각회피, trimesh+pyrender). 6000 `~/kaist_render/` → `memory/project_kaist_dataset_render_0604.md`
- 상세: `memory/project_kaist_meeting_0602.md`

### 5/28~29 정의 (역사 — 미팅 전 베이스라인)

상세: `memory/project_kaist_6week_definition_0528.md` + `memory/project_kaist_advisor_limhaksu_consult_0529.md`

**주제**: 빈피킹 비전 AI — 실제 카메라가 다양한 환경에서 부품을 정확하게 인식

**⭐ 궁극 목표 (5/29 명확화)**: **"실제 카메라/로봇이 정확하게 인식"**. 평가셋 mAP는 중간 신호, **6주차 발표일 ACE2 라이브 카메라 인식 데모**가 종착점. 산출물은 회사 본업으로 이어가서 산업 현장(로봇 빈피킹) 적용까지 염두.

**메인 (4명 다)**: 후공정 빈피킹
- 다양 환경 평가셋 200장 (팀원 4명 × 50장, 학습 미투입)
- Polygon segmentation 400~500장 — **5/29 조교 자문 흡수: SAM 자동 마스크 활용** (수동 라벨링 → 자동화)
- **RePaint/SDEdit 증강 파이프라인** (5/29 조교 자문)
  - **RePaint** (DDPM inpainting, 코드 공개): 배경 다양화 ← 도메인 갭 최대 원인이라 **먼저**
  - **SDEdit** (Stochastic Differential Editing): 조명/질감 다양화
- YOLOv11s-seg 학습 + 도메인 갭 정량 측정 + 보고서
- ⭐⭐ **ACE2 라이브 카메라 인식 데모** — 3주차부터 누적 → 6주차 본 데모

**보너스 (4주차 이후)**: GAA 도전 (조교님 멘토링 약속)
- ⚠️ **GAA = Generate Aligned Anomaly** (6/1 논문 확인) — 우리가 "부품 seg"로 이해했으나 실제론 **산업 검사용 불량 이미지 합성**. 빈피킹 인식과 결 다름 → 회사 **불량검출 트랙**엔 유효. 보너스 위치 맞음

**⭐ 회사 도움 분석 (6/1)**: RePaint/SDEdit = 회사 빈피킹 도메인 갭 직격(강함, 북극성 2단계). GAA = 불량검출 트랙에만 유효(보너스). **단 AI 증강만 믿지 말고 실 ACE2 라이브 데모 + hold-out으로 검증** 必 ("또 다른 외운 모델" 방지). 상세: `memory/project_kaist_advisor_limhaksu_consult_0529.md`

**성공 기준**:
- ⭐⭐ **ACE2 라이브 인식 데모 Pass/Fail** (궁극)
- 다양 환경 mAP50 0.90+ / Part5 Recall 0.95+ / seg mAP50 0.85+ / 증강 ΔmAP +5%p / 회사 자산 인수 (중간 신호)

**범위**: 북극성 1~2단계 직격(라이브 데모 = 2단계 종착점). 3단계(로봇 픽업·IPC-510 배포)는 회사 본업으로 이어감.

**회사 본업 관계 (5/29 명확화)**: KAIST 산출물 = **회사 본업의 부분집합/직접 연결**. 7/9 발표 후 정태민님이 회사 본업으로 가져가 이어감. 데이터·모델·코드·라이브 인식 모듈 다.

**조교 (임학수, 010-3366-7440)**: 5/29 자문 2회. 적극 멘토링 (RePaint/SDEdit·GAA·SAM·샘플 데이터 직접 제공 약속). **첫 미팅: 6/2 (화) 16:30 강의실** ✅.

**보안 가드레일**: 회사명/실명/공장 내부 X. 부품 사진/CAD OK. **필요 시 KAIST 팀용 별도 repo 운영** (회사 메인 ↔ KAIST repo 게이트키핑, 5/29 결정). Roboflow 팀 전용 Project. Colab 권장.

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

## Phase 3: HCR 로봇 연동 ✅ 한솔 머지 7차까지 공장 PC 배포·검증 완료

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

## Phase 5: 3D 빈피킹 비전 시스템 🔄 합성데이터(디지털 트윈) v1~v3 8000장 구축 (6/12)

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

상세 파일 목록 / 줄 수 / 역할: `memory/project_binpicking_overview.md` + `memory/project_binpicking_e2e_history.md`

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

### 마지막 업데이트 일자: 2026-07-10 (KAIST 부트캠프 종료(우수상) 후 정리 — sim2real 여정 완결 + 대표님 SaaS 고도화 지시 착수 + 프린터 어댑터 리팩터링·배포)

> ⚠️ 아래 마일스톤 표는 5/20까지 상세, 이후는 요약. 6/13~7/10 상세 일자별은 `CLAUDE.local.md`(주간 요약) + `memory/project_digital_twin_synth_data_research_0609.md`(§6/13~§7/8) + `memory/project_kaist_final_presentation_0709.md` 참조.

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
| 2026-04-06~10 | 빈피킹 W3+ 파이프라인 완성 (L1~L6 + 그래스프 DB 29종) | ✅ — `memory/project_binpicking_overview.md` + `memory/project_binpicking_e2e_history.md` |
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
| 2026-05-11 | 바텀비전 인수 완료 (Flicdern_v3) + 인터페이스 명세 추출 + 5종 깊게 모드 결정 + 어댑터 도착 전 사전 디벨롭 계획 | ✅ 완료 — `memory/project_bottom_vision_handover_done.md`, `project_binpicking_overview.md`, `project_binpicking_timeline_realignment_0522.md` |
| 2026-05-11 | **사전 디벨롭 전략 A (코드 몰빵) 완료** — 코드 신규 3 (test_basler_live 678 + pose_enumerator 412 + auto_label 815) + 코드 수정 5 (ACE2 a2A2448-23gcBAS / BLAZE fx 417 fy 188) + 문서 3 (1pager v2 + SOP + 바텀비전 인터페이스) + 설정 2 (5종/29종 yaml) + 메모리 4. 5종 실측 발견 (② 단순/① 대칭/④ 단위 의심) | ✅ 완료 — `memory/project_binpicking_overview.md` (트랙 1·2 인프라) |
| 2026-05-11 (오후) | **부품 5종 사진 + 실측 + 1pager v2.1** — 핸드폰 사진 15장 + **P3 캘리퍼스 56mm = bracket_sen_1 확정** (단위 의심 해소). 레진 Grey 통일 + 무광 표면 확인. P5 main_body 거의 확정 | ✅ 완료 |
| 2026-05-11 (오후) | **🎉 어댑터 ipTIME U1G-C 조기 도착** (예상 5/15 → 5/11, 4일 빠름). 박스 사양 OK (USB 3.0 + 기가비트 + macOS 10.6+). 즉시 Step 1~3 검증 PASS (USB 5Gb/s + en8 1000baseT + IP 고정) | ✅ |
| 2026-05-12 | **🎉 Mac Blaze 풀 작동 검증 완료** — pylon Suite 26.04 설치 → IP Configurator 발견 → Wi-Fi 충돌 발견 → 192.168.20/24 영구 분리 → pylon Viewer 미지원 발견 → **pypylon 단독 풀 작동 워크어라운드** (Range component + Mono16). commit 7e28df9 (basler_capture.py +73/-20) push. 핵심 발견: ① Blaze 실 해상도 848×480 (매뉴얼 640 오류) ② macOS Blaze Supplementary 불필요 (pypylon으로 OK) ③ EnumerateDevices 미동작 → BASLER_BLAZE_IP fallback ④ Wi-Fi 충돌 192.168.20/24 분리. test_basler_live.py --live --save --pipeline 풀 PASS. **IPC-510 대기 3주 불필요** | ✅ — `memory/project_basler_setup_history.md` § 5/12 |
| 2026-05-12 | **문서 동기화 commit 3fa9e10** (origin + personal dual push, +98/-5) — 1pager v2.3 (BLAZE 848 + 리스크 #15/#16 + 5/12 의사결정) + SOP (macOS 운영 노트 + BASLER_BLAZE_IP + 트러블슈팅 4개) + Push 정책 단순화 (모든 commit dual = 사용자 기존 패턴) | ✅ — Mac/6000 양쪽 최신 동기화 |
| 2026-05-12 (저녁) | **🎉 라이브 뷰어 commit 0a34b72** (Mac, live_viewer_basler.py +179줄) — pylon Viewer macOS Blaze 미지원 회피용 cv2 + pypylon 단독 인터랙티브 뷰어. 키: ESC/q/s/c/r/+/-. FPS 20.1, depth median 835mm, JET 컬러맵 정상. 사용자 시각 확인 "오 잘되네". **5/12 인프라 단계 완전 종료** — 빈피킹 워크플로우 100% Mac 단독 가능 확정. 이제부터 사용자 부품 배치 + 본 캡처 페이스 | ✅ |
| 2026-05-12 (퇴근 전) | **일정 결정 — 카메라 사무실 보관, 5/15 금 본 작업 시작** — 2.5kg 이동 부담 + 카메라 충격 위험 회피. 수 5/13 재택은 가벼운 작업만 (ACE2 단톡, 예승님 카톡, 1pager align 메시지 초안). 5/15 금 사무실 종일 P5 main_body 첫 시범 + auto_label 실 데이터 검증 | ✅ |
| 2026-05-13 (수, 재택) | **학습 데이터 라벨 신뢰도 인프라** — 외부 커뮤니케이션 3건 발송 보류 (사용자 결정). commit 2개 dual push: `f9ec525` (pose_enumerator v1.1 / stable_poses 5종+29종 재생성 / auto_label 대칭 그룹 + canonicalize_pose_id + simulate PASS) + `dc8d0bf` (pose_validation_protocol.md 신규 = 5/15 첫 30분 부품 던지기 매뉴얼 / SOP v1→v1.1 = § 1.3 조명 valid % + § 2.1 L4 강제 + § 4.1 흔들림 + § 5.1 REVIEW 큐 처리). **6/2 KAIST 3단계 부트캠프 회사 데이터 프로젝트 마감 도입** (W22, 사무실 가용 4~5일 = 5/15·5/18·5/22·5/25·5/29·6/1) — 5종 ~1,200~2,400장 목표, 주제 결정 W21 (5/25~) | ✅ — `docs/binpicking_pose_validation_protocol.md` + SOP v1.1 + `project_binpicking_timeline_realignment_0522.md` 재조정 |
| 2026-05-14 (목, 재택) | **5/15 본 캡처 인프라 완성** — 5 commits 단위로 분리 진행. ① `chore(gitignore)`: captures + dataset_v* + pose_validation_photos* ignore (5/15 commit 사고 방지) ② `feat(basler)`: INTRINSICS_VERSION 상수 + BaslerIntrinsics.version (캘리브 추적) ③ `feat(auto_label)`: intrinsics_version + has_rgb 라벨 추적 (depth-only vs RGB-D 구분) ④ `feat(binpicking)`: check_intrinsics_planar (A4 평면 RMS sanity) + capture_session (yaw sweep wrapper, 진행 카운터 + 중단/재개) + live_viewer 가드 색상 (valid % 70/50% 임계) ⑤ `docs(binpicking)`: runbook 단일 페이지 + friday_smoke_test.sh (5분 sanity) + 1pager v2.4 (§ 0 6/2 마감 + § 5.2 차원 축소 1,200장 옵션 + § 8 #17 silent bias / #18 domain gap + § 14 체크리스트). 시나리오 A 채택 (5/15 depth-only, ACE2는 5/18~ 추가) | ✅ commit 5개 + dual push — 인프라 100% |
| 2026-05-15 (금, 공장) | **공장 방문 — 예승님 만남 + 한솔 브라켓 출력 + 한글 파일명 fix 종료 + Phase 2 E2E 검증** ① ACE2 전원 케이블 한솔 보유분 인수 ② 추가 어댑터 1개 필요 발견 → ipTIME U1G-C 즉시 발주 ③ **예승님 YOLO + Roboflow 제안 채택** — 트랙 1(6DoF) 유지하면서 트랙 2(YOLO) 병행 ④ 🔴→✅ **한글 파일명 fix commit `06e68b4`** — X-Filename ASCII 위반 → RFC 5987 percent-encoding. 3개 서버 동기화 + 공장 직접 검증 ⑤ ✅ **Phase 2 E2E 풀 패스 검증** — 우리 앱으로 STL → 슬라이스 → 프린터 전송 → 실 부품 형성 (`4.Senser_2_dog.stl` 사진 검증) ⑥ 🔥 **출력 실패 진짜 원인 발견** = 레진 탱크 바닥 잔여물 (FEP 굳음, "옛날부터 있던" 물리 운영 이슈, 우리 앱 무관) ⑦ **운영 의문 정정**: Form 4 Local API는 confirm 단계 원래 없음 (5/6 한솔 회의록 "수동 터치"는 출력 종료 후 얘기) ⑧ **시간 차이 미스터리** — PreForm 1h44m vs 우리 앱 4h26m (.form 올려도 4h12m, 우리 앱이 재슬라이스). layer_thickness 기본값 불일치 가설 + .form 워크플로우 패치 working tree에 있음 (미커밋) ⑨ **5개 부품 사전 촬영** — 23+장 × 4종 + 5장 (P5 main_body 가설 폐기, 5/11 P1~P5 라벨은 추정값) ⑩ **부트캠프 주제 = 빈피킹 + 비전 AI** 사용자 명시 ⑪ 일정 정정: 화/목 KAIST → 월/수/금 사무실, 가용 7일 (5/18·20·22·25·27·29·6/1) → 6/1 마감, 6/2 부트캠프 시작 | 🆕 `project_binpicking_overview.md` + `project_basler_setup_history` + `project_factory_print_korean_filename_bug_0515` + `project_phase2_e2e_complete_0515` +  + `project_factory_capture_0520` + `feedback_excessive_questions` |
| **2026-05-18 (월, 사무실)** | **트랙 2 Roboflow v1 + YOLO 학습 완성 + 한솔 빈피킹 코드 인계 + AICA A100 부활** ① Mac Claude Code 릴레이 12 commit pull + smoke test 13/14 PASS ② **Intrinsics 확정**: 848×480 / fx 553 / cx 424 / `estimated_v2_20260513` ③ **A4 sanity 2회 FAIL** — Blaze FOV 75° + 30cm fundamental 불가 (시야 가로 46cm vs A4 21cm = 45% 최대) ④ **P5 파일럿 환경 제약으로 보류** — P5 < 5cm, Blaze 단독 어려움, ACE2 RGB 필요. 사무실 valid % 4~8% ⑤ **트랙 2 우선 전환** ⑥ **Mac Claude Bash false negative 발견** — venv activate 후 PATH 캐싱 / 우회법 3가지 ⑦ **Roboflow 셋업**: Public plan + Project `parts-5class-v1` + 보안 익명화 (`part_1~5`) ⑧ **116장 annotation 완주** (P1=25/P2=26/P3=23/P4=24/P5=18) ⑨ **Version v1**: 278장 (Train 243 + Valid 23 + Test 12), Aug 3x ⑩ **AICA A100 부활** (근형님 컨테이너 재생성) — 6000→AICA ssh key 등록, 환경 구축 (PyTorch 2.1+CUDA 12.8, ultralytics, opencv-headless, numpy<2), 함정 해결 (`/dev/shm 64MB → workers=0 cache=ram`) ⑪ **YOLOv8n 학습 완료** — 150 epochs / **10분 22초** / **mAP50 0.988 / mAP50-95 0.836**. 클래스별 mAP50 ≥ 0.962. 약점: part_2 Recall 0.656 ⑫ 결과 회수 `bin_picking/yolo_track/runs/v1-yolov8n-0719/` (11MB) ⑬ **한솔 이예승 빈피킹 코드 인계** — `bin_picking.zip` 4파일 783줄 (`realsense_pure_python` + `handeye_calibration` + `T_gripper2camera.npy` z=-212mm 검증 PASS + `hanwha_bin_picking` 11단계 시퀀스). 보관 `~/hansol_handover/` (git 추적 X), 통합 전략 C 채택 → `bin_picking/yolo_track/`에 어댑테이션, 예승님 회신 완료 ⑭ 코드 git commit: CLAUDE.md만 (3f3220b) | 🆕 `project_binpicking_overview` + `feedback_mac_claude_bash_caching` + `project_roboflow_dataset` + `project_hansol_bin_picking_handover_0518` + `reference_aica_a100` |
| **2026-05-18 (월, 저녁 후반)** | **대표님 보고 발송 + 좌표 명세 피드백 + 5/19 작성 자산 준비** ① **보고 자료 정리** — `docs/ceo_report_20260518_source_material.md` (Basler YOLO 공식 입장 조사 + YOLOv8 선택 5가지 근거) ② **웹 Claude 보고서 작성** — `ORINU-BINPICKING-REPORT-2026-0518` 16페이지 PDF (아키텍처 다이어그램 + 완료/미완료 + YOLO 근거 + 5/20 다음 단계) ③ **대표님 보고 발송 완료** ④ 🔥 **대표님 피드백**: "한솔에서 달라고 했던 좌표들 x/y/z 좌표인지 뭔지 그거 먼저 물어보고 파악하고 인지하고 일을 해" — 5/6 4대 지시 중 좌표 명세 요청 미해결 지적 ⑤ **5/19 액션**: 예승님께 정식 명세 5가지 질문 메일 (좌표계 기준점 / 회전 표현 / 단위 / 그리퍼 기준점 / 시퀀스 책임) ⑥ **5/19 작성 자산 준비** — `bin_picking/yolo_track/camera/basler_wrapper.py` (~220줄) + `bin_picking/yolo_track/pipeline/bin_picking_main.py` (~360줄) Phase 2 임계 2파일 (5/22 통합 시연 코드 baseline) ⑦ **1pager v2.4 → v2.5** (§ 8 리스크 #19~23 추가: A4 fundamental 불가 / valid % / 데이터 누수 / Public 노출 / best vs last + § 10 의사결정 5/18 8행 추가) ⑧ **5/20 사무실 체크리스트** 작성 (`docs/office_checklist_20260520.md`) ⑨ **추가 사진 촬영** (회사 환경, A4 흰 배경): Part_1~3까지 진행, Part_4/5/멀티 객체는 5/20 이월 | 🆕 `project_hansol_coord_spec_0520` |
| **2026-05-19 (화, KAIST 교육 짬)** | **Roboflow 컨벤션 확정 + 5/18 분 62장 annotation + 협력사 통합 메일 발송** ① **Roboflow 명명 컨벤션 확정**: Class/Tag = `PartN` (PascalCase 통일), Batch = `{YYYYMMDD}_partN` (일자=batch 작업/통합한 날) ② **5/15 batch rename**: `Part_N_initial` → `20260519_partN` (5개) ③ **5/18 분 62장 신규 업로드 + annotation 완료** (Part1=17 / Part2=15 / Part3=18 / Part5=12) → 누적 **178장** ④ **5/20 작업 옵션 B 채택**: Part4 + 멀티 객체까지 통합 후 v2 학습 (manual split 데이터 누수 검증 활용) ⑤ **멀티 객체 촬영 전략**: 9배치 × 3각도 = 27장 (효율 leverage: 부품 고정 + 카메라 각도 / 같은 배치 부품 회전) ⑥ **Occlusion 박스 규칙 확정**: 0~70% 추정 박스 / 70~90% 보이는 영역 / 90%+ 건너뜀 ⑦ ✅ **협력사 통합 메일 발송 완료** — 대표님 5/18 피드백 이행. 톤: 짧게 핵심만 + 솔직 표현. 좌표는 5가지 정식 질문 직접 안 던지고 "어떻게 진행하는 게 좋을지" 의견 요청. 회신 대기 → 코드 잠정 처리 ⑧ 미커밋/미푸시 없음 (외부 SaaS + 메일 작업, 로컬 코드 변경 X) | 🆕 `project_factory_capture_0520` + 갱신 `project_roboflow_dataset` + `project_hansol_coord_spec_0520` |
| **2026-05-20 (수, 사무실, 오전~오후)** | **ACE2 셋업 진단 + 한솔 좌표 명세 답변 수신** ① 🆕 **ACE2 단독 셋업 시도** — 2차 ipTIME U1G-C 어댑터 + Mac en8 192.168.20.1/24 + ACE2 static 192.168.20.20/24 + ping 0.7ms ② **pylon IP Configurator 발견**: a2A2448-23gcBAS S/N 41881328 + 첫 프레임 캡처 성공 (BayerRG8 2448×2048 uint8) ③ **`live_viewer_ace2.py` 신규 작성 + commit `09bdb33`** (232줄, BayerRG8 디모자이크 + GigE 패킷 튜닝 + Focus score 오버레이) origin + personal dual push ④ 🔥 **ACE2 광학 진단 — 렌즈 미장착 확정** — DARK mean 39.4 (Exp 100000us) / BRIGHT mean 212.8 (Exp 26us) / OBJECT 형상 없음. 사진 분석: C-mount 마운트만 있고 빨간 센서 노출. **5/8 메모리 "ACE2 렌즈 미장착, 한솔 보유" 그대로 유지** — 5/15 인수 시 명시적 기록 없음 ⑤ 🆕 **ACE2 ↔ Blaze L자 듀얼 마운트 확인** (5/6 회의 합의 "eye-in-hand 듀얼" 실물 구조) ⑥ 🆕 **GigE 튜닝 발견**: ipTIME U1G-C MTU 9000 거부 (Mac sudo invalid) → 어댑터 max packet 8192 보고하나 Mac MTU 1500 한계. ACE2 5MP 안정 캡처는 해상도 절반(1224×1024) + GevSCPD 2000 권장 ⑦ ⭐ **한솔 좌표 명세 답변 수신** (5/19 통합 메일 회신) — 예승님 답변 3가지: (a) 단일환경 누수 검증은 우리 책임 (b) **YOLOv8 → YOLOv11 + n → m/l 권고** (AICA A100 충분) (c) **좌표 6요소 필요: x,y(2D픽셀) + z(Blaze depth) + edge(외각선) + angle(회전) + label**. "Pointcloud 데이터 받아서 로봇 움직임" ⑧ **5/20 v2 학습 모델 변경 결정**: `yolov8n.pt` → `yolov11s.pt` 또는 `yolov11m.pt` (detection 우선, segmentation은 v3 별도) ⑨ **대표님 5/18 피드백 이행 완료** — 좌표 명세 명확화 + 우리 코드 변경 결정 ⑩ **미확정 5항목** (좌표계 기준점/단위/PCD vs dict/각도 정의/edge 형식) — 5/22~5/29 또는 ACE2 렌즈 인수 시 추가 확인 ⑪ 사용자 결정 대기: 한솔 단톡 ACE2 C-mount 렌즈 보유 확인 메시지 시점 자율 | 🆕 `project_ace2_camera` + `project_hansol_coord_spec_0520` + 갱신 `project_hansol_coord_spec_0520` + `project_binpicking_overview.md` + `project_factory_capture_0520` + `MEMORY.md` |
| 2026-05-22~29 (W21~22) | v2 5모델 YOLO 학습(🥇yolov8n mAP50 0.9939) + 일정 재정렬(빈피킹=가을) + JWT 회귀버그 fix + 대표님 5/28 4대 지시 | ✅ — `memory/project_yolo_v2_training_results_0522.md` |
| 2026-06-01~05 (W23) | 삼성 시연 성공 + Formlabs fix + KAIST 첫 미팅(방향 전환) | ✅ — `memory/project_kaist_meetings_timeline.md` |
| 2026-06-08~12 (W24) | KAIST 1차 발표 + Visual Hull baseline + 디지털트윈 합성데이터 v1~v3(8000장) | ✅ — `memory/project_digital_twin_synth_data_research_0609.md` |
| 2026-06-15~19 (W25) | 부품 27종 확정 + 모델 아키텍처 확정(PointNet++/VQ-VAE) + ⭐대표님 6/18 SaaS 지시 | ✅ — `memory/project_saas_platform_directive_0618.md` |
| 2026-06-22~26 (W26) | 조교 코드 통합·A100 학습 1사이클(합성 class 0.804) + 2차 발표 + 실증 100장 촬영 | ✅ — `memory/project_digital_twin_synth_data_research_0609.md` §6/23~26 |
| 2026-06-29~07-08 (W27) | ⭐⭐ sim2real 여정: 실측 5% 붕괴 → real fine-tune 대전환 → test100 F1 0.684 → 학습 종료(병목=센서 물리) | ✅ — `memory/project_digital_twin_synth_data_research_0609.md` §7 |
| **2026-07-09** | 🏆 **KAIST 부트캠프 3단계 최종발표 — 우수상 수상·수료** | ✅ — `memory/project_kaist_final_presentation_0709.md` |
| **2026-07-10** | 대표님 7/7 SaaS 고도화 지시 착수(현황정리+ERP/MES/ATS 기능정의) + 프린터 어댑터 리팩터링·3서버 배포 + KAIST 코드 3곳 백업 | ✅ — `memory/project_ceo_saas_directive_0707.md` + `memory/project_printer_adapter_refactor_0710.md` |

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
- 상세: `memory/project_basler_setup_history.md`, `memory/reference_basler_blaze_112.md`

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
- `memory/project_basler_setup_history.md` ⭐ (어댑터 결정 + 도착 후 8단계 검증/셋업 절차)
- `memory/project_basler_setup_history.md` (ace2 12V 정정 + 한솔 보유 확정)
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
