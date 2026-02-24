# Frontend (React + TypeScript + Vite + Tailwind CSS 4)

> 3D 프린터 자동화 시스템 웹 대시보드

## 개요

Formlabs Form 4 3D프린터 4대를 모니터링하고 원격 프린트 제어를 위한 웹 프론트엔드입니다.

- React 18 + TypeScript + Vite + Tailwind CSS 4
- 4탭 UI: 모니터링 / 프린트 제어 / 대기 큐 / 이력
- REST API + WebSocket 하이브리드 실시간 업데이트

## 프로젝트 구조

```
frontend/
├── src/
│   ├── App.tsx                     # 메인 라우터 (4탭 구조)
│   ├── main.tsx                    # 앱 진입점
│   ├── components/
│   │   ├── Dashboard.tsx           # 모니터링 탭: 프린터 4대 그리드 카드
│   │   ├── PrinterCard.tsx         # 프린터 카드 (상태/진행률/시간/레진)
│   │   ├── PrinterDetail.tsx       # 프린터 상세 정보 뷰
│   │   ├── PrintPage.tsx           # 프린트 제어 탭: 프린터별 컨테이너 나열
│   │   ├── PrinterPrintControl.tsx # 프린터별 독립 제어 (슬라이스/업로드/프리셋/출력)
│   │   ├── FileUpload.tsx          # STL 파일 드래그앤드롭 업로드
│   │   ├── PresetManager.tsx       # 프리셋 관리 (CRUD)
│   │   ├── PrintControl.tsx        # 프린트 시작 제어
│   │   ├── QueuePage.tsx           # 대기 큐 탭: 드래그앤드롭 순서 변경
│   │   └── HistoryPage.tsx         # 이력 탭: 로컬+클라우드 이력, 재출력 모달
│   ├── services/
│   │   ├── api.ts                  # Phase 1 API (Formlabs Cloud)
│   │   └── localApi.ts             # Phase 2 API (Local API)
│   ├── types/
│   │   ├── printer.ts              # Phase 1 타입 (PrinterSummary, PrintStatus)
│   │   ├── local.ts                # Phase 2 타입 (프리셋/작업/Scene)
│   │   └── index.ts
│   └── hooks/
│       ├── useDashboard.ts         # REST 초기 로드 + WebSocket 실시간 구독
│       └── useWebSocket.ts         # WebSocket 자동 재연결 + 15초 폴링 폴백
├── public/
├── dist/                           # 프로덕션 빌드 결과물
├── vite.config.ts
├── tsconfig.json
└── package.json
```

## 4탭 UI 구조

| 탭 | 컴포넌트 | 기능 |
|----|----------|------|
| **모니터링** | Dashboard.tsx | 프린터 4대 그리드 카드, 실시간 WebSocket, 프린터 상세 뷰 |
| **프린트 제어** | PrintPage.tsx | 프린터별 독립 컨테이너 (파일 업로드 + 프리셋 + 슬라이스 + 출력) |
| **대기 중인 작업** | QueuePage.tsx | 드래그앤드롭 순서 변경, 프린터 필터, 예약 시간, 30초 자동 새로고침 |
| **이전 작업 내용** | HistoryPage.tsx | 로컬 + 클라우드 이력, 썸네일/부품/에러, 재출력 모달 |

## 설치 및 실행

### 개발 모드

```bash
cd frontend
npm install
npm run dev
```

### 프로덕션 빌드

```bash
npm run build
# dist/ 폴더에 빌드 결과물 생성
# web-api/app/static/ 에 복사하면 FastAPI SPA로 서빙
```

## 데이터 흐름

```
REST 초기 로드 → State → WebSocket 실시간 구독 (15초 폴링 폴백)
Phase 1: api.ts (Formlabs Cloud)  →  Dashboard, HistoryPage
Phase 2: localApi.ts (Local API)  →  PrintPage, QueuePage, HistoryPage
```

## 기술 스택

| 기술 | 버전 | 용도 |
|------|------|------|
| React | 18+ | UI 라이브러리 |
| TypeScript | 5+ | 타입 안전성 |
| Vite | 5+ | 빌드 도구 (HMR) |
| Tailwind CSS | 4 | 유틸리티 CSS |
