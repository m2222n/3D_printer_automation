# 3D Printer Automation System

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
- 서버 구성: 5090=운영, 6000=개발

### 2026.02.24 (한솔코에버 미팅)
- ~~소스코드 공유 X, 가이드라인만~~ → **2/26 변경: 소스코드 공유 결정**
- 한솔코에버 작업 서버: Faridh님과 세팅
- 협업 담당자: 김기원 주임 (한솔, GitHub: `justkiwon`), 이나라 주임 (한솔)
- **3/3(화) 공장 방문**: Faridh님 + 정태민 → 한솔코에버 현장 협업

### 2026.02.26
- **소스코드 공유 결정** + **Phase 전환 지시**: 인수인계 후 → OpenMV 개발
- 운영 서버: 5090 VM 폐기 → **카카오 클라우드로 이전 예정**
- AICA A100: 한솔에서 3월간 1대 필요 → 근형님께 전달 완료

---

## Phase별 개발 계획 (확정)

| Phase | 항목 | 우선순위 | 기간 | 상태 |
|-------|------|----------|------|------|
| **Phase 1** | Web API 모니터링 | 🔴 URGENT | 2주 | ✅ 완료 |
| **Phase 2** | Local API 원격 제어 + 프론트엔드 UI | 🔴 URGENT | 3주 | ✅ 완료 (UI 개선 완료, 운영 전환 대기) |
| **Phase 3** | HCR 로봇 연동 | 🟡 HIGH | 4주 | ⬜ 대기 (한솔코에버 협업 확정) |
| **Phase 4** | OpenMV + YOLO 비전 검사 | 🔴 URGENT | 6주 | 🔄 진행 중 (Step 1~3 완료, Step 5 진행 중) |

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
│   │   ├── App.tsx              # 메인 라우터 (5탭 + 알림벨)
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
│   │   │   └── StatisticsPage.tsx      # 통계 탭
│   │   ├── types/
│   │   │   ├── printer.ts       # Phase 1 타입
│   │   │   └── local.ts         # Phase 2 타입
│   │   └── services/
│   │       ├── api.ts           # Phase 1 API
│   │       └── localApi.ts      # Phase 2 API
│   └── package.json
│
├── factory-pc/                  # 공장 PC 스크립트
│   └── file_receiver.py         # STL 파일 수신 + 스크린샷 서빙 (포트 8089)
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

### 후처리 장비 (⚠️ API 미지원 → OpenMV 카메라로 해결)
- Form Wash (2대), Form Cure (2대)
- **해결**: OpenMV 카메라로 완료 감지 (대표님 확정, 02-06)

### OpenMV 카메라 (세척기/경화기 완료 감지용)
- **추천 모델**: OpenMV AE3 ($85) - WiFi/BT 내장, NPU, 초저전력
- **통신**: WiFi → MQTT/HTTP → FastAPI 서버
- **참고**: https://openmv.io/

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
| ShrewdStork | Form4-ShrewdStork | 192.168.219.45 | ⚠️ 헤드커버 고장 중단 |

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
- [ ] 아키텍처 + 스크린샷 대표님 전달

### 인프라
| 구분 | 서버 | 외부 포트 | 용도 |
|------|------|----------|------|
| 6000 서버 | 192.168.100.50:8085 | 8085 | **개발용** (현재 동작 중 ✅) |
| 카카오 클라우드 | 미정 | 미정 | **운영용** (추후 이전 예정) |

### VPN 네트워크 구조
```
브라우저 → http://106.244.6.242:8085 → 6000 서버 (개발) → VPN → 공장 PC → 프린터 4대
```

### 공장 PC 정보
| 항목 | 값 |
|------|-----|
| VPN IP | 10.145.113.3 |
| PreFormServer | 포트 44388 (v3.55.0.606) |
| file_receiver | 포트 8089 → `C:\STL_Files` |
| AnyDesk ID | 1 382 237 708 |
| 자동 시작 | WireGuard + PreFormServer + file_receiver + AnyDesk |

---

## Phase 3: HCR 로봇 연동 ⬜ 대기

- **프로토콜**: Modbus TCP (포트 502), pymodbus
- **로봇**: HCR-12 (빌드플레이트 교체, 세척기 투입) + HCR-10L (후가공, 제품 이송)
- **한솔코에버 협업**: `hansol-dev` 브랜치에서 작업

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

## 기술적 제약사항 및 대안

| 제약 | 문제 | 우리 대안 |
|------|------|----------|
| Web API 읽기 전용 | 프린트 전송 불가 | Local API 병행 |
| Web API 예열/충전 미반영 | IDLE로 표시됨 | Local API 연동 시 해결 |
| 공장 WiFi VPN 문제 | VPN 라우팅 깨짐 | 사무실 LAN에서만. 공장에서는 PreForm 앱 |
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
```

---

## 한솔코에버 협업 타임라인 (3/5 기준 — 세부 일정 변동 가능)

### 1. HW 설계변경 및 구축 — 후공정 하드웨어 변경 (바렐 → 스핀들) | 02-25 ~ 03-18
| ID | Task | 기간 | 수행 | 담당 | 비고 |
|----|------|------|------|------|------|
| 1.1 | 기구설계 컨셉 설계 수령 | 02-25~02-27 | 재원텍 | 원영규 | |
| 1.2 | 고객사(플릭던) 컨셉 확정 및 승인 회의 | 02-26~02-27 | 코에버 | 원영규, 김주엽 | |
| 1.3 | 후공정 변경 사항 가발주 진행 | 02-27 | 코에버 | 황두화 | |
| 1.4 | 구매/가공/제작 (Feeder ASSY, Align 지그, Spindle ASSY) | 02-27~03-09 | 재원텍 | 원영규, 김주엽 | 재원텍 1차 제안(3/3), 예산 조율 중, xArm 활용 데모일정 단납기 조정 |
| 1.5 | 현장 설치 (스핀들→피더→얼라인 순차적) | 03-09~03-18 | 재원텍+코에버 | 원영규, 김기원, 김주엽 | |
| 1.6 | 기존 바렐 연마기 철거 및 반출 | 03-09~03-18 | 코에버 | 원영규, 김기원, 김주엽 | |

### 2. SW 개발 (시스템 통합) — 제어 소프트웨어 및 인터페이스 개발 | 02-26 ~ 03-19
| ID | Task | 기간 | 담당 | 비고 |
|----|------|------|------|------|
| 2.1 | 파이썬 소스 및 API 테스트 분석 | 02-26~03-06 | 김기원 | 플릭던(오리누)에서 API 자료 수신, 분석 설계 중 |
| 2.2 | 로봇 연동 매뉴얼 개발 | 03-07~03-09 | 김기원 | |
| 2.3 | 비전 연동 매뉴얼 개발 | 03-10~03-11 | 김기원 | |
| 2.4 | 3D프린팅 연동 매뉴얼 개발 | 03-12~03-13 | 김기원 | |
| 2.5 | 로봇 시퀀스 개발 | 03-14~03-15 | 김기원 | |
| 2.6 | (후공정) 드릴링 시퀀스 개발 | 03-15~03-17 | 김기원 | |
| 2.7 | (후공정) 비전-로봇 시퀀스 개발 | 03-17~03-19 | 김기원 | |
| **2.8** | **비전 분류 모델 (데모 시연용 5종 확보)** | 02-27~03-06 | 이나라 | 기존 데이터(9종) 활용, 경량화 모델, 서버 활용은 보류 |
| **2.9** | **비전 로봇 통신 작업** | 03-09~03-10 | 김기원, 이나라 | **1차 방문 3/6**: 비전 I/F 및 조명 테스트. **2차 방문 3/9**: 디버깅+SW 로직 구현 |
| 2.10 | 모델 학습 및 Align 보정 | 03-10~03-15 | 김기원, 이나라 | |
| 2.11 | WEB UI 개발 및 통신 | 03-16~03-19 | 김기원, 이나라 | |
| 2.12 | 로봇 티칭 (전공정, 후공정 모션) | 03-15~03-17 | 이예승 | 전공정 PC제어-로봇티칭 통신 규격 확보(3/5) |

### 3. 테스트 및 시운전 | 03-18 ~ 03-20
| ID | Task | 기간 | 담당 | 비고 |
|----|------|------|------|------|
| 3.1 | 단위 테스트 (프린팅/세척/경화/가공) | 03-18~03-19 | 원영규, 김기원, 김주엽 | 데모 시연 후 최종 입고일에 따라 변경 예정 |
| 3.2 | 통합 시운전 (Dry Run) | 03-18~03-20 | 원영규, 김기원, 김주엽 | 단위 테스트 일정에 따라 변경 예정 |

### 4. 최종평가 및 사업종료 | 03-20 ~ 03-31
| ID | Task | 기간 | 담당 | 비고 |
|----|------|------|------|------|
| 4.1 | 안전인증 보완심사 (라이더 위치 재설정 후 사진 제출) | 03-20~03-25 | 원영규 | |
| 4.2 | 최종 완료보고서 제출 | 03-20 | 원영규, 김주엽 | |
| 4.3 | **데모 시연** (경기ITP-코에버 3자 간 최종 확인) | 03-27~03-31 | 원영규, 김주엽 | 플릭던(오리누) + 코에버 |

> **오리누 관련 핵심 일정**: 2.1(API 분석, ~3/6) → 2.9(비전 로봇 통신, 1차 방문 3/6) → 2.11(WEB UI, 3/16~) → 4.3(데모 시연, 3/27~)

---

## GitHub 협업 구조 (한솔코에버)

| 항목 | 내용 |
|------|------|
| 리포 | `m2222n/3D_printer_automation` (Private) |
| main 보호 | Require PR + Restrict deletions + Block force pushes |
| 오리누 작업 | `main` 브랜치 |
| 한솔 작업 | `hansol-dev` 브랜치 |
| 한솔 권한 | Write (Collaborator: `justkiwon`) |
| 리모트 | `origin` = orinu-ai, `personal` = m2222n |

---

## 마지막 업데이트

- **날짜**: 2026-03-09
- **현재 상태**: Phase 1, 2 완료. 한솔코에버 인수인계 완료. **Phase 4 (OpenMV) 개발 착수.**
- **최근 완료**:
  - ✅ **한솔코에버 인수인계 완료** (3/6)
  - ✅ **CSUN 기념품 점자 교구 키링 ~493개 출력 완료** (3/3~3/4)
  - ✅ Mac 개발 환경 세팅 완료 (SSH 키 + GitHub + 서버 rsync)
  - ✅ AICA A100 세팅 완료 (GPU #7, PyTorch 2.4.1+cu121)
  - ✅ GitHub README 다이어그램 정렬 수정 (3/9)
- **현재 진행**:
  - 🔄 **Phase 4 서버 인프라 완료** (3/9): Mosquitto MQTT, vision 모듈 7파일, 10 API, 시뮬레이터
  - 🔄 **OpenMV 카메라 스크립트 작성** (3/9): wash_detector.py, cure_detector.py (샘플 기반)
  - 다음: OpenMV IDE + AE3 카메라 연결 테스트 -> Edge Impulse 모델 학습
- **대기 중**:
  - ⬜ Faridh님 + 한솔코에버 서버 세팅
  - ⬜ 아키텍처 + 스크린샷 대표님 전달 (후순위)
  - ⬜ Grey 프린터 LCD 스크래치 테스트 (대표님 지시)
