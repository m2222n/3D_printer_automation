# Sequence Service

Standalone sequence runner service (separate from FastAPI web-api).

## Features
- Single controller thread (`SequenceThread`)
- Inheritance-based sequences (`SequenceBase`)
- Dataclass runtime context (`JobCtx`, `RuntimeCtx`)
- MySQL-backed job status transitions
- DB update on every step transition

## Structure
- `app/cell/runtime.py`: controller thread + sequence list (`mainSequence.py` 가 시퀀스 인스턴스 목록)
- `app/cell/sequences/printer.py` · `washing.py` · `curing.py` · `inprocess.py`: 설비별 단계
- `app/cell/sequences/robot.py`: 로봇 작업 큐·우선순위·Modbus 명령값/파라미터 (`_modbus_command_value` · `_modbus_params`)
- `app/cell/modbus_protocol.py`: 8단계 핸드셰이크 (`ModbusHandshakeClient`)
- `app/cell/line_events.py`: 라인 MES(PG) 로 State/Moved 발행 — 실패해도 제어를 막지 않는다
- `app/cell/repository.py`: claim/update DB operations
- `app/main.py`: service entrypoint

## Run
```bash
cd sequence_service
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app/main.py
```

## Environment (.env)
```env
MYSQL_DSN=mysql+pymysql://user:password@127.0.0.1:3306/automation
SERVICE_ID=sequence-main
TICK_SECONDS=0.1
PRINT_SIM_SECONDS=30
CURE_SIM_SECONDS=120
DEFAULT_WASH_MINUTES=6
ENABLE_CELL_STATE=true
```

## 로봇암A 이송 명령표

PC → 로봇 Modbus TCP(HCR-12A · 레지스터 = `app/core/config.py:35~47`). 펜던트 프로그램(한솔)과 이 표가 같아야 한다.
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

대기랙·거치대·완료랙이 들어오면 아래가 필요하다. 값은 한솔과 합의 뒤 여기와 `config.py` 를 같이 고친다.

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
