# 2-0. 한눈에

| 모듈 | 기존 파일 | 실제 수정 | 기존 로직 침범 |
| --- | --- | --- | --- |
| **M2a** MQTT | `web-api/app/vision/schemas.py:38` | 타입 넓히기 **1줄**  • 어댑터 신규 | 🟢 없음 |
| **M2b** Modbus | `sequence_service/app/cell/sequences/robot.py:204` | 발행 **1줄** | 🟡 **블로킹 주의 — 2-2** |
| **M3b** 반송 | 같은 파일 같은 줄 | **M2b 와 동일 작업** (별건 아님) | 🟢 ①~⑦ 무변경 |
| **M5a** Repeat | — | **0건** | 🟢 Grafana 는 뷰만 읽는다 |
| **M5b** 라인 개요 | — | **0건** (10/31 이후) | 🟢 |

---

# 2-1. M2a — 기존 `except Exception` 을 믿으면 안 된다

**수정** = `vision/schemas.py:38` `timestamp: str` → `float | str`. 타입을 **넓히는** 것이라 기존 str 입력도 그대로 통과한다 — 하위 호환이다.

<aside>
🚨

**발행 코드를 `mqtt_client.py:86-88` 의 `except Exception` 안에 넣지 않는다.**

그 블록이 지금 `ValidationError` 를 삼켜 **실물 메시지를 전건 버리고 있고**(vision 미가동의 원인), 같은 자리에 발행을 넣으면 **새 버그도 똑같이 조용히 사라진다.** 발행은 블록 바깥에 자체 try 로.

</aside>

<aside>
🚨

**`wash_1 → WSH-01` 은 개명이 아니라 매핑표다.**

네 문자열이 네 곳에 박혀 있다 — `camera_manager.py:30-33` · `simulator.py:19-24` · `schemas.py:133` · `routes.py:117`(`f"{device_type}_{device_id}"` 로 키 재조립).

**하나라도 개명하면 네 곳이 동시에 깨진다.** 매핑은 새 어댑터 안에만 둔다.

</aside>

---

# 2-2. 🚨 M2b — 진짜 위험은 "발행 실패" 가 아니라 "블로킹" 이다

계획서는 `try/except` 로 감싸라고만 한다. 그런데 `robot.py:402-631` 은 **논블로킹 스텝머신**이고, 여기서 psycopg `connect`/`INSERT` 를 하면 **예외가 안 나도 루프가 그만큼 멈춘다.** 로봇이 느려진다.

```
_complete_task  →  queue.Queue.put_nowait(Moved(...))      ← 논블로킹. 이것도 try/except
                   데몬 스레드가 소비해서 DB 에 쓴다        ← 여기서 죽어도 로봇은 안 멈춘다
```

큐가 차면 **버린다** — 관측이기 때문이다.

⭐ 이 한 가지가 *"관측이 제어를 막지 않는다"* 를 실제로 보장하는 부분이다. `try/except` 만으로는 예외는 막아도 지연은 못 막는다.

레지스터 맵(`sequence_service/app/core/config.py:36-42`)은 **읽기만** 한다. 제어 변경 0.

---

# 2-3. M3b — P4 에서는 M2b 와 같은 작업이다

별도 모듈 작업처럼 보이지만 **P4 범위에서는 같은 파일 같은 한 줄**이다. 후보 산출 ①~④ · 자원 배정 ⑤~⑦ 은 **무변경**.

**P5(10/31 이후)에만** 아래가 이관 대상이 된다.

| 대상 | 지금 하는 일 |
| --- | --- |
| `robot.py:72 _select_executable_task()` | ①~④ |
| `robot.py:101/104/116 _find_free_*()` | ④ 자리 확인 |
| `robot.py:86 _priority()` | ⑦ 우선순위 |
| `mainSequence.py:20-33` | 설비 개수를 인스턴스 생성으로 고정 (경화기 2호기는 주석 처리) |
| `enums.py:19-28 PostProcStage` | 공정 순서를 IntEnum 으로 고정 |

🔴 **지금 하면 안 되는 이유** = 로봇암은 한 대인데 판단하는 코드가 두 벌이 된다. 둘이 같은 순간 다른 결론을 내고 둘 다 레지스터 `130` 에 쓴다.

📌 마이그레이션 시 `PostProcStage` **값을 `step_order` 로 쓰면 안 된다** — 세척→경화에서 `60 → 10` 으로 역행한다. 순서는 `route` 의 MAIN 엣지로 잡는다.

---

# 2-4. 🔴 M5a · M5b 를 "기존 코드 수정" 으로 잡은 것은 과하다

|  | 보는 것 |
| --- | --- |
| 기존 `monitoring` 탭 | **프린터 대수**의 상태 |
| 신규 대시보드 | **제품 개체**의 라인 통과 현황 |

**대상이 다르므로 `frontend/` 는 변경 0건이다.**

실제로 UI 를 건드리는 모듈은 **M2m(수동 조작)** 이고, 그것도 `wireframe/` 이라는 **별도 Vite 앱**이라 지금은 역시 변경 0건이다. 프론트와 합칠지는 **M5a 가 실물 데이터로 검증된 뒤**에 정한다.

---

# 확인 방법

```bash
# M2a 선행 버그
grep -n "timestamp" web-api/app/vision/schemas.py              # :38 str
grep -n "except Exception" web-api/app/vision/mqtt_client.py   # :86-88

# M2b 발행 지점
grep -n "_complete_task\|STEP0070" sequence_service/app/cell/sequences/robot.py
```