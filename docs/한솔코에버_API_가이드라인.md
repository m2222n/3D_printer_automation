# Formlabs 3D 프린터 API 가이드라인

> **작성일**: 2026-02-24
> **작성자**: 정태민 (오리누 주식회사)
> **대상**: 한솔코에버 개발팀 (김기원 주임, 이나라 주임)
> **목적**: Formlabs Form 4 프린터 연동을 위한 API 가이드

---

## 1. 시스템 개요

### 1.1 전체 아키텍처

```
┌────────────────────────────────┐
│        사용자 (웹 브라우저)       │
└────────────────────────────────┘
                │
                ▼
┌────────────────────────────────┐
│      백엔드 서버 (Linux)         │
│      FastAPI + Python 3.11     │
│                                │
│  ┌──────────┐  ┌────────────┐  │
│  │ Web API  │  │ Local API  │  │
│  │ (모니터링)│  │ (프린트제어)│  │
│  └──────────┘  └────────────┘  │
└────────────────────────────────┘
     │ (인터넷)        │ (VPN)
     ▼                 ▼
┌──────────┐   ┌──────────────────────┐
│ Formlabs │   │   공장 Windows PC     │
│  Cloud   │   │  PreFormServer :44388 │
│  API     │   └──────────────────────┘
└──────────┘            │ (로컬 네트워크)
                        ▼
               ┌──────────────────┐
               │  Form 4 프린터    │
               │  (4대, WiFi 연결) │
               └──────────────────┘
```

### 1.2 API 이원화 구조

Formlabs는 **2개의 독립된 API**를 제공합니다. 용도가 완전히 다르므로 반드시 구분해야 합니다.

| 구분 | Web API (클라우드) | Local API (로컬) |
|------|-------------------|------------------|
| **용도** | 프린터 상태 모니터링 (읽기 전용) | 프린트 작업 전송 (제어) |
| **서버** | api.formlabs.com | PreFormServer (Windows PC) |
| **인증** | OAuth 2.0 (Client Credentials) | 없음 (로컬 실행) |
| **프린트 전송** | ❌ 불가능 | ✅ 가능 |
| **프린터 상태 조회** | ✅ 상세 (레진, 온도, 진행률) | ⚠️ 제한적 (연결 여부 정도) |
| **Rate Limit** | IP 100 req/sec, 사용자 1500 req/hr | 없음 |
| **문서** | https://support.formlabs.com/s/article/Formlabs-Web-API | 아래 2.2절 참조 |

> **핵심 포인트**: Web API로는 프린트를 전송할 수 없습니다. 원격 프린팅은 반드시 Local API(PreFormServer)를 사용해야 합니다.

---

## 2. Formlabs Web API (클라우드 모니터링)

### 2.1 인증 (OAuth 2.0 Client Credentials)

#### API 키 발급
1. https://dashboard.formlabs.com 접속 → 로그인
2. Developer Tools > API Credentials
3. Client ID + Client Secret 발급

#### 토큰 발급
```
POST https://api.formlabs.com/developer/v1/o/token/

Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id={CLIENT_ID}
&client_secret={CLIENT_SECRET}
```

**응답 예시:**
```json
{
    "access_token": "eyJ0eXAiOiJKV1...",
    "expires_in": 86400,
    "token_type": "Bearer",
    "scope": "read"
}
```

- **토큰 유효기간**: 24시간 (86,400초)
- **갱신**: 만료 전에 동일 요청으로 새 토큰 발급
- **헤더**: `Authorization: Bearer {access_token}`

#### 주의사항
- 토큰 만료 시 `401 Unauthorized` 반환 → 재발급 필요
- Rate Limit 초과 시 `429 Too Many Requests` 반환 → 15초 이상 간격 권장
- Beta API이므로 예고 없이 변경될 수 있음 → 에러 핸들링 철저히

### 2.2 주요 엔드포인트

**Base URL**: `https://api.formlabs.com/developer/v1`

#### 프린터 목록 조회
```
GET /printers/

Authorization: Bearer {access_token}
```

**응답 주요 필드:**
```json
{
    "serial": "Form4-CapableGecko",
    "machine_type_id": "FORM-4-0",
    "printer_status": {
        "status": "IDLE",
        "ready_to_print": "READY",
        "build_platform_contents": "EMPTY",
        "current_print_run": null,
        "temperature": {
            "primary": 25.0
        },
        "cartridge": {
            "material": "FLGPGR05",
            "level": 0.1,
            "display_name": ""
        },
        "tank_status": {
            "installed": true
        }
    }
}
```

#### 특정 프린터 조회
```
GET /printers/{serial}/

예: GET /printers/Form4-CapableGecko/
```

#### 프린트 이력 조회
```
GET /prints/

쿼리 파라미터:
- printer: 시리얼 번호로 필터
- status: PRINTING, FINISHED, ERROR 등으로 필터
- limit: 결과 수 제한
- offset: 페이지네이션
```

#### 이벤트 조회
```
GET /events/

쿼리 파라미터:
- printer: 시리얼 번호
- after: ISO 날짜 (이후 이벤트만)
```

### 2.3 프린터 상태값 (PrintStatus)

| 상태 | 설명 |
|------|------|
| `IDLE` | 대기 중 |
| `QUEUED` | 작업 대기 |
| `PRINTING` | 출력 중 |
| `PREHEAT` | 예열 중 |
| `PRECOAT` | 코팅 준비 |
| `POSTCOAT` | 코팅 후처리 |
| `FILLING` | 레진 충전 |
| `FINISHED` | 완료 |
| `ERROR` | 오류 |
| `PAUSING` | 일시정지 중 |
| `PAUSED` | 일시정지됨 |
| `ABORTING` | 중단 중 |
| `WAITING_FOR_RESOLUTION` | 조치 필요 (탱크/mixer 미장착 등) |

### 2.4 프린터 준비 상태

| 필드 | 값 | 의미 |
|------|-----|------|
| `ready_to_print` | `READY` | 출력 가능 |
| `ready_to_print` | `NOT_READY` | 출력 불가 |
| `build_platform_contents` | `EMPTY` | 빌드플레이트 비어있음 |
| `build_platform_contents` | `HAS_PARTS` | 출력물 있음 |
| `build_platform_contents` | `MISSING` | 빌드플레이트 미장착 |
| `build_platform_contents` | `UNCONFIRMED` | 확인 필요 |
| `build_platform_contents` | `CONFIRMED_CLEAR` | 비어있음 확인됨 |

### 2.5 진행 중인 프린트 정보

`printer_status.current_print_run` 필드 (출력 중일 때만 존재):

```json
{
    "status": "PRINTING",
    "currently_printing_layer": 150,
    "layer_count": 500,
    "estimated_duration_ms": 7200000,
    "elapsed_duration_ms": 2160000,
    "estimated_time_remaining_ms": 5040000
}
```

| 필드 | 설명 |
|------|------|
| `currently_printing_layer` | 현재 레이어 (예: 150) |
| `layer_count` | 전체 레이어 수 (예: 500) |
| `estimated_duration_ms` | 전체 예상 시간 (ms) |
| `elapsed_duration_ms` | 경과 시간 (ms) |
| `estimated_time_remaining_ms` | 남은 시간 (ms) |

### 2.6 레진 카트리지 정보

```json
{
    "cartridge": {
        "material": "FLGPGR05",
        "level": 0.1,
        "display_name": ""
    }
}
```

- `level`: 0.0 ~ 1.0 (0% ~ 100%)
- `display_name`이 빈 문자열인 경우가 많음 → `material` 코드로 직접 매핑 필요

#### 레진 코드 → 이름 매핑

| 코드 | 이름 |
|------|------|
| `FLGPGR05` | Grey Resin V5 |
| `FLGPCL05` | Clear Resin V5 |
| `FLGPBK05` | Black Resin V5 |
| `FLGPWH05` | White Resin V5 |
| `FLRGPCL04` | Rigid 4000 V4 |
| `FLRGPWH04` | Rigid 10K V4 |
| `FLFLPGR03` | Flexible 80A V3 |
| `FLELPBK03` | Elastic 50A V3 |
| `FLTOPBK03` | Tough 2000 V3 |
| `FLGPGR04` | Grey Resin V4 |
| `FLGPCL04` | Clear Resin V4 |
| `FLGPBK04` | Black Resin V4 |
| `FLGPWH04` | White Resin V4 |
| `FLDCBL01` | Draft V1 |

> **주의**: Formlabs API의 `display_name`이 빈 값으로 오는 경우가 빈번합니다. 위 매핑 테이블을 코드에 반드시 포함하세요.

### 2.7 알려진 이슈 및 주의사항

| 이슈 | 설명 | 해결 방법 |
|------|------|----------|
| **enum 누락** | API가 새 상태값 반환 시 파싱 에러 | enum을 유연하게 처리 (unknown 허용) |
| **WAITING_FOR_RESOLUTION** | 탱크/mixer 미장착 시 반환 | enum에 반드시 포함 |
| **BUILD_PLATFORM_CONTENTS** | `UNCONFIRMED`, `CONFIRMED_CLEAR` | enum에 반드시 포함 |
| **display_name 빈 값** | 카트리지 이름이 빈 문자열 | material 코드로 직접 매핑 |
| **일시정지/중단 원격 제어** | Web API로 pause/cancel **불가능** | 프린터 터치스크린에서만 가능 |
| **mixer not detected** | 레진 탱크 내부 부품 이슈 | 하드웨어 문제 (탱크 재장착) |
| **Beta API** | 예고 없이 변경 가능 | 에러 핸들링 + 로깅 철저히 |

---

## 3. Formlabs Local API (PreFormServer)

### 3.1 개요

| 항목 | 내용 |
|------|------|
| **역할** | STL 파일 슬라이싱 + 프린터에 작업 전송 |
| **실행 파일** | PreFormServer.exe (Windows/macOS만 지원) |
| **포트** | 44388 (기본) |
| **인증** | 없음 (로컬 실행) |
| **공식 문서** | https://formlabs-dashboard-api-resources.s3.amazonaws.com/formlabs-local-api-latest.html |
| **Python 라이브러리** | https://github.com/Formlabs/formlabs-api-python |

### 3.2 PreFormServer 설치 및 실행

#### 설치
1. https://formlabs.com/software/ 에서 PreForm 다운로드
2. PreForm 설치 후 `PreFormServer.exe`는 설치 경로에 포함됨
3. 또는 별도 PreFormServer 실행 파일 사용

#### 실행
```bash
PreFormServer.exe --port 44388
```

- 표준 출력에 `"READY FOR INPUT"` 메시지 출력 시 API 호출 가능
- **자동 시작 권장**: Windows 시작 프로그램에 등록

#### 핵심 제약
- **PreFormServer는 프린터와 같은 로컬 네트워크에서 실행되어야 합니다**
- Windows/macOS만 지원 (Linux 미지원)
- 원격 서버에서 접근하려면 VPN 또는 터널링 필요

### 3.3 프린터 검색

```
POST http://{PREFORM_HOST}:44388/discover-devices/

Content-Type: application/json

{
    "timeout_seconds": 10
}
```

**응답 예시:**
```json
[
    {
        "connection_type": "WIFI",
        "name": "Form4-CapableGecko",
        "ip": "192.168.219.46",
        "machine_type": "FORM-4-0",
        "status": "online",
        "is_remote_print_enabled": true,
        "firmware_version": "2.4.2",
        "cartridge": {
            "material_code": "FLGPGR05",
            "level_ml": 100,
            "max_fill_ml": 1000
        },
        "tank": {
            "installed": false
        }
    }
]
```

**주요 확인 포인트:**
- `is_remote_print_enabled`: **반드시 `true`**여야 원격 프린트 가능
  - `false`인 경우: 프린터 터치스크린에서 Settings > Remote Print > Enable
- `connection_type`: `WIFI`, `USB`, `ETHERNET`
- `cartridge.material_code`: 장착된 레진 종류
- `tank.installed`: 레진 탱크 장착 여부

### 3.4 프린트 워크플로우

전체 프린트 과정은 아래 순서를 따릅니다:

```
① Scene 생성 → ② STL 임포트 → ③ 자동 방향 설정
→ ④ 자동 서포트 → ⑤ 자동 배치 → ⑥ 프린트 전송
```

#### ① Scene 생성
```
POST http://{PREFORM_HOST}:44388/scene/

{
    "machine_type": "FORM-4-0",
    "material_code": "FLGPGR05",
    "layer_thickness_mm": 0.05,
    "print_setting": "DEFAULT"
}
```

**응답:**
```json
{
    "scene_id": "abc123"
}
```

**레이어 두께 옵션:**
| 값 | 해상도 |
|----|--------|
| `0.025` | 25µm (최고 품질, 가장 느림) |
| `0.05` | 50µm (균형) |
| `0.1` | 100µm (빠른 출력) |

#### ② STL 모델 임포트
```
POST http://{PREFORM_HOST}:44388/scene/{scene_id}/import-model/

{
    "file": "C:\\STL_Files\\model.stl"
}
```

> **중요**: `file` 경로는 **PreFormServer가 실행되는 Windows PC 기준**의 로컬 경로입니다.
> 원격 서버에서 STL을 전송하려면 먼저 Windows PC에 파일을 복사한 뒤, 해당 Windows 경로를 전달해야 합니다.

#### ③ 자동 방향 설정 (Auto Orient)
```
POST http://{PREFORM_HOST}:44388/scene/{scene_id}/auto-orient/
```

#### ④ 자동 서포트 생성 (Auto Support)
```
POST http://{PREFORM_HOST}:44388/scene/{scene_id}/auto-support/
```

#### ⑤ 자동 배치 (Auto Layout)
```
POST http://{PREFORM_HOST}:44388/scene/{scene_id}/auto-layout/
```

#### ⑥ 프린트 전송
```
POST http://{PREFORM_HOST}:44388/scene/{scene_id}/print/

{
    "printer": "Form4-CapableGecko"
}
```

- `printer`: discover에서 확인한 프린터 이름 (예: `"Form4-CapableGecko"`)
- 전송 성공 시 프린터가 자동으로 출력 시작

### 3.5 슬라이스 예측 (프린트 전 확인)

프린트 전송 전에 예상 시간/재료량을 확인할 수 있습니다.

```
POST http://{PREFORM_HOST}:44388/scene/{scene_id}/estimate/
```

**응답 예시:**
```json
{
    "estimated_print_time_ms": 7200000,
    "estimated_material_ml": 45.2,
    "layer_count": 500
}
```

### 3.6 주의사항

| 항목 | 설명 |
|------|------|
| **STL 경로** | PreFormServer 실행 PC의 **Windows 로컬 경로** 사용 (예: `C:\STL_Files\model.stl`) |
| **동시 Scene** | 여러 Scene 동시 생성 가능하나, 프린터별로 1개씩만 전송 |
| **프린터 이름** | discover 응답의 `name` 값 그대로 사용 (예: `"Form4-CapableGecko"`) |
| **Remote Print** | 프린터에서 Remote Print가 비활성화되면 전송 실패 |
| **탱크 미장착** | 레진 탱크가 없으면 프린트 시작 불가 |
| **에러 시 Scene 정리** | 실패한 Scene은 `DELETE /scene/{scene_id}` 로 삭제 권장 |

---

## 4. 프린터 정보

### 4.1 보유 프린터 (4대)

| 이름 | 시리얼 | 모델 | 연결 |
|------|--------|------|------|
| CapableGecko | Form4-CapableGecko | Form 4 | WiFi |
| HeavenlyTuna | Form4-HeavenlyTuna | Form 4 | WiFi |
| CorrectPelican | Form4-CorrectPelican | Form 4 | WiFi |
| ShrewdStork | Form4-ShrewdStork | Form 4 | WiFi |

### 4.2 프린터 사양

| 항목 | 사양 |
|------|------|
| 모델 | Formlabs Form 4 |
| 기술 | mSLA (Masked Stereolithography) |
| 빌드 볼륨 | 200 × 125 × 210 mm (5.25L) |
| XY 해상도 | 50 µm |
| machine_type | `"FORM-4-0"` |
| 연결 | Wi-Fi, USB, Ethernet |

### 4.3 후처리 장비 (API 미지원)

| 장비 | 수량 | API |
|------|------|-----|
| Form Wash (세척기) | 2대 | ❌ 없음 |
| Form Cure (경화기) | 2대 | ❌ 없음 |

> Form Wash / Form Cure는 공식 API가 없습니다. 완료 감지는 별도 방식(카메라 등)으로 구현해야 합니다.

---

## 5. 네트워크 구성

### 5.1 현재 네트워크 구조

```
┌───────────────────────────────────────────────────────┐
│              VPN 네트워크 (WireGuard)                    │
│                                                         │
│  ┌────────────┐           ┌────────────┐               │
│  │  서버 (Linux) │  ◀═VPN═▶ │ 공장 PC     │               │
│  │  FastAPI     │           │ PreFormServer│              │
│  └────────────┘           └────────────┘               │
│                                  │                      │
│                                  │ (WiFi, 로컬 네트워크) │
│                                  ▼                      │
│                        ┌─────────────────┐             │
│                        │ Form 4 프린터 4대 │             │
│                        └─────────────────┘             │
└───────────────────────────────────────────────────────┘
```

### 5.2 네트워크 요건

| 항목 | 요구사항 |
|------|---------|
| **PreFormServer ↔ 프린터** | 같은 로컬 네트워크 (필수) |
| **서버 ↔ PreFormServer** | VPN 또는 같은 네트워크 |
| **서버 ↔ Formlabs Cloud** | 인터넷 접속 가능 |
| **PreFormServer 포트** | 44388 (방화벽 허용 필요) |

### 5.3 VPN 구성 (WireGuard)

현재 WireGuard VPN으로 서버 ↔ 공장 PC 간 통신합니다.

- **VPN 소프트웨어**: WireGuard
- **공장 PC VPN IP**: 별도 공유
- **서버 VPN IP**: 별도 공유
- **포트**: 44388 (PreFormServer), 8089 (파일 수신)

> VPN 설정 상세는 Faridh님과 별도 협의 예정

---

## 6. 개발 시 권장사항

### 6.1 에러 핸들링

```
1. Web API 토큰 만료 (401) → 자동 재발급 로직 구현
2. Rate Limit (429) → 15초 이상 요청 간격 유지
3. PreFormServer 미응답 → 연결 상태 확인 + 재시도
4. 프린터 오프라인 → discover로 상태 재확인
5. enum 파싱 에러 → 알 수 없는 값은 무시하거나 기본값 처리
```

### 6.2 폴링 주기

| 용도 | 권장 주기 |
|------|----------|
| 프린터 상태 모니터링 (Web API) | 15초 이상 |
| 프린트 진행률 확인 (Web API) | 15초 |
| PreFormServer 헬스체크 | 30초 |
| 프린터 검색 (Local API discover) | 수동 또는 5분 |

### 6.3 기술 스택 참고

우리가 사용한 기술 스택입니다 (참고용):

| 분류 | 기술 |
|------|------|
| 백엔드 | Python 3.11, FastAPI, httpx (비동기) |
| DB | SQLite (개발), PostgreSQL (운영 예정) |
| 프론트엔드 | React 18, TypeScript, Vite, Tailwind CSS 4 |
| 실시간 | WebSocket + 15초 폴링 폴백 |
| 인프라 | Docker, WireGuard VPN |

---

## 7. 참고 링크

| 자료 | URL |
|------|-----|
| Formlabs Web API 문서 | https://support.formlabs.com/s/article/Formlabs-Web-API |
| Formlabs Local API 문서 | https://formlabs-dashboard-api-resources.s3.amazonaws.com/formlabs-local-api-latest.html |
| Formlabs Python 라이브러리 | https://github.com/Formlabs/formlabs-api-python |
| PreForm 다운로드 | https://formlabs.com/software/ |
| Formlabs Dashboard | https://dashboard.formlabs.com |

---

## 8. 협업 일정

| 날짜 | 내용 |
|------|------|
| 2026-02-24 | 본 가이드라인 전달 |
| 별도 협의 | Faridh님과 서버 환경 세팅 |
| 2026-03-02 (화) | 공장 방문 현장 협업 (Faridh님 + 정태민 + 한솔코에버) |

---

## 9. 연락처

| 소속 | 이름 | 역할 | 연락처 |
|------|------|------|--------|
| 오리누 | 정태민 | 3D 프린터 시스템 개발 | (별도 공유) |
| 오리누 | Faridh | 서버/인프라 | (별도 공유) |
| 한솔코에버 | 김기원 주임 | 개발 | (별도 공유) |
| 한솔코에버 | 이나라 주임 | 개발 | (별도 공유) |
