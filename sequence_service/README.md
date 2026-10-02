# Sequence Service

제어 층 — 프린터 출력 지시 · 로봇 반송 · 셀 상태. FastAPI web-api 와 별도 프로세스이며 **로봇에 쓰는 유일한 자리**다.
리포 루트 `python main.py` 가 web-api 와 함께 띄운다(공장 PC 는 NSSM 서비스). Windows 전용(Ajin AXL.dll).

## Features
- 단일 컨트롤러 스레드 (`SequenceThread`) · 상속 기반 시퀀스 (`SequenceBase`)
- Dataclass 런타임 컨텍스트 (`JobCtx` · `RuntimeCtx`)
- MariaDB `automation` 에 작업 상태 전이를 매 단계 기록 (`print_command` · `cell_state` · `automation_log`)
- 로봇 Modbus TCP 8단계 핸드셰이크 (아래 명령표)
- 프린터 출력은 web-api `/api/v1/local/print` 를 호출해 건다 (loopback 인증 면제)
- 라인 MES(PostgreSQL) 로 `State(DONE)` · `Moved` 발행 — **논블로킹, 실패해도 제어를 막지 않는다**

## Structure
```
app/
├── main.py                      # 진입점
├── core/config.py               # 설정 (pydantic-settings) — .env + ../web-api/.env 공유
├── cell/
│   ├── runtime.py               # 컨트롤러 스레드 + 시퀀스 목록 (mainSequence.py 가 인스턴스 목록)
│   ├── sequence.py · ctx.py · enums.py
│   ├── sequences/
│   │   ├── printer.py           # 출력 지시 → 상태 폴링 → PRINT_FINISHED (라인 MES State DONE 발행)
│   │   ├── washing.py · curing.py · inprocess.py
│   │   └── robot.py             # 로봇 작업 큐·우선순위·Modbus 명령값/파라미터 (_complete_task 가 Moved 발행)
│   ├── modbus_protocol.py       # ModbusHandshakeClient — 8단계 핸드셰이크
│   ├── tcp_protocol.py          # 로봇/비전 TCP 수동 송신
│   ├── printer_interface.py     # web-api 호출 (출력 걸기 · 상태 조회)
│   ├── line_events.py           # 라인 MES 발행 한 줄 (printer_done · robot_moved) — LINE_DSN 비면 no-op
│   └── repository.py            # claim/update DB 연산
├── db/                          # SQLAlchemy 모델 · 세션 (MariaDB)
└── io/                          # Ajin IO (AXL.dll · Windows) — AJIN_SIMULATION=true 면 더미
```

## Run
```bash
cd sequence_service
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt     # 또는 리포 루트 requirements.txt (line_mes 포함)
python app/main.py
```

## Environment (.env)

`sequence_service/.env` 와 `../web-api/.env` 를 **둘 다** 읽는다(앞이 우선). 프린터 시리얼 · `LINE_DSN` 은 web-api 쪽 한 곳에만 둔다.

```env
MYSQL_DSN=mysql+pymysql://user:password@127.0.0.1:3306/automation
SERVICE_ID=sequence-main
SIMUL_MODE=false                 # true 면 장비 없이 시퀀스만 돈다 (웹 자동화 탭에서 토글 가능)
TICK_SECONDS=0.1
PRINT_SIM_SECONDS=15
CURE_SIM_SECONDS=120
DEFAULT_WASHING_TIME=360
DEFAULT_CURING_TIME=120
ENABLE_CELL_STATE=true

ENABLE_TCP_IO=true               # 로봇 Modbus
ROBOT_TCP_HOST=<robot_ip>
ROBOT_TCP_PORT=9100
AJIN_SIMULATION=true             # 실 DIO 는 false + AXL.dll
PRINTER_SERVER_SIMUL=true        # 실 출력은 false (web-api 경유)
WEB_API_BASE_URL=http://127.0.0.1:8085

# web-api/.env 에서 공유되는 값 (여기 다시 쓰지 않는다)
# PRINTER_SERIAL_MAP={"1":"SERIAL1",...}   프린터 번호 ↔ 시리얼. 비어 있으면 'printer serial not configured' 로 크게 실패
# LINE_DSN=                                  라인 MES. 비면 발행 전부 no-op
```

Modbus 레지스터 번호 · 명령값 · 시뮬 타이밍의 기본값은 `app/core/config.py` 에 있다.

## 로봇암A 이송 명령표

PC → 로봇 Modbus TCP(HCR-12A · 레지스터 = `app/core/config.py:35~47`). 펜던트 프로그램(협력사)과 이 표가 같아야 한다.
빈피킹 좌표는 이 표를 쓰지 않는다(펜던트 script + 소켓).

### 레지스터

| 주소 | 방향 | 뜻 |
|---|---|---|
| 130 | PC→로봇 | 명령값 (아래 표) · 정지 리셋 시 100 |
| 131~135 | PC→로봇 | 파라미터 5개 (명령마다 배치 다름) |
| 150 | PC→로봇 | 송신 트리거 |
| 151 | PC→로봇 | PC Ready |
| 200 | 로봇→PC | Robot Ready |
| 206 | 로봇→PC | Robot Moved(완료) |

순서 = PC Ready(151) → 명령·파라미터 기록 → 송신(150) → Robot Ready(200) 대기 → 완료(206) 대기. 로봇이 동작 중이면 130 을 다시 쓰지 않는다.

### 명령값 (현행 · 코드와 일치)

| 작업 | 130 | 131 | 132 | 133 | 134 | 135 |
|---|---|---|---|---|---|---|
| P / SW 프린터→세척기 | 0 | printer_id | wash_id | 0 | 0 | 0 |
| FW 세척기→(프린터 되주차)→경화기 | 1 | wash_id | parking_printer_id | cure_id | wait_minutes | 0 |
| FC 경화기→반출 | 2 | cure_id | 0 | 0 | 0 | 0 |

### 미정 (레이아웃 재배치 후 · 10월)

대기랙·거치대·완료랙이 들어오면 아래가 필요하다. 값은 협력사와 합의 뒤 여기와 `config.py` 를 같이 고친다.

| 단위 동작 | 130 | 파라미터 | 비고 |
|---|---|---|---|
| 대기랙 칸에서 플레이트 빼기 | 미정 | rack_id · slot_no | 대기랙은 빼기만 |
| 프린터 커버 열기 / 닫기 / 버튼 | 미정 | printer_id | 커버·버튼을 별도 명령으로 둘지 P 에 포함할지 미정 |
| 프린터 플레이트 넣기 / 빼기 | 미정 | printer_id | |
| 거치대 넣기 / 빼기 | 미정 | cradle_id | 거치대는 랙이 아님 |
| 세척기 플레이트 넣기 / 빼기 / 버튼 | 미정 | wash_id | 뚜껑은 열어 둔 상태 유지 |
| 완료랙 칸에 넣기 | 미정 | rack_id · slot_no | 완료랙은 넣기만 |
| 주행(서보) 정지 위치 | 별도 모듈 | rail 좌표 | 서보 드라이버 미정 · 주행 중 130 금지 |

랙·칸의 Modbus 인코딩(한 레지스터에 rack_id·slot_no 를 어떻게 넣나)과 로봇 티칭이 칸 단위인지는 합의 항목.

---

_Last updated: 2026-10-02_
