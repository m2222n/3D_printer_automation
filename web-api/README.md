# 🖨️ Formlabs 원격제어 시스템

> **Phase 1: Web API 기반 모니터링 시스템**

Formlabs Form 4 3D프린터 4대를 실시간으로 모니터링하고, 프린트 완료/에러 시 알림을 받을 수 있는 시스템입니다.

## 📋 목차

- [프로젝트 개요](#-프로젝트-개요)
- [기능](#-기능)
- [시스템 아키텍처](#-시스템-아키텍처)
- [설치 및 실행](#-설치-및-실행)
- [API 문서](#-api-문서)
- [설정](#-설정)
- [개발 로드맵](#-개발-로드맵)

---

## 🎯 프로젝트 개요

### 연관 사업
- **사업명**: 2025년 경기도 제조로봇 이니셔티브
- **주관기관**: 오리누 주식회사 (구 플릭던)
- **사업기간**: ~2025.12.31
- **총사업비**: 2억원

### 개발 목표
| Phase | 목표 | 상태 |
|-------|------|------|
| Phase 1 | 웹/앱 프린터 모니터링 + 완료 알림 | 🔄 진행중 |
| Phase 2 | 원격 프린팅 작업 전송 | ⏳ 대기 |
| Phase 3 | HCR 로봇 연동 자동화 | ⏳ 대기 |
| Phase 4 | YOLO 비전 검사 | ⏳ 대기 |

---

## ✨ 기능

### Phase 1 (현재)
- ✅ OAuth 2.0 인증 (자동 토큰 갱신)
- ✅ 4대 프린터 실시간 상태 모니터링
- ✅ 프린트 진행률 추적 (레이어, 남은 시간)
- ✅ 프린트 완료/에러 알림 (이메일, 슬랙, 푸시)
- ✅ WebSocket 실시간 업데이트
- ✅ 프린트 이력 조회
- ✅ REST API 제공

---

## 🏗 시스템 아키텍처

```
┌─────────────────────────────────────────┐
│            클라이언트                    │
│   웹 대시보드 / 모바일 앱 / 관리자 PC     │
└──────────────────┬──────────────────────┘
                   │ HTTPS / WebSocket
┌──────────────────▼──────────────────────┐
│         FastAPI 백엔드 서버              │
│  ┌────────────────────────────────────┐ │
│  │ • 프린터 상태 폴링 (15초 주기)      │ │
│  │ • 상태 변경 감지                    │ │
│  │ • 알림 발송 (이메일/슬랙/푸시)      │ │
│  │ • WebSocket 실시간 푸시            │ │
│  └────────────────────────────────────┘ │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│         Formlabs Web API                │
│         (api.formlabs.com)              │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│         Form 4 프린터 4대                │
│   [#1] [#2] [#3] [#4]                   │
└─────────────────────────────────────────┘
```

---

## 🚀 설치 및 실행

### 요구사항
- Python 3.11+
- Formlabs Dashboard 계정 및 API 키

### 1. 프로젝트 클론
```bash
git clone <repository_url>
cd formlabs-web-api
```

### 2. 가상환경 생성 및 활성화
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. 의존성 설치
```bash
pip install -r requirements.txt
```

### 4. 환경 설정
```bash
cp .env.example .env
# .env 파일을 열어 실제 값으로 수정
```

### 5. 서버 실행
```bash
# 개발 모드
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 프로덕션 모드
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 6. 접속
- API 문서: http://localhost:8000/docs
- 헬스체크: http://localhost:8000/health

---

## 📚 API 문서

### 주요 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/v1/dashboard` | 대시보드 전체 데이터 |
| GET | `/api/v1/printers` | 프린터 목록 |
| GET | `/api/v1/printers/{serial}` | 특정 프린터 상태 |
| GET | `/api/v1/printers/{serial}/refresh` | 상태 즉시 새로고침 |
| GET | `/api/v1/prints` | 프린트 이력 |
| WS | `/api/v1/ws` | WebSocket 실시간 업데이트 |

### 응답 예시

**GET /api/v1/dashboard**
```json
{
  "printers": [
    {
      "serial": "FORM4-001",
      "name": "프린터 1호",
      "status": "PRINTING",
      "current_job_name": "점자블록_v3",
      "progress_percent": 67.5,
      "remaining_minutes": 45,
      "current_layer": 135,
      "total_layers": 200,
      "resin_remaining_ml": 350.5,
      "is_online": true
    }
  ],
  "total_printers": 4,
  "printers_printing": 2,
  "printers_idle": 1,
  "printers_error": 0,
  "printers_offline": 1,
  "last_update": "2025-01-29T10:30:00Z"
}
```

---

## ⚙️ 설정

### 필수 설정

| 환경변수 | 설명 | 예시 |
|----------|------|------|
| `FORMLABS_CLIENT_ID` | API Client ID | Dashboard에서 발급 |
| `FORMLABS_CLIENT_SECRET` | API Client Secret | Dashboard에서 발급 |
| `PRINTER_SERIALS` | 모니터링할 프린터 시리얼 | `["SN1","SN2","SN3","SN4"]` |

### 선택 설정

| 환경변수 | 설명 | 기본값 |
|----------|------|--------|
| `POLLING_INTERVAL_SECONDS` | 폴링 주기 (초) | 15 |
| `SLACK_WEBHOOK_URL` | 슬랙 알림 URL | - |
| `SMTP_HOST` | 이메일 서버 | - |

---

## 🗺 개발 로드맵

### Phase 1: 모니터링 시스템 ✅
- [x] OAuth 2.0 인증
- [x] 프린터 상태 폴링
- [x] 상태 변경 감지
- [x] 알림 시스템
- [x] REST API
- [x] WebSocket
- [ ] 프론트엔드 대시보드

### Phase 2: 원격 제어 시스템
- [ ] Local API 연동
- [ ] STL 파일 업로드
- [ ] 자동 프린트 준비
- [ ] 작업 큐 관리

### Phase 3: 로봇 연동
- [ ] HCR-12 Modbus TCP 통신
- [ ] HCR-10L Modbus TCP 통신
- [ ] 프린트 완료 → 로봇 트리거
- [ ] 전체 시퀀스 자동화

### Phase 4: 비전 검사
- [ ] YOLO 부품 식별
- [ ] 워싱머신 완료 감지
- [ ] 불량 검출

---

## 📝 라이선스

© 2025 오리누 주식회사. All rights reserved.

---

## 👨‍💻 개발자

- **정태민** - 오리누 주식회사
