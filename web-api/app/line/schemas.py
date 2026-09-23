"""
v2 응답·요청 모델. 정본 = frontend/src/types/line.ts — 필드 이름·타입을 그대로 옮긴다(계획 §5 어긋남 8곳 주의).

여기 채우는 순서 = 라우트를 붙이는 순서(R4 → R2 R1 R3 R5 R11 → R6~R10 R12 → W3 W2 W1 W4 W5 → W6).
공통은 WriteResult 하나뿐이라 먼저 둔다.
"""
from typing import Optional

from pydantic import BaseModel


class WriteResult(BaseModel):
    """쓰기 API 공통 응답 (명세 §1-3). 엔진 거부는 여기가 아니라 409 다."""
    ok: bool
    event_ids: list[int] = []
    unit_ids: list[str] = []
    group_id: Optional[str] = None
    message: str = ""
    warnings: list[str] = []
