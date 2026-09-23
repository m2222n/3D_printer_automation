"""
M2(어댑터) -> M3a(상태 엔진) 이벤트 계약.

이 파일이 유일한 경계입니다.
시뮬레이터, MQTT 어댑터, Modbus 어댑터가 모두 여기 정의된 것만 발행하고,
상태 엔진은 여기 정의된 것만 받습니다.
P3에서 시뮬레이터를 실물로 교체할 때 상태 엔진은 한 줄도 바뀌지 않아야 합니다.

네 가지 이벤트뿐입니다.

  SPAWN  신규 배치 투입          누가: 프린터API(프린터가 받음) / 시뮬  -- 주문은 선택(추후)
  STATE  설비 상태가 바뀜        누가: 카메라·프린터API(추정) -- 위치를 바꾸지 않는다
                                     RUN | DONE | ERROR | HOLD
  MOVED  반송이 끝남            누가: 로봇암·작업자(확정)  -- 위치를 확정한다
  SPLIT  배치가 부품으로 분해     누가: 부품 분리 공정        -- 추적 단위가 바뀐다

캐리어는 이벤트에 없습니다.
  플레이트 = line.plate_count 숫자 (투입 시 상한 검사)
  바구니·박스 = group_id 꼬리표 (Moved.group_id / join_group, Split.group_id)

설계 규칙
  1. STATE 는 unit_id 를 싣지 않는다. 카메라는 제품 ID를 모른다.
     어느 제품인지는 상태 엔진이 node_id 로 조회해서 정한다.
  2. 위치를 바꾸는 것은 MOVED 뿐이다. STATE 는 절대 node_id 를 옮기지 않는다.
     카메라가 오탐해도 제품 위치가 틀어지지 않게 하기 위함이다.
  3. 채번(display_id 갱신)은 MOVED 에서만 일어난다.
     카메라가 "끝난 것 같다"고 할 때 미리 번호를 따면
     반송이 실패했을 때 번호가 새고 순번이 실제 처리 순서와 어긋난다.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional

Source = Literal["CAMERA", "ROBOT", "MANUAL", "ADAPTER", "SIM"]


def now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Spawn:
    """
    신규 출력 배치를 라인에 투입. 보통 프린터 대기 랙.

    배치는 빌드플레이트 위에 실린다. 플레이트는 개수가 정해진 재사용 자산이라
    unit 이 아니라 container 다. 빈 플레이트가 없으면 투입할 수 없다 —
    이것도 정상적인 백프레셔다.

    contents 를 비우면 주문 품목을 그대로 올린다 (주문 하나 = 플레이트 한 장).
    주문이 커져 여러 장으로 나뉘면 그때 장별 수량을 실어 보낸다.

    지금은 배치 -> 유닛만 본다. 주문은 추후 붙인다 (2026-09-22 결정).
      order_id 가 없으면 주문 검사·품목 복사를 건너뛴다.
      contents 도 없으면 내용 미상 배치다 — unit_content 0행. Split 때 확정된다.
      없는 주문을 지어 넣지 않는다.

    cmd_id = 기존 제어 DB 의 print_command.cmd_id. 이 출력이 어느 CMD 소속인가 하는
    꼬리표일 뿐이다 — 누가 옮기나(로봇/사람)와 무관하고, 없으면 NULL.
    """
    node_id: str
    line_id: str
    order_id: Optional[str] = None       # 어느 주문분인가. 한 플레이트에 한 주문만. 없으면 None
    contents: tuple["Content", ...] = ()  # 비우면 주문 품목(order_line)을 그대로 쓴다
    cmd_id: Optional[str] = None         # print_command.cmd_id (B). unit.cmd_id 다리
    source: Source = "SIM"
    ts: datetime = field(default_factory=now)
    kind: str = "SPAWN"


@dataclass(frozen=True)
class State:
    """
    설비 상태 관측. 추정값이므로 confidence 를 함께 싣는다.
    디바운싱은 어댑터 책임 — 여기 도착한 것은 이미 확정된 판정이어야 한다.

    status
      HOLD 는 화면의 [중지] 버튼 때문에 넣은 것이 아니다.
      「모듈 상세 설계」 M2c 프린터 어댑터 상태 매핑이
      PAUSED / PAUSING / ABORTING -> HOLD 를 이미 요구하는데 계약에 그 값이 없었다.
      schema.sql 의 product_state.status 는 처음부터 HOLD 를 허용한다 —
      빠진 곳은 이 계약 한 곳뿐이었다.

      🔴 HOLD 는 개체 하나의 상태다. 기존 cell_state.paused(셀 전체 운전 모드)와
         층이 다르므로 합치지 않는다. 셀을 세우는 것과 이 설비의 개체가 멈춘 것은 다른 사실이다.
      🔴 물리적으로 설비를 멈추는 것은 이 계약 밖이다. HOLD 는 기록일 뿐
         어댑터에게 정지를 지시하지 않는다.

    duration_s
      이번 가동을 얼마나 돌릴지. 작업별 지시값이고 노드의 표준 주기가 아니다.
      기존이 같은 것을 print_command.washing_time / curing_time (초, 작업자 입력)으로
      풀었고, washing.py:57 / curing.py:132 가 실제로 그 값대로 돈다.
      node.std_cycle_s 는 표준이고 이 값은 배치마다 다르게 준다.
      없으면 상태 엔진이 std_cycle_s 를 쓴다.
    """
    node_id: str
    status: Literal["RUN", "DONE", "ERROR", "HOLD"]
    source: Source = "SIM"
    confidence: Optional[float] = None
    duration_s: Optional[int] = None     # RUN 일 때만 의미가 있다
    ts: datetime = field(default_factory=now)
    kind: str = "STATE"


@dataclass(frozen=True)
class Moved:
    """
    반송 완료. 물리적 사실이므로 이것만이 위치를 확정한다.
    unit_id 와 slot_no 는 반송 지시(M3b)가 발행할 때 실려 나갔다가 그대로 돌아온다.

    slot_no
      목적지가 랙일 때 어느 칸에 넣었는지. M3b 가 지시에 실은 값이 그대로 온다.
      비어 있으면 M3a 가 next_place() 로 계산한다 — 시뮬레이터와,
      로봇이 스스로 자리를 고르는 경우를 위한 경로다.

      칸 안의 위치(pos_no)는 싣지 않는다. FIFO/LIFO 랙은 밀어 넣으면
      물리적으로 뒤에 붙으므로 순번이 자명하고, 로봇에게 알려줄 필요도 없다.

    unit_id / group_id
      둘 중 정확히 하나만 싣는다.
        unit_id      개체 하나가 움직인다 (플레이트, 또는 바구니에서 꺼낸 부품)
        group_id     바구니째 움직인다. 안에 든 부품 전부가 함께 이동한다
      경화는 바구니 단위, 치수검사는 부품 단위라 두 경로가 모두 필요하다.
      부품이 개별로 움직이면 바구니에서 빠진 것으로 본다.
    """
    unit_id: Optional[str] = None
    group_id: Optional[str] = None       # 묶음째 이동 (바구니·트레이)
    join_group: Optional[str] = None     # 개별 이동인데 도착지에서 묶음에 합류 (OK 박스 적재)
    from_node: str = ""
    to_node: str = ""
    transporter_id: str = ""
    slot_no: Optional[int] = None
    source: Source = "SIM"
    ts: datetime = field(default_factory=now)
    kind: str = "MOVED"


@dataclass(frozen=True)
class Content:
    part_no: str
    qty: int


@dataclass(frozen=True)
class SplitOutput:
    part_no: str
    qty: int


@dataclass(frozen=True)
class Split:
    """
    배치가 개별 부품으로 분해됨. `splits_batch: true` 인 노드에서 일어난다
    (현재 라인에서는 SEP-01 부품 분리대. 서포트 제거 SUP-01 은 그 다음 별개 노드다).

    이 시점부터 추적 단위가 BATCH 에서 PART 로 바뀐다.
    부모 배치는 소비되고, 부품마다 unit 행이 하나씩 생긴다.
    부품의 display_id 는 부모 이름을 이어받는다 — 'P3-W2' -> 'P3-W2-S15'.
    parent_unit_id 로 어느 주문의 어느 배치에서 나왔는지까지 거슬러 올라간다.

    outputs 를 싣는 이유는 실제로 나온 수량이 적재 수량과 다를 수 있기 때문이다.
    (분해 중 파손, 이미 걸러진 불량 등)

    작업자가 플레이트에서 출력물을 떼어낸다. 떼어낸 부품은 group_id 꼬리표로 묶여
    다음 노드(서포트 제거)로 함께 넘어간다.

    부모 배치는 소비되고(consumed_at), 그 자리가 비면서 플레이트 한 장이
    자동으로 반납된 셈이 된다 — 플레이트는 line.plate_count 숫자라 복귀 처리가 없다.
    """
    unit_id: str
    node_id: str
    outputs: tuple[SplitOutput, ...]
    group_id: Optional[str] = None        # 부품 묶음 꼬리표 (바구니). 없으면 자동
    source: Source = "SIM"
    ts: datetime = field(default_factory=now)
    kind: str = "SPLIT"


Event = Spawn | State | Moved | Split


# ------------------------------------------------------------------
# 직렬화 — MQTT 페이로드도 이 형태를 씁니다.
# ------------------------------------------------------------------

def to_dict(e: Event) -> dict:
    d = {k: v for k, v in e.__dict__.items()}
    d["ts"] = e.ts.isoformat()
    return d


def from_dict(d: dict) -> Event:
    d = dict(d)
    kind = d.pop("kind")
    if isinstance(d.get("ts"), str):
        d["ts"] = datetime.fromisoformat(d["ts"])
    return {"SPAWN": Spawn, "STATE": State, "MOVED": Moved,
            "SPLIT": Split}[kind](**d)
