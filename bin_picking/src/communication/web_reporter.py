#!/usr/bin/env python3
"""모듈 인식 결과를 **우리 웹으로 던지는** 경로. (2026-08-07 신설)

⭐ 왜 이 파일이 필요한가 (사업 범위 재정의)
------------------------------------------
사업 범위가 재정의됐다. **로봇 제어는 이번 사업 범위에서 제외**되고,
산출물은 **모듈 3개(①상태 판단 ②빈피킹 ③치수검사)와
⭐그 결과를 웹으로 전달하는 것까지**다.

즉 **이 파일이 산출물의 경계선**이다. 여기까지가 사업 범위 안이고,
로봇을 움직이는 것은 범위 밖이다.

기존에 있던 것 / 없던 것 (8/7 전수 확인):
  ① 상태 판단 → 🟢 **경로 있음**. `web-api/app/vision/`에 MQTT 수신 →
     `camera_manager` → DB 이벤트 → WebSocket 푸시 + 조회 API가 이미 구축돼 있다.
     ⚠️단 `camera_manager.py`에 `wash_1/wash_2/cure_1/cure_2` **4대가 하드코딩**돼
     있어 빈피킹·치수검사 결과는 그 경로로 들어갈 수 없다.
  ② 빈피킹 → 🔴 **코드 0건**  ← 이 파일이 채운다
  ③ 치수검사 → 🔴 코드 0건 (⏸️ 무엇을 측정할지 미확정이라 스키마를 못 정한다)

## 설계 원칙

🚨 **1. 웹 전송 실패가 인식·파지를 멈추지 않는다.**
   웹은 **보고 경로**이지 제어 경로가 아니다. 서버가 죽어도 로봇은 계속 돌아야 한다.
   → `report()`는 예외를 밖으로 던지지 않고 **결과 객체로 성패를 돌려준다.**
   ⭐ 단 **조용히 삼키지도 않는다** — 실패는 `ok=False`와 `error`에 남고 로그로 나간다.
   (이 파일만 예외적으로 "크게 실패하라" 원칙을 뒤집는다. 이유는 위 한 줄.)

🚨 **2. 좌표를 그대로 웹에 보내지 않는다.**
   웹은 **사람이 보는 화면**이다. `edge` 4코너나 `camera_3d` 같은 로봇용 값을
   그대로 흘리면 화면에서 쓸모도 없고 payload만 커진다.
   → **요약(summary) + 검출별 핵심 필드**로 줄여 보낸다. 원본이 필요하면 파일에 있다.

⭐ **3. 게이트 판정을 반드시 함께 보낸다.**
   8/6에 만든 입력·출력 게이트는 **"이 장면을 믿을 수 있나"** 를 판정한다.
   그 판정 없이 검출 수만 보내면 **c3처럼 배경을 부품으로 잡은 결과가
   정상처럼 보인다**. 신뢰도는 숫자와 함께 가야 한다.

⏸️ **미확정이라 지금 안 하는 것**
   - 실제 엔드포인트 경로·인증 — `web-api`에 빈피킹 수신 라우터가 아직 없다.
     ⭐ 그래서 **전송 대상(transport)을 갈아끼울 수 있게** 만들어 두고,
     기본은 **파일로 떨어뜨리는 것**으로 한다. 라우터가 생기면 HTTP로 바꾸면 된다.
     (7/30 레지스터 설계를 확정 전에 짰다가 무효가 된 전례를 되풀이하지 않는다.)
   - 치수검사 payload — **무엇을 측정하는지**가 8/5로 바뀌어(드릴 전 = 출력물 치수)
     아직 정해지지 않았다.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# 모듈 식별자 — 8/5 회의의 "모듈 3개"와 1:1 대응
MODULE_BIN_PICKING = "bin_picking"
MODULE_STATE_VISION = "state_vision"
MODULE_DIMENSION = "dimension_inspection"

PAYLOAD_SCHEMA_VERSION = "1.0.0"

# 웹으로 보낼 검출 필드 — 로봇 전용 값(edge·camera_3d)은 제외한다.
_DETECTION_FIELDS = ("x", "y", "z", "angle", "label", "confidence")


class WebReportError(RuntimeError):
    """payload를 만들 수 없을 때. **전송 실패는 여기에 해당하지 않는다.**"""


@dataclass
class ReportResult:
    """전송 결과. 🚨 예외 대신 이 객체로 성패를 돌려준다(위 설계원칙 1)."""

    ok: bool
    module: str
    scene_id: Optional[str] = None
    detail: str = ""
    error: Optional[str] = None
    payload: Optional[dict] = None

    def __bool__(self) -> bool:  # `if reporter.report(...):` 로 쓸 수 있게
        return self.ok


def _scene_verdict(six: dict) -> dict:
    """게이트 판정을 뽑는다. 게이트를 안 돌렸으면 그 사실을 명시한다.

    🚨 게이트를 안 돌린 것을 "정상"으로 보고하면 안 된다 — 판정이 없는 것과
    판정이 통과인 것은 다르다.
    """
    summary = six.get("gate_summary") or {}
    scene = six.get("gate_scene") or {}
    verdict = summary.get("scene_verdict", "not_checked")
    # 🚨 키 이름은 `valid_ratio_pct`다 — 8/7에 `valid_pct`로 추측해서 틀렸고,
    #    그 결과 유효율이 조용히 None으로 나갔다(verdict·note는 정상이라 안 보였다).
    #    ⭐ 시그니처는 추측하지 말고 확인할 것 → input_gate.check_scene() 반환 참조.
    return {
        "verdict": verdict,
        "trusted": bool(scene.get("trusted")) if scene else None,
        "valid_ratio_pct": scene.get("valid_ratio_pct"),
        "note": scene.get("note"),
        "n_dropped_by_size_gate": summary.get("n_dropped", 0),
    }


def build_bin_picking_payload(
    six: dict,
    *,
    plans: Optional[list] = None,
    latency_ms: Optional[float] = None,
    timestamp: Optional[str] = None,
) -> dict:
    """6요소 결과 → 웹 payload.

    ⭐ 여기서 줄인다. 웹 화면에 필요한 것은 **"몇 개를 어디서 찾았고 믿을 만한가"** 이지
    `edge` 4코너가 아니다.

    Args:
        six: `depth_track_to_6elements.convert()` 결과 (게이트 적용 후 권장)
        plans: `grasp_plan` 결과. 있으면 벌림을 함께 싣는다(인덱스 1:1 대응)
        latency_ms: 인식에 걸린 시간. 운영 화면에서 10초 예산 감시에 쓴다
        timestamp: 미지정이면 호출 시각
    """
    if not isinstance(six, dict):
        raise WebReportError("six는 dict여야 한다")
    if "detections" not in six:
        raise WebReportError(
            "six에 detections가 없다 — 6요소 결과가 맞는지 확인할 것")

    dets_in = six.get("detections") or []
    if plans is not None and len(plans) != len(dets_in):
        # 🚨 8/5 grasp_plan에서 세운 원칙 — 인덱스가 어긋나면 엉뚱한 부품의
        #    벌림을 보고하게 된다. 조용히 zip으로 자르지 않는다.
        raise WebReportError(
            f"plans({len(plans)})와 detections({len(dets_in)}) 개수가 다르다 "
            f"— 인덱스 대응이 깨졌다")

    dets_out = []
    for i, d in enumerate(dets_in):
        item: dict[str, Any] = {k: d.get(k) for k in _DETECTION_FIELDS}
        if plans is not None:
            p = plans[i]
            width = getattr(p, "gripper_width_mm", None)
            if width is None and isinstance(p, dict):
                width = p.get("gripper_width_mm")
            item["gripper_width_mm"] = width
        dets_out.append(item)

    labels = [d.get("label") for d in dets_in if d.get("label")]
    return {
        "schema_version": PAYLOAD_SCHEMA_VERSION,
        "module": MODULE_BIN_PICKING,
        "scene_id": six.get("scene_id"),
        "timestamp": timestamp or time.strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": {
            "n_detections": len(dets_out),
            "n_unique_labels": len(set(labels)),
            "recognition_track": six.get("recognition_track"),
            "latency_ms": round(latency_ms, 1) if latency_ms is not None else None,
        },
        # ⭐ 신뢰도 판정은 숫자와 반드시 함께 간다(설계원칙 3)
        "scene_gate": _scene_verdict(six),
        "detections": dets_out,
    }


# ── transport ────────────────────────────────────────────────────────────
# ⭐ 엔드포인트가 아직 없으므로 갈아끼울 수 있게 분리한다.
#    라우터가 생기면 http_transport만 붙이면 되고 호출부는 그대로다.

def file_transport(out_dir: Path) -> Callable[[dict], str]:
    """payload를 JSON 파일로 남긴다. **기본값** — 서버 없이도 동작을 검증할 수 있다."""
    out_dir = Path(out_dir)

    def _send(payload: dict) -> str:
        out_dir.mkdir(parents=True, exist_ok=True)
        scene = payload.get("scene_id") or "unknown"
        # 파일명에 쓰일 수 없는 문자를 지운다(scene_id는 외부 유래).
        safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in str(scene))
        path = out_dir / f"{payload['module']}_{safe}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    return _send


def http_transport(url: str, *, timeout_s: float = 3.0,
                   token: Optional[str] = None) -> Callable[[dict], str]:
    """payload를 웹 API로 POST한다.

    ⚠️ **빈피킹 수신 라우터는 아직 web-api에 없다.** 생기면 이 transport를 쓴다.
    🚨 timeout을 짧게 두는 이유 = 웹이 느려도 **인식 사이클(10초 예산)을 잡아먹으면 안 된다.**
    """
    def _send(payload: dict) -> str:
        import urllib.error
        import urllib.request

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return f"HTTP {resp.status}"

    return _send


class WebReporter:
    """모듈 결과를 웹으로 보낸다.

    ⭐ 사용:
        reporter = WebReporter(file_transport(Path("/data/.../web_out")))
        result = reporter.report_bin_picking(six, latency_ms=2670)
        if not result:
            logger.warning("웹 보고 실패: %s", result.error)   # 그래도 로봇은 계속
    """

    def __init__(self, transport: Callable[[dict], str],
                 *, module_label: str = MODULE_BIN_PICKING):
        self._send = transport
        self._module = module_label
        self.sent = 0
        self.failed = 0

    def report(self, payload: dict) -> ReportResult:
        """payload를 보낸다. 🚨 **예외를 밖으로 던지지 않는다**(설계원칙 1)."""
        scene = payload.get("scene_id")
        try:
            detail = self._send(payload)
        except Exception as exc:  # noqa: BLE001 - 어떤 전송 오류든 로봇을 멈추지 않는다
            self.failed += 1
            msg = f"{type(exc).__name__}: {exc}"
            logger.warning("웹 보고 실패 (scene=%s): %s", scene, msg)
            return ReportResult(ok=False, module=self._module, scene_id=scene,
                                error=msg, payload=payload)
        self.sent += 1
        logger.info("웹 보고 성공 (scene=%s): %s", scene, detail)
        return ReportResult(ok=True, module=self._module, scene_id=scene,
                            detail=detail, payload=payload)

    def report_bin_picking(self, six: dict, **kw) -> ReportResult:
        """6요소 결과를 payload로 만들어 보낸다.

        🚨 payload를 **만들지 못하는 것**은 전송 실패와 다르다(우리 코드의 계약 위반).
           그래서 그때는 예외를 던진다 — 조용히 넘기면 형식이 깨진 채 굳는다.
        """
        payload = build_bin_picking_payload(six, **kw)
        return self.report(payload)

    @property
    def stats(self) -> dict:
        return {"sent": self.sent, "failed": self.failed}


__all__ = [
    "MODULE_BIN_PICKING",
    "MODULE_STATE_VISION",
    "MODULE_DIMENSION",
    "PAYLOAD_SCHEMA_VERSION",
    "WebReportError",
    "ReportResult",
    "WebReporter",
    "build_bin_picking_payload",
    "file_transport",
    "http_transport",
]
