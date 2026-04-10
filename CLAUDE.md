# 3D Printer Automation System

> **새 세션 시작 시**: CLAUDE.md, CLAUDE.local.md 읽은 후 `~/.claude/projects/-home-jtm/memory/MEMORY.md`도 반드시 읽을 것

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

### 2026.04.03 (빈피킹 지시)
- **3D+RGB 카메라 확인**: Blaze-112(ToF) 단독인지, ace2(RGB)와 조합해서 포인트 잡는지 확인
- **STL 수집+정리+중복제거 완료 (4/6)**: 55개 다운 → 중복 제거 → 46개 → bbox 동일 분석 → **29종** (17개 `_duplicates/`). STL 최종 목록은 아직 미확정 (대표님도 확정 전, 킵고잉)
- **L1~L6 전체 파이프라인 SW 완성 (4/6~10)**: cad_library + E2E 테스트 + main_pipeline + L5 그래스프 + L6 Modbus TCP. OBB SizeFilter + 포인트 비율 필터 (4/8). 그래스프 DB 29종 완성 + E2E 시나리오 확장 + multi-res ICP (4/10). **인식률 100%(easy), crowded 90%, hard 60%. RMSE 1.0~1.5mm, 매칭 0.4~0.6s/부품**
- **RealSense D435**: USB로 받음 (스테레오 depth + RGB, 640x480). USB 3.0 젠더 필요 (라이브 테스트 블로킹)

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
| **Phase 3** | HCR 로봇 연동 | 🟡 HIGH | 4주 | ✅ 한솔코에버 코드 머지 완료 (4/3) — 시퀀스 서비스 + 자동화 프론트엔드 통합. 3/27 최종 시연 완료 (한솔 자체) |
| **Phase 4** | OpenMV + YOLO 비전 검사 | 🟡 HIGH | 6주 | 🔄 진행 중 (Step 1~3 완료, Step 5 WiFi+MQTT E2E 성공, 학습 이미지 350장 추출) — 빈피킹 우선으로 일시 대기 |
| **Phase 5** | 3D 빈피킹 비전 시스템 | 🔴 URGENT | 11주 | 🔄 W3+ 완료 — **L1~L6 전체 파이프라인 구현 완료**. STL 29종, **그래스프 DB 29종 완성**. **인식률 100%(easy), crowded 90%, hard 60%**. RMSE 1.0~1.5mm, 매칭 0.4~0.6s/부품. E2E 시나리오 확장(crowded/mixed-size/stress) + multi-res ICP 옵션. **다음: 카메라 입고(5월) → 실데이터 검증 + Colored ICP** |

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
│   │   ├── acquisition/         # L1: 카메라 캡처 (depth_to_pointcloud, realsense_capture)
│   │   ├── preprocessing/       # L2: 전처리 (cloud_filter — ROI, 이상치, 다운샘플, RANSAC, 법선)
│   │   ├── segmentation/        # L3: 분할 (dbscan_segmenter)
│   │   ├── recognition/         # L4: 인식+자세 (cad_library, pose_estimator, size_filter)
│   │   ├── grasping/            # L5: 그래스프 계획 (미구현)
│   │   └── communication/       # L6: 로봇 통신 (미구현)
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

### 후처리 장비 (⚠️ API 미지원 → OpenMV 카메라로 해결)
- Form Wash (2대), Form Cure (2대)
- **해결**: OpenMV 카메라로 완료 감지 (대표님 확정, 02-06)

### OpenMV 카메라 (세척기/경화기 완료 감지용)
- **모델**: OpenMV AE3 ($85) - WiFi/BT 내장, NPU, 초저전력
- **센서**: PAG7936
- **펌웨어**: 4.8.1 (최신, 2026-03-09 업그레이드)
- **IDE**: OpenMV IDE v4.7.0 (Intel Mac용, v4.8.x는 ARM 전용)
- **연결 확인**: USB C-to-C → Mac, helloworld 정상 동작 (FPS 15.6)
- **WiFi**: `OrinuAI_2.4GHz` (5GHz 미지원) → 192.168.100.x 대역 (서버와 동일)
- **통신**: WiFi → MQTT (`192.168.100.29:1883`) → FastAPI 서버 ✅ E2E 통신 확인 (3/12)
- **자동 실행**: 카메라 내부 플래시에 `main.py` 저장 시 전원 ON 자동 실행
- **⚠️ 플래시 저장 주의**: `/flash/`에 저장된 파일은 IDE Disconnect/USB 분리 시 소실됨 → 이미지 캡처 시 Mac 직접 저장(IDE Frame Buffer) 방식 사용
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
| 구분 | 서버 | 외부 포트 | 용도 |
|------|------|----------|------|
| 6000 서버 | 192.168.100.29:8085 (VPN: 10.145.113.8) | 8085 | **개발용** (현재 동작 중 ✅) |
| 카카오 클라우드 | 61.109.239.142:22 | 미정 | **운영용** (VM 생성 완료, 세팅 대기) |

### VPN 네트워크 구조 (현재)
```
브라우저 → http://106.244.6.242:8085 → 6000 서버 (VPN: 10.145.113.8) → WireGuard Tunnel → 공장 PC (VPN: 10.145.113.3) → 프린터 4대
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
| W7: 카메라 입고 + 실제 연동 | calibration.py | 카메라 5월 초 | 5/5~5/9 |
| 대표님 보고 | 진행 보고서 | — | 수시 |

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
| 4.3 | **데모 시연** (경기ITP-코에버 3자 간 최종 확인) | ~~03-27~03-31~~ → **03-20 완료** | 원영규, 김주엽 | 플릭던(오리누) + 코에버 |
| 4.4 | **한솔코에버 최종 시연** | **03-27** | 한솔코에버 | 정태민 불참 (외부 교육), 한솔 자체 진행 |

> **오리누 관련 핵심 일정**: 2.1(API 분석, ~3/6) → 2.9(비전 로봇 통신, 1차 방문 3/6) → 2.11(WEB UI, 3/16~) → 4.3(데모 시연, ~~3/27~~ 3/20 완료) → 4.4(한솔 최종 시연, 3/27)
> **3/26 화성시 디지털 가속성장 실사**: 대표님이 직접 진행 (정태민 외부 교육)

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

- **날짜**: 2026-04-03
- **현재 상태**: Phase 1~3 완료. **Phase 5 빈피킹 집중 — 파이프라인 SW 구현 완료, STL 25종 가져오기 + RealSense 테스트 예정**

### 최근 진행 (4/3) — 오늘
- ✅ **한솔코에버 hansol-dev 머지 완료** (`9c161dc`): 시퀀스 서비스 + 자동화 프론트엔드 통합, 인코딩 복원, 기존 코드 보존
- ✅ **STP 어셈블리 트리 전체 분석**: FreeCAD 1.1.0으로 `00_bp_total_assy_asm.stp` 탐색, 후보 33종+불확실 8종 식별
- ✅ **bin_picking/ 폴더 구조 리팩토링** (`99b02fe`): 파이프라인 6단계 모듈 구조
- ✅ **depth_to_pointcloud() + Redwood E2E** (`d977890`): Mac 실행 전체 PASS (267K pts, 2.2s)
- ✅ **L2 전처리 + L3 분할 모듈화** (`9517987`): CloudFilter (레진별 프리셋) + DBSCANSegmenter
- 📌 **대표님 지시 (4/3)**:
  - 공장 PC에 **STL 25종 있음** → 가져와서 테스트 (FreeCAD 분리 불필요)
  - **RealSense 카메라** USB 수령 → 이걸로도 빈피킹 되는지 테스트
  - 3D+RGB 카메라 조합 방식 확인 → 설계대로 (Blaze-112 depth + ace2 RGB)
  - 향후 미묘한 모델링 변경 가능성 있음
- 기원님에게 카톡: 머지 완료 알림 + 새 코드 요약 요청

### 최근 추가 (4/3 오후)
- ✅ **RealSense D435 캡처 모듈** (`73f3d00`): realsense_capture.py + test_e2e_realsense.py, 시뮬 E2E PASS (1.17s)
- ✅ **프리셋 프린터별 독립** (`0e3451e`): printer_serial 컬럼, 프린터별 분리 생성/조회
- ✅ **프린트 전 readiness 체크** (`0e3451e`): 백엔드 6가지 검증 + 프론트 경고/버튼 비활성화
- ✅ **한솔코에버 담당자 변경**: 김기원 주임 퇴사 → 이예승 사원 (eseung97, collaborator 초대 완료)
- ✅ **README.md 전체 업데이트** (`8607c3c`): Phase 3/5, D435, 구조/스택 갱신

### 현재 진행 / 다음 작업
- ✅ ~~STL 수집+정리+캐싱~~ (4/6, 29종)
- ✅ ~~L5 그래스프 + L6 Modbus + L1~L6 통합~~ (4/6)
- ✅ ~~OBB SizeFilter + 포인트 비율 필터~~ (4/8, medium 100%, 0.5s)
- ✅ ~~E2E 난이도 테스트 medium/hard~~ (4/8)
- ✅ ~~그래스프 DB 29종 완성 + 시나리오 확장 + multi-res ICP~~ (4/10, crowded 90%)
- 🔴 **D435 라이브 테스트** → USB 3.0 젠더 확보 후 Mac에서 진행
- 🟡 **[한솔 협업]** 이예승 사원 온보딩 + sequence_service 연동
- 🔄 카카오 클라우드 + Cloudflare Tunnel — 파리드님에게 요청 예정
- 🔄 **카메라 입고 대기 (5월)** → 실데이터 검증 + Colored ICP + 핸드-아이 캘리브레이션

### 대기 중
- ⬜ 카카오 클라우드 VM 환경 세팅 (운영 서버 이전) — 도메인 `lab.flickdone.com` 확정
- ⬜ 한솔코에버 자동화 탭 문서 수신 대기 (예승님)
