# Phase 2: Local API 아키텍처 설계

## 개요

### 목적
- STL 파일을 원격으로 업로드하고 프린터에 작업 전송
- 부품별 최적 세팅 저장 및 재사용
- 프린트 큐 관리

### 핵심 제약
- **PreFormServer**가 프린터와 **같은 네트워크**에서 실행되어야 함
- PreFormServer는 **Windows/macOS만 지원** (Linux 미지원)
- 6000 서버(Linux)에서 직접 실행 불가 → 별도 PC 필요

---

## 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           사용자 (웹 브라우저)                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      6000 서버 (Linux)                                   │
│                      106.244.6.242:8085                                  │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    FastAPI Backend                               │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │    │
│  │  │  Web API    │  │  Local API  │  │   Print Job Manager     │  │    │
│  │  │  (모니터링)  │  │  (프록시)   │  │   (큐 관리, 세팅 저장)   │  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
          │                         │
          │ (인터넷)                 │ (내부망/VPN)
          ▼                         ▼
┌──────────────────┐      ┌──────────────────────────────────────────────┐
│  Formlabs Cloud  │      │            공장 Windows PC                    │
│  (api.formlabs)  │      │  ┌────────────────────────────────────────┐  │
└──────────────────┘      │  │         PreFormServer                  │  │
                          │  │         localhost:44388                │  │
                          │  └────────────────────────────────────────┘  │
                          └──────────────────────────────────────────────┘
                                              │
                                              │ (로컬 네트워크)
                                              ▼
                          ┌──────────────────────────────────────────────┐
                          │              Form 4 프린터 (4대)              │
                          │  CapableGecko, HeavenlyTuna,                 │
                          │  CorrectPelican, ShrewdStork                 │
                          └──────────────────────────────────────────────┘
```

---

## 핵심 구성 요소

### 1. 공장 Windows PC (PreFormServer 호스트)

| 항목 | 내용 |
|------|------|
| 역할 | PreFormServer 상시 실행 |
| OS | Windows 10/11 |
| 포트 | 44388 (기본) |
| 요구사항 | 프린터와 같은 네트워크, 고정 IP 권장 |

**실행 명령:**
```bash
PreFormServer.exe --port 44388
```

**준비 완료 확인:**
- 표준 출력에 `"READY FOR INPUT"` 메시지 출력 시 API 호출 가능

---

### 2. 6000 서버 (Local API 프록시)

6000 서버에서 PreFormServer로 API 요청을 중계

**구조:**
```
사용자 → 6000 서버 API → PreFormServer (Windows PC) → 프린터
```

**환경 변수 추가:**
```bash
# .env
PREFORM_SERVER_HOST=192.168.x.x  # 공장 Windows PC IP
PREFORM_SERVER_PORT=44388
```

---

## API 설계

### 새로운 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| `POST` | `/api/v1/local/discover` | 네트워크 프린터 검색 |
| `POST` | `/api/v1/local/upload` | STL 파일 업로드 |
| `POST` | `/api/v1/local/prepare` | 자동 준비 (방향, 서포트, 배치) |
| `POST` | `/api/v1/local/print` | 프린터로 작업 전송 |
| `GET` | `/api/v1/local/presets` | 저장된 프리셋 목록 |
| `POST` | `/api/v1/local/presets` | 프리셋 저장 |
| `GET` | `/api/v1/local/queue` | 프린트 큐 조회 |

---

## 프린트 워크플로우

### 기본 흐름

```
1. STL 업로드
      │
      ▼
2. 씬(Scene) 생성
   - machine_type: "FORM-4-0"
   - material_code: 레진 종류
      │
      ▼
3. 모델 임포트
   - POST /scene/{id}/import-model/
      │
      ▼
4. 자동 처리
   - auto-orient (방향 최적화)
   - auto-support (서포트 생성)
   - auto-layout (빌드 플레이트 배치)
      │
      ▼
5. 검증
   - 출력 가능 여부 확인
      │
      ▼
6. 프린터 선택 & 전송
   - POST /print/
      │
      ▼
7. 모니터링 (Phase 1 Web API)
```

### API 호출 예시

```python
# 1. 씬 생성
scene = POST /scene/
{
    "machine_type": "FORM-4-0",
    "material_code": "FLGPGR05"  # Grey Resin V5
}

# 2. STL 임포트
POST /scene/{scene_id}/import-model/
{
    "file": "path/to/model.stl"
}

# 3. 자동 준비
POST /scene/{scene_id}/auto-orient/
POST /scene/{scene_id}/auto-support/
POST /scene/{scene_id}/auto-layout/

# 4. 프린트 전송
POST /print/
{
    "scene_id": scene_id,
    "printer": "Form4-CapableGecko"
}
```

---

## 부품 프리셋 관리

### 대표님 요구사항
> "A 부품 최적 세팅 → 내보내기 → 반복 사용"

### 프리셋 구조

```json
{
    "preset_id": "uuid",
    "name": "점자프린터_커버_A",
    "part_type": "cover_a",
    "created_at": "2026-02-02T10:00:00",
    "settings": {
        "machine_type": "FORM-4-0",
        "material_code": "FLGPGR05",
        "layer_thickness_mm": 0.05,
        "orientation": {
            "x_rotation": 45,
            "y_rotation": 0,
            "z_rotation": 0
        },
        "support_density": "normal",
        "support_touchpoint_size": 0.5
    },
    "stl_file": "models/cover_a.stl"  # 선택적
}
```

### 프리셋 API

```
GET  /api/v1/local/presets              # 목록 조회
GET  /api/v1/local/presets/{id}         # 상세 조회
POST /api/v1/local/presets              # 새 프리셋 저장
PUT  /api/v1/local/presets/{id}         # 수정
DELETE /api/v1/local/presets/{id}       # 삭제
POST /api/v1/local/presets/{id}/print   # 프리셋으로 바로 출력
```

---

## 네트워크 구성 옵션

### 옵션 A: 직접 연결 (권장)

6000 서버와 공장 PC가 같은 내부망에 있는 경우:

```
6000 서버 (192.168.100.29) ──────► Windows PC (192.168.x.x:44388)
```

**장점:** 단순, 빠름
**조건:** 방화벽에서 44388 포트 허용 필요

### 옵션 B: VPN 연결

6000 서버가 외부에 있는 경우:

```
6000 서버 ──► VPN ──► 공장 네트워크 ──► Windows PC
```

**장점:** 보안
**단점:** 설정 복잡, 지연 발생 가능

### 옵션 C: 터널링 (ngrok 등)

Windows PC에서 외부로 터널 생성:

```
Windows PC ──► ngrok ──► 6000 서버
```

**장점:** 방화벽 설정 불필요
**단점:** 외부 서비스 의존, 보안 우려

---

## 구현 순서

### Step 1: 환경 확인
- [ ] 공장 Windows PC IP 확인
- [ ] 6000 서버 → Windows PC 통신 테스트
- [ ] PreFormServer 설치

### Step 2: PreFormServer 연동
- [ ] PreFormServer 자동 시작 설정
- [ ] 기본 API 연동 (discover, scene 생성)
- [ ] 에러 핸들링

### Step 3: 핵심 기능 구현
- [ ] STL 업로드 API
- [ ] 자동 준비 (orient, support, layout)
- [ ] 프린트 전송

### Step 4: 프리셋 관리
- [ ] 프리셋 저장/불러오기
- [ ] 프리셋 기반 빠른 출력

### Step 5: 프론트엔드
- [ ] 업로드 UI
- [ ] 프리셋 관리 UI
- [ ] 프린터 선택 UI

---

## 확인 필요 사항

| 항목 | 담당 | 상태 |
|------|------|------|
| 공장 Windows PC IP | 태민 | ❓ |
| 6000 서버 ↔ 공장 PC 통신 가능 여부 | 파리드/태민 | ❓ |
| PreFormServer 설치 | 태민 (공장 방문) | ❓ |
| 레진 종류 (material_code) | 공장 확인 | ❓ |

---

## 참고 자료

- [Formlabs Local API 문서](https://formlabs-dashboard-api-resources.s3.amazonaws.com/formlabs-local-api-latest.html)
- [Formlabs Python Library](https://github.com/Formlabs/formlabs-api-python)
- [PreForm 다운로드](https://formlabs.com/software/)

---

## 작성 정보

- **작성일**: 2026-02-02
- **작성자**: 정태민
- **상태**: 설계 완료, 환경 확인 후 구현 예정
