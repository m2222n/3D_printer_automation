# Frontend (React + TypeScript + Vite + Tailwind CSS 4)

> 3D 프린터 자동화 시스템 웹 대시보드 — 프린터 모니터링 · 원격 프린트 · 자동화 셀 제어 · 라인 MES

## 개요

- React 18 + TypeScript 5 + Vite 5 + Tailwind CSS 4
- **9탭 UI**: 모니터링 / 프린트 제어 / 대기 중인 작업 / 이전 작업 내용 / 통계 / 자동화 / 자동화 수동제어 / 라인 모니터링 / 공정 제어
- v1 화면 = REST + WebSocket 하이브리드, v2 라인 화면 = 폴링 + ETag/304
- JWT 로그인 — 모든 API 호출은 `services/auth.ts`의 `authFetch` 를 거친다
- 라인 MES 화면의 실 API/목업 전환은 서버 한 값: `GET /api/v1/system/config` 의 `line_mes` (= 서버 `LINE_DSN` 유무). 꺼져 있으면 `mocks/lineMock.ts` 가 답한다

## 프로젝트 구조

```
frontend/
├── src/
│   ├── App.tsx                     # 9탭 라우터 + 알림벨 + 로그인 가드 + 프린터 상세 모달
│   ├── main.tsx
│   ├── components/
│   │   ├── LoginPage.tsx           # JWT 로그인
│   │   ├── Dashboard.tsx           # 모니터링: 프린터 4대 그리드 + 타임라인
│   │   │   PrinterCard · PrinterDetail · PrinterInfoModal · PrinterTimeline
│   │   ├── PrintPage.tsx           # 프린트 제어: 프린터별 독립 컨테이너
│   │   │   PrinterPrintControl · FileUpload · PresetManager · PrintControl
│   │   ├── QueuePage.tsx           # 대기 큐 (드래그앤드롭)
│   │   ├── HistoryPage.tsx         # 이력 (로컬+클라우드, 라인 미등록 표시)
│   │   ├── StatisticsPage.tsx      # 통계
│   │   ├── AutomationPage.tsx      # 자동화: CMD 생성·프린터 할당·셀 START/STOP
│   │   ├── AutomationManualPage.tsx# 자동화 수동제어: DIO·Modbus·TCP (관리자용)
│   │   ├── LineMonitorPage.tsx     # 라인 모니터링 (v2)
│   │   │   LineFlowBoard · lineUi
│   │   ├── ProcessControlPage.tsx  # 공정 제어 (v2)
│   │   │   ControlSidePanel · MonitorScreen · BatchSplitScreen · PartJudgeScreen · RobotManualScreen
│   │   └── index.ts
│   ├── services/
│   │   ├── auth.ts                 # 토큰 저장 · login/logout · authFetch (sliding refresh 헤더 반영)
│   │   ├── api.ts                  # v1 모니터링 (Formlabs Cloud 경유)
│   │   ├── localApi.ts             # v1 로컬 제어 + 자동화 (/api/v1/local/*)
│   │   └── lineApi.ts              # v2 라인 MES (/api/v2/*) — 함수별 실 API/목업 분기
│   ├── mocks/lineMock.ts           # 라인 MES 목업 데이터 (LINE_DSN 없는 서버에서 화면 확인용)
│   ├── types/{printer, local, line}.ts
│   └── hooks/
│       ├── useDashboard.ts         # REST 초기 로드 + WebSocket 구독
│       └── useWebSocket.ts         # 자동 재연결 + 15초 폴링 폴백
├── dist/                           # 빌드 결과물 — web-api 가 정적 서빙
├── vite.config.ts                  # 포트 · /api · /ws 프록시
└── package.json
```

## 9탭 UI

| 탭 | 컴포넌트 | 데이터 | 동작 조건 |
|----|----------|--------|-----------|
| 모니터링 | Dashboard | `api.ts` + WS | 항상 |
| 프린트 제어 | PrintPage | `localApi.ts` | PreFormServer 연결 시 전송 가능 |
| 대기 중인 작업 | QueuePage | `localApi.ts` | 항상 |
| 이전 작업 내용 | HistoryPage | `api.ts` + `localApi.ts` | 항상 |
| 통계 | StatisticsPage | `api.ts` | 항상 |
| 자동화 | AutomationPage | `localApi.ts` (automation) | 공장 PC에서 sequence_service 실행 중 |
| 자동화 수동제어 | AutomationManualPage | `localApi.ts` (manual) | 위와 같음 · 관리자용 |
| 라인 모니터링 | LineMonitorPage | `lineApi.ts` | `line_mes=true` 면 실 API, 아니면 목업 |
| 공정 제어 | ProcessControlPage | `lineApi.ts` | 위와 같음 |

## 버전별 페이지 — v1 / v2 는 API prefix 이고 Phase 는 개발 단계다

`/api/v1` 에 Phase 1~5 가 전부 들어 있고, `/api/v2` 는 Phase 6 라인 MES 만 쓴다(`web-api/app/main.py` 라우터 마운트 기준).

### v1 (`/api/v1/*`) — REST + WebSocket

| 페이지 | Phase | API | 서비스 파일 | 설명 |
|---|---|---|---|---|
| 모니터링 | 1 | `/api/v1/dashboard` · `/printers` · WS `/api/v1/ws` | `api.ts` | 프린터 4대 그리드 카드, 상태 필터, 타임라인 간트. 프린터 이름 클릭 → 상세 모달(Details/Settings/Services) |
| 프린트 제어 | 2 | `/api/v1/local/upload` · `/presets` · `/scene/*` · `/print` | `localApi.ts` | 프린터별 독립 컨테이너. STL 업로드 → 프리셋 저장 → 슬라이스 미리보기·예상 시간 → 전송 |
| 대기 중인 작업 | 2 | `/api/v1/local/print` | `localApi.ts` | 드래그앤드롭 순서 변경, 예약 시간, 30초 자동 새로고침 |
| 이전 작업 내용 | 1+2 | `/api/v1/prints` · `/local/print` · `/local/notes` | `api.ts` + `localApi.ts` | 로컬+클라우드 이력, 필터, CSV, 메모, 재출력 모달. 라인 MES 미등록 작업은 주황으로 표시 |
| 통계 | 1 | `/api/v1/statistics` | `api.ts` | 재료 도넛, 일별 바, 프린터별 가동률 |
| 자동화 | 3 | `/api/v1/local/automation/commands` · `/control/{action}` · `/state` · `/logs` | `localApi.ts` | CMD 생성·프린터 할당(라벨은 `/system/config.printer_serial_map`), 셀 START/STOP/PAUSE, 시뮬 토글, 큐·로그. CMD 행의 `line_tracked` 로 라인 MES 등록 여부 표시 |
| 자동화 수동제어 | 3 | `/api/v1/local/automation/manual/*` | `localApi.ts` | DIO 비트 읽기/쓰기, Modbus 레지스터 읽기/쓰기, 로봇·비전 TCP 수동 송신. 관리자용 — 조작은 서버가 기록 |
| 🔔 알림벨 | 2 | `/api/v1/local/notifications` | `localApi.ts` | 미읽음 뱃지, 드롭다운, 30초 폴링 |

### v2 (`/api/v2/*`) — 폴링 + ETag/304, WebSocket 없음

| 페이지 | Phase | API | 설명 |
|---|---|---|---|
| 라인 모니터링 (`LineMonitorPage`) | 6 | R1 `/lines/{id}/nodes` · R2 `/transporters` · R3 `/wip` | 라인 흐름판(`LineFlowBoard`): 설비·랙 점유와 진척, 반송자원 큐·대기 시간, 재공 파이프라인 |
| 공정 제어 (`ProcessControlPage`) | 6 | R4 `/lines/{id}/control-menu` | 좌측 `ControlSidePanel` 이 설비 목록·화면 종류를 받아 아래 네 화면으로 분기 |
| ┗ 설비 모니터 (`MonitorScreen`) | 6 | R5 `/nodes/{id}/inbound` · R6 `/source-racks` · R7 `/racks/{id}/slots` · R8 `/slots/{n}/queue` · W2 `/moves` · W3 `/nodes/{id}/state` | 투입 대기 큐, 직전 출처 랙과 칸 FIFO, 이동 등록, 설비 상태 변경 |
| ┗ 배치 분리 (`BatchSplitScreen`) | 6 | R9 `/nodes/{id}/groups` · R12 `/parts` · W1 `/units/{id}/split` | 배치(플레이트) 완료 → 부품 분리 등록. 내용 미상 배치는 부품 마스터에서 고른다 |
| ┗ 부품 판정 (`PartJudgeScreen`) | 6 | R10 `/nodes/{id}/parts` · W4 `/judgements` | 노드의 부품 목록과 양품/불량 판정 |
| ┗ 로봇 수동 (`RobotManualScreen`) | 6 | R11 `/transporters/{id}/commands` · W5 `/commands` · W6 `/transporters/{id}/commands/{cmd}` | 카탈로그에 등록된 검증 명령만 실행(기록·검증까지, 실제 송신은 sequence_service), 조작 기록 |

v2 화면은 서버 `LINE_DSN` 이 비어 있으면 `/system/config.line_mes=false` 를 보고 `mocks/lineMock.ts` 데이터로 그대로 그려진다 — 화면 확인은 DB 없이 가능하다.

### lineApi.ts 전환 규칙

- `/system/config.line_mes` 가 `true` 면 18개 함수 전부 실 API(`/api/v2`)를 부른다.
- `REAL` 집합은 그 전에 함수 하나씩 강제로 켤 때만 쓴다(평소 비어 있음).
- 라인 ID는 하드코딩하지 않는다 — `currentLineId()` 가 `/system/config.line_id` 를 읽는다.
- v2 읽기는 ETag 를 보내고 304 면 기억한 본문을 쓴다.
- 쓰기 결과의 `warnings` 는 "미송신 사유"로 화면에 표시한다(로봇 명령은 기록·검증까지).

## 설치 및 실행

```bash
cd frontend
npm install
npm run dev          # http://localhost:5180 → API 프록시 127.0.0.1:8085
npm run build        # tsc -b && vite build → dist/
npm run lint
```

개발용 포트 분리(main과 병행): 리포 루트에서 `./scripts/dev_develop.sh` → vite **5181** → web-api **8086**.
환경변수 `VITE_PORT` · `VITE_API_TARGET` 으로 직접 지정할 수도 있다.

## 데이터 흐름

```
로그인 → 토큰(localStorage) → authFetch → X-New-Token 헤더로 sliding refresh
v1: REST 초기 로드 → State → WebSocket 실시간 구독 (15초 폴링 폴백)
v2: 폴링 + ETag/304 — WebSocket 없음
```

## 기술 스택

| 기술 | 버전 | 용도 |
|------|------|------|
| React | 18 | UI |
| TypeScript | 5 | 타입 |
| Vite | 5 | 빌드 · 개발 서버 · API 프록시 |
| Tailwind CSS | 4 (`@tailwindcss/vite`) | 스타일 |

---

_Last updated: 2026-10-02_
