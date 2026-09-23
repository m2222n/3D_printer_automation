"""
v2 쓰기 API — W1~W6. 요청 → line_mes.contract 이벤트 → StateEngine.handle(). 엔진 ValueError = 409.

  W1 POST /units/{unit_id}/split    Split (+ part_scrap)   🚨 내용 미상 배치는 outputs+scraps 로 unit_content 먼저
  W2 POST /moves                    Moved
  W3 POST /nodes/{node_id}/state    State
  W4 POST /judgements               judgement (+ Moved →EXIT-SCRAP)  한 트랜잭션
  W5 POST /commands                 command_log (+ group_close)
  W6 POST /transporters/{tid}/commands/{cid}   command_log(DEVICE) · verified=false → 409 · 송신 어댑터는 미연결(ok=false)

product_state 를 직접 UPDATE 하는 경로는 0건이다 (명세 §5).
"""
from fastapi import APIRouter

router = APIRouter(tags=["LineMES v2 · write"])
