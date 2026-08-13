"""
빈피킹 Pydantic 스키마
=====================
수신(ingest) / 조회 응답 모델

🚨 **수신 스키마는 `bin_picking/src/communication/web_reporter.py`의
   `build_bin_picking_payload()` 출력과 1:1로 맞춰야 한다.**
   키 이름을 추측해서 지으면 조용히 None이 들어간다 — 8/7에 `valid_pct`로
   추측해서 실제 `valid_ratio_pct`와 어긋났고, verdict·note는 정상이라
   **유효율만 None으로 나가는 것을 못 봤다.**
   ⭐ 그래서 이 파일의 필드명은 전부 그 모듈의 출력을 열어서 베꼈다.

⭐ 모르는 필드는 거부하지 않는다(`extra="ignore"`).
   모듈이 먼저 배포되고 서버가 나중에 갈 수도 있으므로, 필드가 늘었다고
   수신을 깨뜨리면 **보고 경로가 제어 경로처럼 굴게 된다**(설계원칙 1 위반).
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime


# ===== 수신 (모듈 → 서버) =====

class SceneGateIn(BaseModel):
    """게이트 판정. ⭐ 미실행은 `not_checked`이고 그것을 그대로 보존한다."""
    model_config = ConfigDict(extra="ignore")

    verdict: str = "not_checked"
    trusted: Optional[bool] = None
    valid_ratio_pct: Optional[float] = None
    note: Optional[str] = None
    n_dropped_by_size_gate: int = 0


class DetectionIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    angle: Optional[float] = None
    label: Optional[str] = None
    confidence: Optional[float] = None
    gripper_width_mm: Optional[float] = None


class SummaryIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    n_detections: int = 0
    n_unique_labels: int = 0
    recognition_track: Optional[str] = None
    latency_ms: Optional[float] = None


class BinPickReportIn(BaseModel):
    """빈피킹 인식 결과 1장면.

    ⚠️ `summary.n_detections`와 `len(detections)`가 어긋날 수 있다(모듈 버그·전송
       잘림). 라우터가 **detections 실제 길이를 신뢰**하고 불일치를 경고로 남긴다.
    """
    model_config = ConfigDict(extra="ignore")

    schema_version: str
    module: str = "bin_picking"
    scene_id: Optional[str] = None
    timestamp: Optional[str] = None
    summary: SummaryIn = Field(default_factory=SummaryIn)
    scene_gate: SceneGateIn = Field(default_factory=SceneGateIn)
    detections: list[DetectionIn] = Field(default_factory=list)


class BinPickIngestResponse(BaseModel):
    """수신 결과. ⭐ 불일치가 있으면 받아들이고 `warnings`로 알린다."""
    scene_pk: str
    scene_id: Optional[str] = None
    n_detections_stored: int
    gate_verdict: str
    warnings: list[str] = Field(default_factory=list)


# ===== 조회 (서버 → 웹) =====

class DetectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    idx: int
    label: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    angle: Optional[float] = None
    confidence: Optional[float] = None
    gripper_width_mm: Optional[float] = None


class SceneGateResponse(BaseModel):
    verdict: str
    trusted: Optional[bool] = None
    valid_ratio_pct: Optional[float] = None
    note: Optional[str] = None
    n_dropped_by_size_gate: int = 0


class SceneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scene_pk: str
    scene_id: Optional[str] = None
    schema_version: str
    module: str
    n_detections: int
    n_unique_labels: int
    recognition_track: Optional[str] = None
    latency_ms: Optional[float] = None
    scene_gate: SceneGateResponse
    reported_at: Optional[str] = None
    received_at: Optional[datetime] = None


class SceneDetailResponse(SceneResponse):
    detections: list[DetectionResponse] = Field(default_factory=list)


class SceneListResponse(BaseModel):
    scenes: list[SceneResponse]
    total: int
    page: int
    page_size: int


class BinPickHealthResponse(BaseModel):
    """빈피킹 수신 경로 상태.

    ⭐ `scenes_untrusted`를 같이 낸다 — 게이트가 걸러낸 장면이 쌓이고 있으면
       촬영 조건이 어긋났다는 뜻이고, 그것이 c2·c3에서 실제로 일어난 일이다.
    """
    status: str
    scenes_total: int
    scenes_last_24h: int
    scenes_untrusted: int
    last_scene_at: Optional[datetime] = None
