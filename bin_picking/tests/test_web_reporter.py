#!/usr/bin/env python3
"""`web_reporter` 검증. (2026-08-07)

⭐ 이 테스트가 지키는 것
-----------------------
1. 🚨 **웹이 죽어도 로봇은 계속 돌아야 한다** — 전송 실패가 예외로 터져 나오면
   인식 사이클이 멈춘다. 실패는 `ok=False`로 돌아와야 한다.
2. 🚨 **그렇다고 조용히 삼키지도 않는다** — 실패는 `error`에 남아야 한다.
   ("실패해도 안 멈춤"과 "실패를 숨김"은 다르다.)
3. ⭐ **인덱스 정합** — plans와 detections 개수가 다르면 **거부**한다.
   8/5 grasp_plan에서 세운 원칙: 어긋나면 엉뚱한 부품의 벌림을 보고하게 된다.
4. ⭐ **게이트 판정이 반드시 실린다** — 안 돌렸으면 `not_checked`로 명시.
   판정 없는 것과 판정이 통과인 것은 다르다.
5. **로봇 전용 값은 웹에 안 나간다** — `edge`·`camera_3d`는 화면에서 쓸모없다.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from bin_picking.src.communication.web_reporter import (  # noqa: E402
    MODULE_BIN_PICKING,
    PAYLOAD_SCHEMA_VERSION,
    ReportResult,
    WebReporter,
    WebReportError,
    build_bin_picking_payload,
    file_transport,
)

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}  {detail}")


def six_sample(n: int = 2, with_gate: bool = True) -> dict:
    dets = []
    for i in range(n):
        dets.append({
            "x": 100 + i, "y": 200 + i, "z": 450.0 + i,
            "angle": 12.5, "label": f"part_{i}", "confidence": 0.9,
            # 로봇 전용 — 웹에 나가면 안 되는 값들
            "edge": [[0, 0], [1, 0], [1, 1], [0, 1]],
            "camera_3d": {"Xc": 1.0, "Yc": 2.0, "Zc": 450.0},
            "cad_score": 0.8,
        })
    out = {
        "scene_id": "shot_001_c1",
        "recognition_track": "depth_track",
        "detections": dets,
    }
    if with_gate:
        # 🚨 키 이름은 input_gate.check_scene()의 **실제 반환**과 같아야 한다.
        #    8/7에 여기를 `valid_pct`로 지어냈다가, 코드도 같은 오타를 쓰고 있어
        #    **테스트가 통과하는데 실제로는 None이 나가는** 상태를 놓쳤다.
        #    → 아래 [6]에서 진짜 input_gate 출력으로 교차 검증한다.
        out["gate_summary"] = {"n_in": n + 1, "n_kept": n, "n_dropped": 1,
                               "scene_verdict": "in_distribution"}
        out["gate_scene"] = {"trusted": True, "valid_ratio_pct": 5.6,
                             "verdict": "in_distribution", "note": "분포 안"}
    return out


class Plan:
    def __init__(self, w): self.gripper_width_mm = w


def main() -> int:
    print("=" * 66)
    print(" [1] payload 생성 — 로봇 전용 값은 빠진다")
    print("=" * 66)
    p = build_bin_picking_payload(six_sample(2), latency_ms=2670.4)
    check("schema_version 있음", p["schema_version"] == PAYLOAD_SCHEMA_VERSION)
    check("module = bin_picking", p["module"] == MODULE_BIN_PICKING)
    check("scene_id 보존", p["scene_id"] == "shot_001_c1")
    check("검출 2건", len(p["detections"]) == 2)
    check("6요소 핵심 필드 유지",
          all(k in p["detections"][0] for k in ("x", "y", "z", "angle", "label")))
    # 🚨 로봇 전용 값이 새어나가면 payload만 커지고 화면엔 쓸모없다
    check("edge는 안 나간다", "edge" not in p["detections"][0])
    check("camera_3d는 안 나간다", "camera_3d" not in p["detections"][0])
    check("latency 반올림", p["summary"]["latency_ms"] == 2670.4)
    check("고유 라벨 수", p["summary"]["n_unique_labels"] == 2)

    print()
    print("=" * 66)
    print(" [2] ⭐ 게이트 판정이 반드시 실린다")
    print("=" * 66)
    check("게이트 verdict 실림", p["scene_gate"]["verdict"] == "in_distribution")
    check("유효율 실림", p["scene_gate"]["valid_ratio_pct"] == 5.6)
    check("크기게이트 제거건수 실림",
          p["scene_gate"]["n_dropped_by_size_gate"] == 1)
    # 🚨 게이트를 안 돌린 것을 "정상"으로 보고하면 안 된다
    p2 = build_bin_picking_payload(six_sample(1, with_gate=False))
    check("게이트 미실행은 not_checked",
          p2["scene_gate"]["verdict"] == "not_checked",
          str(p2["scene_gate"]))
    check("미실행 시 trusted는 None", p2["scene_gate"]["trusted"] is None)

    print()
    print("=" * 66)
    print(" [3] 🚨 인덱스 정합 — 개수가 다르면 거부")
    print("=" * 66)
    ok_plans = [Plan(40.0), Plan(63.0)]
    p3 = build_bin_picking_payload(six_sample(2), plans=ok_plans)
    check("벌림이 실린다", p3["detections"][1]["gripper_width_mm"] == 63.0)
    try:
        build_bin_picking_payload(six_sample(2), plans=[Plan(40.0)])
        check("개수 불일치 거부", False, "예외가 안 났다")
    except WebReportError:
        check("개수 불일치 거부", True)

    try:
        build_bin_picking_payload({"scene_id": "x"})
        check("detections 없으면 거부", False, "예외가 안 났다")
    except WebReportError:
        check("detections 없으면 거부", True)

    print()
    print("=" * 66)
    print(" [4] 🚨 전송 실패가 로봇을 멈추지 않는다")
    print("=" * 66)

    def boom(_payload):
        raise ConnectionError("서버 없음")

    r = WebReporter(boom).report_bin_picking(six_sample(1))
    check("예외가 밖으로 안 나온다", isinstance(r, ReportResult))
    check("실패로 표시", r.ok is False)
    check("bool()도 False", not r)
    # ⭐ 삼키지 않는다 — 원인이 남아야 한다
    check("에러 원인 보존", r.error and "서버 없음" in r.error, str(r.error))
    check("scene_id 보존", r.scene_id == "shot_001_c1")

    print()
    print("=" * 66)
    print(" [5] 파일 transport — 서버 없이도 검증된다")
    print("=" * 66)
    with tempfile.TemporaryDirectory() as td:
        rep = WebReporter(file_transport(Path(td)))
        res = rep.report_bin_picking(six_sample(2), latency_ms=100.0)
        check("전송 성공", bool(res), str(res.error))
        written = list(Path(td).glob("*.json"))
        check("파일 1개 생성", len(written) == 1, str(written))
        saved = json.loads(written[0].read_text(encoding="utf-8"))
        check("저장 내용이 payload와 같다",
              saved["scene_id"] == "shot_001_c1" and len(saved["detections"]) == 2)
        check("통계 집계", rep.stats == {"sent": 1, "failed": 0}, str(rep.stats))

        # scene_id에 경로 문자가 있어도 파일명이 깨지지 않아야 한다
        bad = six_sample(1)
        bad["scene_id"] = "../evil/x y"
        res2 = rep.report_bin_picking(bad)
        check("위험한 scene_id도 안전하게 저장", bool(res2), str(res2.error))
        check("상위 경로로 안 새어나감",
              all(f.parent == Path(td) for f in Path(td).glob("*.json")))

    print()
    print("=" * 66)
    print(" [6] 🚨 진짜 input_gate 출력과 교차 검증 (손으로 지은 dict 금지)")
    print("=" * 66)
    # ⭐ 왜 이 블록이 필요한가 — [2]는 **내가 만든 가짜 dict**를 쓴다. 그래서
    #    코드와 테스트가 **같은 오타**를 공유하면 통과해버린다. 8/7에 실제로
    #    `valid_pct`(존재하지 않는 키)로 둘 다 써서 유효율이 조용히 None으로
    #    나가는 것을 놓쳤다. 아래는 **진짜 게이트를 돌려** 그 구멍을 막는다.
    import numpy as np  # noqa: E402
    from bin_picking.src.pipeline import input_gate  # noqa: E402

    # 학습 분포 안(유효율 낮음)을 흉내내는 depth — 대부분 0(무효), 일부만 부품 대역
    depth = np.zeros((480, 848), dtype=np.uint16)
    depth[200:230, 400:440] = 30000  # 약 5% 미만 유효
    gated = input_gate.apply(six_sample(2), depth)
    pg = build_bin_picking_payload(gated)
    sg = pg["scene_gate"]

    check("실제 게이트 verdict가 실린다",
          sg["verdict"] in ("in_distribution", "out_of_distribution", "warn"),
          str(sg["verdict"]))
    # 🚨 핵심 — 유효율이 None이면 키 이름이 어긋난 것이다
    check("⭐유효율이 None이 아니다(키 이름 검증)",
          isinstance(sg["valid_ratio_pct"], (int, float)),
          f"실제 {sg['valid_ratio_pct']!r} — input_gate 반환 키와 대조할 것")
    check("note가 실린다", bool(sg["note"]), str(sg["note"]))
    check("trusted가 bool", isinstance(sg["trusted"], bool), str(sg["trusted"]))
    # payload가 싣는 모든 게이트 키가 실제 반환에 존재하는지 전수 대조
    real_scene = gated.get("gate_scene", {})
    for key in ("verdict", "trusted", "valid_ratio_pct", "note"):
        check(f"input_gate에 '{key}' 실재", key in real_scene,
              f"실제 키: {sorted(real_scene)}")

    print()
    print("=" * 66)
    print(f"결과: {PASS} 통과 / {FAIL} 실패")
    print("=" * 66)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
