# Phase 4: OpenMV 세척기/경화기 완료 감지 시스템 개발설계서

## 작성 정보

| 항목 | 내용 |
|------|------|
| 작성일 | 2026-03-09 |
| 작성자 | 정태민 |
| 상태 | 설계 완료, 구현 예정 |
| 선행 문서 | 리서치문서5 (YOLO), 리서치문서6 (OpenMV), OpenMV 리서치 보고 요약 |

---

## 1. 프로젝트 개요

### 1.1 목적

Form Wash(세척기)와 Form Cure(경화기)는 공식 API를 제공하지 않는다.
OpenMV AE3 카메라를 각 장비 전면에 설치하여, 카메라 내부 AI가 작업 상태를 판단하고
서버에 완료 신호를 자동 전송한다. 이 신호를 받아 HCR 로봇이 다음 공정으로 자동 진행한다.

### 1.2 대표님 지시사항

| 일자 | 지시 내용 |
|------|---------|
| 2026.02.04 | 세척기/경화기 완료 감지 기능 개발 |
| 2026.02.06 | OpenMV 카메라 내부에서 판단 -> 자동 신호 전송 방식 확정 |
| 2026.02.06 | SaaS 플랫폼 구축 지시 (추후 외부 고객에게 서비스 판매) |
| 2026.02.26 | Phase 전환 지시: 인수인계 완료 후 OpenMV 개발 착수 |

### 1.3 16단계 공정 중 적용 위치

```
... -> (5) 빌드플레이트 픽업 -> (6) 세척기 투입
                                       |
                                       v
                              [OpenMV #1, #2 감지]  <-- *** 여기 ***
                                       |
                                (7) 세척 완료 신호
                                       |
                                       v
                              (8) 경화기 투입
                                       |
                                       v
                              [OpenMV #3, #4 감지]  <-- *** 여기 ***
                                       |
                                (9) 경화 완료 신호
                                       |
                                       v
                              (10) 경화기에서 픽업 -> ...
```

### 1.4 범위 (Scope)

**포함:**
- OpenMV 카메라 -> MQTT -> FastAPI 서버 파이프라인
- 카메라 상태 관리 API (REST + WebSocket)
- 세척기/경화기 모니터링 프론트엔드 UI
- MQTT 시뮬레이터 (카메라 없이 테스트 가능)
- OpenMV 카메라 MicroPython 스크립트

**제외 (별도 Phase 또는 한솔코에버 담당):**
- YOLO 부품 식별/불량 검출 (Intel RealSense) -- 한솔코에버 이나라 주임 진행 중
- HCR 로봇 연동 (Modbus TCP) -- Phase 3, 한솔코에버 김기원 주임 진행 중
- Edge Impulse 모델 학습 -- 공장 이미지 데이터 수집 후 진행

---

## 2. 시스템 아키텍처

### 2.1 전체 구조

```
+----------------------------------------------------------------------+
|                          공장 현장                                      |
|                                                                      |
|  [OpenMV #1] --+                                                     |
|  (세척기 1)     |                                                     |
|                |                                                     |
|  [OpenMV #2] --+-- WiFi --> [Mosquitto MQTT] --> [FastAPI Server]    |
|  (세척기 2)     |            (공장 PC or 서버)     (6000 서버)          |
|                |                    |                   |            |
|  [OpenMV #3] --+                    |                   v            |
|  (경화기 1)     |              MQTT Subscribe      [WebSocket]        |
|                |                                        |            |
|  [OpenMV #4] --+                                        v            |
|  (경화기 2)                                     [프론트엔드 UI]        |
|                                                                      |
+----------------------------------------------------------------------+
                                                          |
                                                          v
                                                  [HCR 로봇 트리거]
                                                  (Phase 3, 추후)
```

### 2.2 통신 흐름 (시퀀스)

```
OpenMV Camera          Mosquitto           FastAPI Server        Frontend
     |                     |                     |                   |
     |-- WiFi connect ---->|                     |                   |
     |                     |                     |                   |
     |  [AI 추론: wash_running]                  |                   |
     |-- MQTT publish ---->|                     |                   |
     |  topic: factory/wash/1/status             |                   |
     |  payload: {...}     |                     |                   |
     |                     |-- deliver --------->|                   |
     |                     |                     |-- WebSocket ------>|
     |                     |                     |   (실시간 상태)     |
     |                     |                     |                   |
     |  [AI 추론: wash_complete]                 |                   |
     |-- MQTT publish ---->|                     |                   |
     |                     |-- deliver --------->|                   |
     |                     |                     |-- DB 저장          |
     |                     |                     |-- 알림 생성        |
     |                     |                     |-- WebSocket ------>|
     |                     |                     |                   |
     |                     |                     |-- 로봇 트리거 -->  |
     |                     |                     |   (Phase 3, 추후)  |
```

### 2.3 비판적 분석: 왜 MQTT인가

| 대안 | 장점 | 단점 | 판정 |
|------|------|------|------|
| **MQTT (선택)** | 경량, QoS 지원, 자동 재연결(umqtt.robust), pub/sub 패턴 | 브로커 추가 필요 | 적합 |
| HTTP POST | 단순, 브로커 불필요 | OpenMV에서 이미지 전송 제한(~20KB), 연결 오버헤드, resp.close() 필수 | 부적합 |
| UART -> RPi | 안정성 최고, 버퍼링 가능 | Raspberry Pi 추가 비용, 복잡도 증가 | 운영 단계 고려 |
| WebSocket 직접 | 양방향 통신 | OpenMV MicroPython에서 WebSocket 클라이언트 불안정 | 부적합 |

**결론:** 프로토타입은 MQTT, 운영 환경 안정성 이슈 발생 시 UART -> RPi 전환 고려.

---

## 3. MQTT 설계

### 3.1 토픽 구조

```
factory/                          # 최상위
  wash/                           # 세척기
    {device_id}/                  # 장비 번호 (1, 2)
      status                      # 현재 상태
      heartbeat                   # 카메라 생존 신호
  cure/                           # 경화기
    {device_id}/                  # 장비 번호 (1, 2)
      status                      # 현재 상태
      heartbeat                   # 카메라 생존 신호
  camera/                         # 카메라 관리
    {camera_id}/                  # 카메라 ID (wash_1, wash_2, cure_1, cure_2)
      info                        # 카메라 메타정보 (부팅 시 1회)
```

### 3.2 메시지 포맷

**상태 메시지 (status):**
```json
{
  "camera_id": "wash_1",
  "device_type": "wash",
  "device_id": 1,
  "status": "wash_complete",
  "confidence": 0.94,
  "timestamp": "2026-03-09T14:30:00+09:00",
  "consecutive_count": 5,
  "fps": 15.2,
  "mem_free": 52000
}
```

**하트비트 메시지 (heartbeat):**
```json
{
  "camera_id": "wash_1",
  "uptime_s": 3600,
  "mem_free": 52000,
  "temperature_c": 45.2,
  "wifi_rssi": -65,
  "timestamp": "2026-03-09T14:30:00+09:00"
}
```

**카메라 정보 (info, 부팅 시 1회):**
```json
{
  "camera_id": "wash_1",
  "firmware_version": "4.8.1",
  "model_name": "wash_classifier_v1.tflite",
  "model_classes": ["wash_running", "wash_complete"],
  "ip_address": "192.168.219.100"
}
```

### 3.3 상태 값 정의

| 장비 | 상태 | 값 | 감지 특징 |
|------|------|-----|---------|
| 세척기 | 유휴 | `wash_idle` | 바스켓 없음, 장비 정지 |
| 세척기 | 세척 중 | `wash_running` | 바스켓 회전 중, IPA 표면 움직임 |
| 세척기 | 세척 완료 | `wash_complete` | 바스켓 정지, 표면 안정 |
| 경화기 | 유휴 | `cure_idle` | UV LED 꺼짐, 회전판 없음 |
| 경화기 | 경화 중 | `cure_running` | UV LED 발광 (파란 빛), 회전판 회전 |
| 경화기 | 경화 완료 | `cure_complete` | UV LED 꺼짐, 회전판 정지 |
| 공통 | 오프라인 | `offline` | 서버 측 판단 (하트비트 타임아웃) |
| 공통 | 에러 | `error` | 카메라 측 예외 발생 |

### 3.4 상태 전환 안정성 (Debounce)

AI 추론은 프레임마다 결과가 흔들릴 수 있다. 오탐 방지를 위해:

- **연속 N프레임 동일 결과** 시에만 상태 전환 (기본값: `N=5`)
- **최소 confidence 임계값** (기본값: `0.7`)
- **상태 전환 시에만 MQTT publish** (매 프레임 전송하지 않음)
- **하트비트는 30초 주기**로 별도 전송

```
프레임 1: wash_running (0.85) -- count=1
프레임 2: wash_running (0.82) -- count=2
프레임 3: wash_complete (0.55) -- count 리셋 (confidence 미달)
프레임 4: wash_running (0.90) -- count=1
프레임 5: wash_running (0.88) -- count=2
...
프레임 9: wash_running (0.91) -- count=5 --> MQTT publish!
```

### 3.5 QoS 설정

| 메시지 | QoS | 이유 |
|--------|-----|------|
| status | 1 | 상태 변경은 반드시 전달되어야 함 |
| heartbeat | 0 | 누락되어도 다음 주기에 전송됨 |
| info | 1 | 카메라 등록 정보는 반드시 전달 |

---

## 4. 서버 API 설계

### 4.1 새로운 엔드포인트

기존 `web-api/app/` 구조에 `vision/` 모듈을 추가한다.

| Method | Endpoint | 설명 |
|--------|----------|------|
| `GET` | `/api/v1/vision/health` | Vision 모듈 상태 (MQTT 연결 등) |
| `GET` | `/api/v1/vision/cameras` | 등록된 카메라 목록 + 현재 상태 |
| `GET` | `/api/v1/vision/cameras/{camera_id}` | 특정 카메라 상세 |
| `GET` | `/api/v1/vision/devices` | 세척기/경화기 장비 상태 목록 |
| `GET` | `/api/v1/vision/devices/{type}/{id}` | 특정 장비 상세 (예: wash/1) |
| `GET` | `/api/v1/vision/events` | 상태 변경 이벤트 이력 (필터: 기간, 장비, 상태) |
| `GET` | `/api/v1/vision/events/latest` | 최근 이벤트 N건 |
| `POST` | `/api/v1/vision/simulate` | 시뮬레이터: 가짜 상태 변경 전송 (개발용) |
| `WS` | `/api/v1/vision/ws` | WebSocket 실시간 상태 스트림 |

### 4.2 응답 스키마

**카메라 목록 (GET /cameras):**
```json
{
  "cameras": [
    {
      "camera_id": "wash_1",
      "device_type": "wash",
      "device_id": 1,
      "status": "wash_running",
      "confidence": 0.92,
      "is_online": true,
      "last_seen": "2026-03-09T14:30:00+09:00",
      "uptime_s": 3600,
      "firmware_version": "4.8.1",
      "wifi_rssi": -65
    }
  ],
  "total": 4,
  "online": 3,
  "offline": 1
}
```

**장비 상태 (GET /devices):**
```json
{
  "devices": [
    {
      "type": "wash",
      "id": 1,
      "name": "세척기 1호",
      "status": "wash_running",
      "camera_id": "wash_1",
      "is_online": true,
      "last_status_change": "2026-03-09T14:25:00+09:00",
      "elapsed_since_change_s": 300
    }
  ]
}
```

**이벤트 이력 (GET /events):**
```json
{
  "events": [
    {
      "id": "uuid",
      "camera_id": "wash_1",
      "device_type": "wash",
      "device_id": 1,
      "previous_status": "wash_running",
      "new_status": "wash_complete",
      "confidence": 0.94,
      "timestamp": "2026-03-09T14:30:00+09:00"
    }
  ],
  "total": 150,
  "page": 1,
  "page_size": 50
}
```

### 4.3 WebSocket 메시지

```json
{
  "type": "vision_status_change",
  "data": {
    "camera_id": "wash_1",
    "device_type": "wash",
    "device_id": 1,
    "status": "wash_complete",
    "confidence": 0.94,
    "timestamp": "2026-03-09T14:30:00+09:00"
  }
}
```

---

## 5. 데이터베이스 설계

기존 SQLite + SQLAlchemy 구조를 그대로 사용한다.

### 5.1 새 테이블

**vision_cameras (카메라 등록 정보):**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| camera_id | String(20), PK | wash_1, wash_2, cure_1, cure_2 |
| device_type | String(10) | wash / cure |
| device_id | Integer | 1 / 2 |
| name | String(50) | 표시 이름 (세척기 1호) |
| status | String(20) | 현재 상태 |
| confidence | Float | 마지막 추론 confidence |
| is_online | Integer | 0/1 |
| firmware_version | String(20) | 펌웨어 버전 |
| model_name | String(100) | 배포된 모델명 |
| ip_address | String(15) | 카메라 IP |
| wifi_rssi | Integer | WiFi 신호 강도 |
| last_seen | DateTime | 마지막 하트비트 시각 |
| last_status_change | DateTime | 마지막 상태 변경 시각 |
| created_at | DateTime | 등록 시각 |

**vision_events (상태 변경 이력):**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | String(36), PK | UUID |
| camera_id | String(20), FK, INDEX | 카메라 ID |
| device_type | String(10), INDEX | wash / cure |
| device_id | Integer | 장비 번호 |
| previous_status | String(20) | 이전 상태 |
| new_status | String(20) | 새 상태 |
| confidence | Float | 추론 confidence |
| created_at | DateTime, INDEX | 이벤트 시각 |

---

## 6. 프로젝트 구조 (추가 파일)

```
web-api/app/
  vision/                           # Phase 4: 비전 모듈 (신규)
    __init__.py
    routes.py                       # REST API + WebSocket 라우터
    schemas.py                      # Pydantic 요청/응답 스키마
    models.py                       # SQLAlchemy 모델 (vision_cameras, vision_events)
    mqtt_client.py                  # MQTT 구독 클라이언트 (aiomqtt)
    camera_manager.py               # 카메라 상태 관리 (온라인/오프라인 판단, 이벤트 생성)
    simulator.py                    # MQTT 시뮬레이터 (개발/테스트용)

OpenMV/
  scripts/                          # OpenMV 카메라용 MicroPython 스크립트 (신규)
    wash_detector.py                # 세척기 감지 스크립트
    cure_detector.py                # 경화기 감지 스크립트
    config.py                       # WiFi/MQTT 설정
    boot.py                         # 부팅 시 자동 실행

frontend/src/components/
  VisionPage.tsx                    # 세척기/경화기 모니터링 탭 (신규)
```

---

## 7. OpenMV 카메라 스크립트 설계

### 7.1 구조

```python
# wash_detector.py (개략 설계)

# 1. 초기화
#    - CSI 카메라 초기화 (csi 모듈, v4.8.1+)
#    - WiFi 연결
#    - MQTT 연결 (umqtt.robust)
#    - TFLite 모델 로드
#    - Watchdog Timer 설정

# 2. 메인 루프
#    - 이미지 캡처
#    - AI 추론 (Classification)
#    - Debounce 처리 (연속 N프레임)
#    - 상태 변경 시에만 MQTT publish
#    - 주기적 하트비트 전송
#    - Watchdog feed
#    - 메모리 관리 (gc.collect)
```

### 7.2 핵심 설계 결정

**sensor 모듈 vs CSI 모듈:**
- yolov8.py: `import sensor` (구 방식)
- blazeface_face_detector.py: `import csi` (신 방식, v4.8.1+)
- **결정: CSI 모듈 사용** (sensor는 deprecated)

**Classification vs FOMO (Object Detection):**
- 세척기/경화기 완료 감지는 "장면 전체가 어떤 상태인가" 판단
- 특정 객체 위치가 필요하지 않음
- **결정: Classification** (wash_running vs wash_complete 이진 분류)

**모델 학습 플랫폼:**
- Edge Impulse (OpenMV 1등급 공식 지원)
- 배포: OpenMV Library (.zip) -> .tflite + labels.txt
- 입력: 96x96 RGB (Edge Impulse 기본값)
- 양자화: int8 (OpenMV 필수)

### 7.3 24/7 운영 안정성

| 항목 | 구현 |
|------|------|
| Watchdog | `machine.WDT(timeout=10000)` - 10초 내 무응답 시 자동 리셋 |
| WiFi 재연결 | `umqtt.robust` 자동 재연결 + 수동 WiFi reconnect 로직 |
| 메모리 관리 | `gc.collect()` 매 추론 후 호출, `gc.mem_free()` 모니터링 |
| 에러 핸들링 | try/except로 메인 루프 감싸기, 에러 시 MQTT error 상태 전송 후 리셋 |
| 하트비트 | 30초 주기, 서버에서 60초 타임아웃 시 offline 판정 |

---

## 8. Mosquitto MQTT 브로커 설정

### 8.1 설치 (Docker, 6000 서버)

docker-compose.yml에 추가:

```yaml
mosquitto:
  image: eclipse-mosquitto:2
  container_name: formlabs-mosquitto
  restart: unless-stopped
  ports:
    - "1883:1883"    # MQTT
    - "9001:9001"    # WebSocket (선택)
  volumes:
    - ./mosquitto/config:/mosquitto/config
    - ./mosquitto/data:/mosquitto/data
    - ./mosquitto/log:/mosquitto/log
```

### 8.2 설정 파일

```
# mosquitto/config/mosquitto.conf
listener 1883
allow_anonymous true      # 프로토타입 단계, 운영 시 인증 추가

persistence true
persistence_location /mosquitto/data/

log_dest file /mosquitto/log/mosquitto.log
log_type all
```

### 8.3 보안 (운영 단계)

프로토타입에서는 `allow_anonymous true`로 시작하되, 운영 전환 시:
- 사용자/비밀번호 인증 추가
- TLS 적용 (공장 내부망이라 우선순위 낮음)
- ACL로 토픽별 접근 제어

---

## 9. 서버 MQTT 클라이언트 설계

### 9.1 라이브러리 선택

| 라이브러리 | 비고 |
|-----------|------|
| **aiomqtt** (선택) | asyncio 네이티브, FastAPI와 자연스러운 통합 |
| paho-mqtt | 동기식, 별도 스레드 필요 |
| fastapi-mqtt | aiomqtt 래퍼, 의존성 추가 |

### 9.2 구독 토픽

```python
SUBSCRIBE_TOPICS = [
    "factory/wash/+/status",      # 세척기 상태
    "factory/wash/+/heartbeat",   # 세척기 하트비트
    "factory/cure/+/status",      # 경화기 상태
    "factory/cure/+/heartbeat",   # 경화기 하트비트
    "factory/camera/+/info",      # 카메라 정보
]
```

### 9.3 메시지 처리 흐름

```
MQTT 메시지 수신
    |
    v
토픽 파싱 (device_type, device_id, message_type)
    |
    +-- status --> camera_manager.update_status()
    |                  |
    |                  +-- 상태 변경 시 --> DB 이벤트 저장
    |                  +-- 상태 변경 시 --> WebSocket broadcast
    |                  +-- 상태 변경 시 --> 알림 생성
    |
    +-- heartbeat --> camera_manager.update_heartbeat()
    |                  |
    |                  +-- last_seen 갱신
    |                  +-- 오프라인 카메라 온라인 전환
    |
    +-- info --> camera_manager.register_camera()
                   |
                   +-- 카메라 정보 DB 저장/업데이트
```

---

## 10. 프론트엔드 UI 설계

### 10.1 새 탭: 세척/경화 모니터링

기존 5탭 네비게이션에 추가하거나, 대시보드 내에 섹션으로 통합.

**UI 구성:**
- 장비 4대 카드 (세척기 1, 2 + 경화기 1, 2)
- 각 카드: 장비 이름, 현재 상태 (아이콘 + 텍스트 + 색상), 카메라 온/오프라인
- 상태 변경 시 시각적 알림 (색상 변환, 애니메이션)
- 하단: 최근 이벤트 이력 테이블

**상태별 색상:**
| 상태 | 색상 | 아이콘 |
|------|------|--------|
| idle | 회색 | 정지 |
| running | 파랑 (세척) / 보라 (경화) | 회전 애니메이션 |
| complete | 초록 | 체크 |
| offline | 빨강 | 경고 |
| error | 주황 | 느낌표 |

### 10.2 데이터 흐름

```
REST GET /vision/devices  -->  초기 로드
WebSocket /vision/ws      -->  실시간 업데이트
```

---

## 11. MQTT 시뮬레이터 설계

카메라와 공장 이미지 없이도 전체 파이프라인을 테스트할 수 있도록 한다.

### 11.1 기능

- CLI 또는 API 호출로 가짜 MQTT 메시지 발행
- 시나리오 모드: 세척 시작 -> 5분 후 완료 등 자동 시퀀스
- 개발/데모 시 활용

### 11.2 시뮬레이터 API

```
POST /api/v1/vision/simulate
{
  "camera_id": "wash_1",
  "status": "wash_complete",
  "confidence": 0.95
}
```

### 11.3 시나리오 모드

```
POST /api/v1/vision/simulate/scenario
{
  "scenario": "full_cycle",    // 세척 시작 -> 완료 -> 경화 시작 -> 완료
  "interval_seconds": 10       // 각 단계 간격
}
```

---

## 12. 비판적 분석: 리스크와 대응

### 12.1 기술 리스크

| 리스크 | 영향 | 확률 | 대응 |
|--------|------|------|------|
| 공장 WiFi 불안정 | 카메라 -> 서버 통신 끊김 | 높음 (이미 VPN 이슈 경험) | umqtt.robust 자동 재연결 + Watchdog 리셋 + 하트비트로 감지 |
| AI 모델 정확도 부족 | 오탐/미탐으로 잘못된 로봇 트리거 | 중간 | Debounce (연속 5프레임), confidence 임계값, 수동 확인 UI |
| OpenMV AE3 발열 | 장시간 운영 시 성능 저하/오류 | 중간 | 하트비트에 온도 포함, 환기 케이스, 필요시 딥슬립 주기 |
| MQTT 브로커 다운 | 전체 감지 시스템 중단 | 낮음 | Docker restart policy, 서버 헬스체크 |
| 모델 학습 데이터 부족 | 다양한 조건에서 일반화 실패 | 높음 | 최소 상태별 100장, 다양한 조명/각도, 데이터 증강 |

### 12.2 아직 모르는 것 (Unknown Unknowns)

1. **세척기/경화기의 시각적 특징이 실제로 얼마나 명확한지** -- 리서치에서 "바스켓 회전", "UV LED 발광"이라고 했지만, 실제 카메라 앵글에서 확실히 구분 가능한지는 공장 방문 후 확인 필요
2. **공장 조명 환경** -- 낮/밤, 자연광/인공광 차이가 모델 정확도에 미치는 영향
3. **카메라 설치 위치/각도** -- 최적 위치를 아직 모름, 현장에서 결정 필요
4. **세척기 idle vs complete 구분** -- 둘 다 "정지 상태"인데 시각적으로 구분 가능한지
5. **OpenMV AE3 WiFi 내장 여부** -- 리서치에서 WiFi/BT 내장이라고 했으나 실제 카메라에서 확인 필요

### 12.3 의존성

| 항목 | 의존 대상 | 상태 |
|------|---------|------|
| Edge Impulse 모델 | 공장 이미지 데이터 (최소 400장) | 미수집 |
| 카메라 WiFi 연결 | 공장 WiFi 네트워크 | 미테스트 |
| HCR 로봇 트리거 | Phase 3 완료 (한솔코에버) | 진행 중 |
| 운영 서버 | 카카오 클라우드 이전 | 미정 |

---

## 13. 구현 순서

### Step 1: 인프라 구축 (서버)
- [ ] Mosquitto MQTT 브로커 Docker 설치
- [ ] aiomqtt 의존성 추가
- [ ] FastAPI vision 모듈 기본 구조 생성
- [ ] DB 모델 생성 (vision_cameras, vision_events)

### Step 2: MQTT 연동 + API
- [ ] MQTT 클라이언트 (구독, 메시지 파싱)
- [ ] camera_manager (상태 관리, 온/오프라인 판단)
- [ ] REST API 엔드포인트 구현
- [ ] WebSocket 실시간 푸시

### Step 3: 시뮬레이터
- [ ] MQTT 시뮬레이터 (가짜 카메라 메시지 발행)
- [ ] 시나리오 모드 (full_cycle)
- [ ] E2E 테스트 (시뮬레이터 -> MQTT -> 서버 -> WebSocket)

### Step 4: 프론트엔드
- [ ] VisionPage.tsx (장비 카드 4개 + 이벤트 이력)
- [ ] WebSocket 연동
- [ ] 기존 App.tsx에 탭 추가

### Step 5: OpenMV 카메라 스크립트
- [ ] Mac에 OpenMV IDE 설치 + AE3 연결 테스트
- [ ] 카메라 기본 동작 확인 (예제 실행)
- [ ] WiFi + MQTT 통신 스크립트 작성
- [ ] Classification 추론 + Debounce 로직

### Step 6: 데이터 수집 + 모델 학습 (공장 방문 필요)
- [ ] 세척기/경화기 상태별 이미지 촬영 (최소 상태별 100장)
- [ ] Edge Impulse 프로젝트 생성 + 데이터 업로드
- [ ] Classification 모델 학습
- [ ] .tflite 배포 + OpenMV 스크립트에 모델 적용

### Step 7: 통합 테스트 (공장 현장)
- [ ] 카메라 설치 + 실제 환경 테스트
- [ ] 정확도 검증 + 파라미터 튜닝
- [ ] 24/7 안정성 테스트

---

## 14. 환경 변수 추가 (.env)

```bash
# Phase 4: Vision (MQTT)
MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883
MQTT_TOPIC_PREFIX=factory

# 카메라 오프라인 판정 (초)
CAMERA_HEARTBEAT_TIMEOUT=60

# 시뮬레이터 활성화 (개발용)
VISION_SIMULATOR_ENABLED=true
```

---

## 15. 참고 자료

- [OpenMV 공식 문서](https://docs.openmv.io/)
- [Edge Impulse OpenMV 튜토리얼](https://docs.edgeimpulse.com/docs/edge-ai-hardware/mcu/openmv-cam-h7-plus)
- [aiomqtt (Python async MQTT)](https://github.com/sbtinstruments/aiomqtt)
- [Eclipse Mosquitto](https://mosquitto.org/)
- 리서치문서5_YOLO_커스텀학습_리서치.pdf
- 리서치문서6_OpenMV카메라_리서치.pdf
- OpenMV_리서치_보고_요약.pdf

---

## 작성 정보

- **작성일**: 2026-03-09
- **작성자**: 정태민
- **상태**: 설계 완료, Step 1부터 구현 시작 예정
