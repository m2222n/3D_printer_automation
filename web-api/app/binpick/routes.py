"""
빈피킹 REST API + WebSocket 라우터
==================================
/api/v1/binpick/* 엔드포인트  (2026-08-13 신설)

⭐ 왜 이 라우터가 필요한가
------------------------
8/5 회의로 사업 산출물이 **모듈 3개 + "그 결과를 우리 웹에 던져주는 것까지"** 로
정의됐다. 모듈 쪽(`bin_picking/src/communication/web_reporter.py`)은 8/7에
만들었으나 **받는 쪽이 없어서** 기본 transport가 파일 출력이었다.
이 라우터가 그 수신구이고, 생겼으므로 모듈은 `http_transport`로 갈아끼우면 된다.

## 인증 — 별도 토큰을 만들지 않는다
`app/core/jwt_middleware.py:109-113`이 **loopback(127.0.0.1/::1) 요청을 인증
면제**한다. 빈피킹 모듈은 IPC-510 위에서 같은 호스트의 web-api로 POST하므로
그 면제에 그대로 해당한다. ⭐ 5/29에 sequence_service가 같은 이유로 401을 받아
CMD 픽업이 실패한 회귀가 있었고, 그때 넣은 면제가 여기서도 맞는 답이다.
🚨 원격 호스트에서 넣게 되는 날엔 JWT를 붙여야 한다(`http_transport(token=...)`가
이미 Bearer를 지원한다) — 지금 없는 인증을 미리 짜두지 않는다.

## 설계 원칙 (모듈 쪽과 대칭)
🚨 **1. 수신은 너그럽게, 저장은 정확하게.** 모듈이 필드를 더 보내도 거부하지
   않는다(`extra="ignore"`). 웹이 까다로워서 인식이 멈추면 보고 경로가 제어
   경로처럼 구는 것이다.
⭐ **2. 불일치를 조용히 넘기지 않는다.** `summary.n_detections`와 실제
   `len(detections)`가 다르면 **받아들이고 `warnings`에 실어 돌려준다.**
   거부하면 데이터를 잃고, 조용히 넘기면 8/7 분모 버그처럼 그럴싸한 값이 굳는다.
⭐ **3. 게이트 판정은 1급 컬럼으로 저장하고 조회 필터를 준다.** 판정 없이
   검출 수만 보이면 c3(배경을 부품으로 잡은 장면)가 정상처럼 보인다.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from app.local.database import get_local_db_session
from app.binpick.models import BinPickScene, BinPickDetection
from app.binpick.schemas import (
    BinPickHealthResponse,
    BinPickIngestResponse,
    BinPickReportIn,
    DetectionResponse,
    SceneDetailResponse,
    SceneGateResponse,
    SceneListResponse,
    SceneResponse,
)

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

router = APIRouter(prefix="/binpick", tags=["BinPicking"])

# 게이트가 "믿을 만하다"고 판정하지 않은 장면을 세는 기준.
# ⭐ not_checked는 실패가 아니지만 통과도 아니다 — 별도로 센다.
_UNTRUSTED_VERDICTS = ("out_of_distribution", "rejected", "untrusted")


# ── WebSocket 브로드캐스트 ────────────────────────────────────────────────
# vision 모듈(`camera_manager.register_ws`)과 같은 큐 방식을 쓴다.

_ws_clients: list[asyncio.Queue] = []


def register_ws(queue: asyncio.Queue) -> None:
    _ws_clients.append(queue)


def unregister_ws(queue: asyncio.Queue) -> None:
    if queue in _ws_clients:
        _ws_clients.remove(queue)


async def _broadcast_ws(message: dict) -> None:
    """구독자에게 장면 도착을 알린다.

    🚨 큐가 꽉 차면 버린다(vision과 동일) — 화면 갱신이 밀린다고 수신을
       막으면 안 된다.
    """
    for q in list(_ws_clients):
        try:
            q.put_nowait(message)
        except asyncio.QueueFull:
            pass


def _gate_of(scene: BinPickScene) -> SceneGateResponse:
    return SceneGateResponse(
        verdict=scene.gate_verdict,
        trusted=scene.gate_trusted,
        valid_ratio_pct=scene.gate_valid_ratio_pct,
        note=scene.gate_note,
        n_dropped_by_size_gate=scene.gate_n_dropped_by_size or 0,
    )


def _scene_response(scene: BinPickScene) -> SceneResponse:
    return SceneResponse(
        scene_pk=scene.id,
        scene_id=scene.scene_id,
        schema_version=scene.schema_version,
        module=scene.module,
        n_detections=scene.n_detections,
        n_unique_labels=scene.n_unique_labels,
        recognition_track=scene.recognition_track,
        latency_ms=scene.latency_ms,
        scene_gate=_gate_of(scene),
        reported_at=scene.reported_at,
        received_at=scene.created_at,
    )


# ===== 수신 (모듈 → 서버) =====

@router.post("/reports", response_model=BinPickIngestResponse, status_code=201)
async def ingest_report(report: BinPickReportIn):
    """빈피킹 인식 결과 1장면을 받는다.

    ⭐ 모듈 쪽 호출:
        from src.communication.web_reporter import WebReporter, http_transport
        reporter = WebReporter(http_transport(
            "http://127.0.0.1:8085/api/v1/binpick/reports"))
        reporter.report_bin_picking(six, latency_ms=...)
    """
    warnings: list[str] = []

    # ⭐ 실제 길이를 신뢰한다. summary는 모듈이 계산한 값이라 어긋날 수 있다.
    n_actual = len(report.detections)
    if report.summary.n_detections != n_actual:
        msg = (f"summary.n_detections={report.summary.n_detections}인데 "
               f"detections 길이는 {n_actual} — 실제 길이를 저장한다")
        warnings.append(msg)
        logger.warning("빈피킹 수신 불일치 (scene=%s): %s", report.scene_id, msg)

    # 라벨 종류 수도 실제로 센다(같은 이유).
    labels = [d.label for d in report.detections if d.label]
    n_unique_actual = len(set(labels))
    if report.summary.n_unique_labels != n_unique_actual:
        warnings.append(
            f"summary.n_unique_labels={report.summary.n_unique_labels}인데 "
            f"실제 고유 라벨은 {n_unique_actual}")

    gate = report.scene_gate
    if gate.verdict == "not_checked":
        # 🚨 실패는 아니지만 "판정 통과"로 읽혀선 안 된다.
        warnings.append("게이트 미실행(not_checked) — 이 장면은 신뢰도 판정이 없다")

    with get_local_db_session() as db:
        scene = BinPickScene(
            scene_id=report.scene_id,
            schema_version=report.schema_version,
            module=report.module,
            n_detections=n_actual,
            n_unique_labels=n_unique_actual,
            recognition_track=report.summary.recognition_track,
            latency_ms=report.summary.latency_ms,
            gate_verdict=gate.verdict,
            gate_trusted=gate.trusted,
            gate_valid_ratio_pct=gate.valid_ratio_pct,
            gate_note=gate.note,
            gate_n_dropped_by_size=gate.n_dropped_by_size_gate or 0,
            reported_at=report.timestamp,
        )
        db.add(scene)
        db.flush()  # scene.id 확보

        for i, d in enumerate(report.detections):
            db.add(BinPickDetection(
                scene_pk=scene.id,
                idx=i,
                label=d.label,
                x=d.x, y=d.y, z=d.z,
                angle=d.angle,
                confidence=d.confidence,
                gripper_width_mm=d.gripper_width_mm,
            ))

        scene_pk = scene.id
        scene_id = scene.scene_id
        verdict = scene.gate_verdict
        latency = scene.latency_ms

    logger.info("빈피킹 장면 수신 (scene=%s, n=%d, gate=%s)",
                scene_id, n_actual, verdict)

    await _broadcast_ws({
        "type": "binpick_scene",
        "scene_pk": scene_pk,
        "scene_id": scene_id,
        "n_detections": n_actual,
        "gate_verdict": verdict,
        "latency_ms": latency,
        "received_at": datetime.now(KST).isoformat(),
    })

    return BinPickIngestResponse(
        scene_pk=scene_pk,
        scene_id=scene_id,
        n_detections_stored=n_actual,
        gate_verdict=verdict,
        warnings=warnings,
    )


# ===== 조회 (서버 → 웹) =====

@router.get("/health", response_model=BinPickHealthResponse)
async def binpick_health():
    """수신 경로 상태 + ⭐게이트가 못 믿겠다고 한 장면 수"""
    with get_local_db_session() as db:
        total = db.query(BinPickScene).count()
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        last_24h = db.query(BinPickScene).filter(
            BinPickScene.created_at >= since).count()
        untrusted = db.query(BinPickScene).filter(
            BinPickScene.gate_verdict.in_(_UNTRUSTED_VERDICTS)).count()
        latest = (db.query(BinPickScene)
                  .order_by(BinPickScene.created_at.desc()).first())
        last_at = latest.created_at if latest else None

    return BinPickHealthResponse(
        status="healthy",
        scenes_total=total,
        scenes_last_24h=last_24h,
        scenes_untrusted=untrusted,
        last_scene_at=last_at,
    )


@router.get("/scenes", response_model=SceneListResponse)
async def list_scenes(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    gate_verdict: Optional[str] = Query(default=None,
                                        description="게이트 판정으로 필터"),
    trusted_only: bool = Query(default=False,
                               description="게이트가 신뢰한 장면만"),
    label: Optional[str] = Query(default=None,
                                 description="이 라벨이 검출된 장면만"),
):
    """인식 장면 목록 (최신순)"""
    with get_local_db_session() as db:
        query = db.query(BinPickScene)

        if gate_verdict:
            query = query.filter(BinPickScene.gate_verdict == gate_verdict)
        if trusted_only:
            query = query.filter(BinPickScene.gate_trusted.is_(True))
        if label:
            # 해당 라벨을 가진 검출이 있는 장면만
            sub = (db.query(BinPickDetection.scene_pk)
                   .filter(BinPickDetection.label == label).subquery())
            query = query.filter(BinPickScene.id.in_(sub))

        total = query.count()
        scenes = (query
                  .order_by(BinPickScene.created_at.desc())
                  .offset((page - 1) * page_size)
                  .limit(page_size)
                  .all())

        return SceneListResponse(
            scenes=[_scene_response(s) for s in scenes],
            total=total,
            page=page,
            page_size=page_size,
        )


@router.get("/scenes/latest", response_model=Optional[SceneDetailResponse])
async def latest_scene():
    """가장 최근 장면 1건 + 검출 전체.

    ⭐ 운영 화면의 기본 뷰 — "지금 뭘 보고 있나".
    ⚠️ 한 건도 없으면 `null`을 준다(404가 아니다 — 아직 안 온 것은 오류가 아니다).
    """
    with get_local_db_session() as db:
        scene = (db.query(BinPickScene)
                 .order_by(BinPickScene.created_at.desc()).first())
        if not scene:
            return None
        dets = (db.query(BinPickDetection)
                .filter(BinPickDetection.scene_pk == scene.id)
                .order_by(BinPickDetection.idx).all())
        base = _scene_response(scene)
        return SceneDetailResponse(
            **base.model_dump(),
            detections=[DetectionResponse.model_validate(d) for d in dets],
        )


@router.get("/scenes/{scene_pk}", response_model=SceneDetailResponse)
async def get_scene(scene_pk: str):
    """장면 상세 + 검출 전체 (idx 순 = grasp_plan 인덱스와 대응)"""
    with get_local_db_session() as db:
        scene = db.query(BinPickScene).filter(
            BinPickScene.id == scene_pk).first()
        if not scene:
            raise HTTPException(status_code=404,
                                detail=f"장면 '{scene_pk}' 없음")
        dets = (db.query(BinPickDetection)
                .filter(BinPickDetection.scene_pk == scene.id)
                .order_by(BinPickDetection.idx).all())
        base = _scene_response(scene)
        return SceneDetailResponse(
            **base.model_dump(),
            detections=[DetectionResponse.model_validate(d) for d in dets],
        )


# ===== WebSocket =====

@router.websocket("/ws")
async def binpick_websocket(websocket: WebSocket):
    """장면 도착 실시간 푸시 (vision `/api/v1/vision/ws`와 같은 방식)"""
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    register_ws(queue)

    try:
        while True:
            msg = await queue.get()
            await websocket.send_json(msg)
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        logger.error(f"빈피킹 WebSocket 오류: {e}")
    finally:
        unregister_ws(queue)
