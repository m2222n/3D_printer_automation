"""
depth_track 추론 결과 → 협력사 6요소 좌표 (x, y, z, edge, angle, label)
======================================================================

**P0 #2** — 인식(depth_track)과 출력 규격(6요소)을 잇는 브리지.

기존 `yolo_track/pipeline/detect_and_output.py` 는 **YOLO(RGB) 전용**이고
depth_track 예측 JSON과 인터페이스가 달라 그대로 쓸 수 없다. 이 모듈이 변환을 맡는다.

## 좌표계 — 여기가 이 파일의 핵심 (틀리면 로봇이 엉뚱한 데를 찌른다)

depth_track 예측 bbox는 **크롭·리사이즈된 입력 좌표계**다:

```
원본 depth (848×480)
  └ center_crop 1/6~5/6  → crop_bbox_yxyx = [y0,x0,y1,x1] = [80,141,400,707]  (320×566)
      └ resize           → input_shape_hw = [320,576]      ← 예측 bbox가 이 좌표계
```

따라서 6요소로 내보내려면 **resize 역스케일 → crop 오프셋 가산**으로 원본으로 되돌려야 한다.
6요소 규격(`sample_output_6elements.yaml`)이 `image_shape: [480, 848]` = **원본 기준**이기 때문.

⚠️ 이 역변환을 빼먹으면 좌표가 (141, 80)만큼 밀리고 스케일도 어긋난다. 조용히 틀리는 종류의 버그다.

## z(depth) 계산

⚠️ **7/28 rgbd_fusion 교훈**: 단일 픽셀 depth는 노이즈에 취약하고, Blaze 저해상도
양자화가 ACE2 격자에서 최대 ~3.5px까지 증폭된다 → **영역 median**을 써야 한다.
여기서는 **bbox 중심 주변 window median**(유효 픽셀만)으로 뽑고, 표본 수를 notes에 남긴다.

## edge / angle

⚠️ 현 예측 JSON에는 **마스크 픽셀이 저장되지 않는다**(`mask_area`만 있음) →
edge는 **bbox 4코너 fallback**, angle은 **0.0**이다. 이는 `detect_and_output.py`의
v2(detection) 단계와 같은 한계다. 진짜 contour·회전각이 필요하면 추론 시 마스크를
저장하도록 eval 스크립트를 고쳐야 한다(별건).

## 사용

    # 저장된 예측 JSON 1건 → 6요소 JSON
    python -m bin_picking.src.pipeline.depth_track_to_6elements \
        --pred /data/jtm/synth_out/eval_cpu_0729_full100/predictions/shot_009_g1.json \
        --out /tmp/6elem_shot_009.json

    # 디렉토리 일괄
    python -m bin_picking.src.pipeline.depth_track_to_6elements \
        --pred-dir /data/jtm/synth_out/eval_cpu_0729_full100/predictions --out-dir /tmp/6elem
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

import numpy as np

SPEC_VERSION = "hansol_6elements_v1_20260520"
OUTPUT_SCHEMA_VERSION = "orinu_output_v1_20260522"
# 이 브리지가 만든 출력임을 구분 (yolo_track 산출물과 섞이지 않게)
SOURCE_TAG = "depth_track"


class BridgeError(RuntimeError):
    pass


def crop_to_source(
    bbox_xyxy: list[float],
    crop_bbox_yxyx: list[int],
    input_shape_hw: list[int],
) -> tuple[float, float, float, float]:
    """예측 bbox(크롭·리사이즈 좌표계) → 원본 depth 좌표계.

    crop_bbox_yxyx = [y0, x0, y1, x1] (원본 기준 크롭 영역)
    input_shape_hw = [H, W] (모델 입력 = 크롭을 리사이즈한 결과)
    """
    y0, x0, y1, x1 = crop_bbox_yxyx
    ih, iw = input_shape_hw
    crop_h, crop_w = (y1 - y0), (x1 - x0)
    if crop_h <= 0 or crop_w <= 0 or ih <= 0 or iw <= 0:
        raise BridgeError(f"크롭/입력 크기가 비정상: crop={crop_bbox_yxyx} input={input_shape_hw}")

    # resize 역스케일 (입력 → 크롭) 후 크롭 오프셋 가산 (크롭 → 원본)
    sx, sy = crop_w / float(iw), crop_h / float(ih)
    bx1, by1, bx2, by2 = bbox_xyxy
    return (bx1 * sx + x0, by1 * sy + y0, bx2 * sx + x0, by2 * sy + y0)


# ⚠️⚠️ 실측 npy는 uint16이며 **mm가 아니다**. eval과 동일 변환을 반드시 쓸 것:
#     depth_m = raw_uint16 * (REAL_UINT16_MAX_DEPTH_M / 65535)
# 근거 = eval_real_depth_vq_detector.py:135 (`scale = real_uint16_max_depth_m / 65535.0`)
#        + depth_preprocess.py:54 (`depth_m = raw_uint16 * (10.0 / 65535.0)`)
# 검산: raw 3212 → 3212*10/65535 = 0.490 m = 490 mm ✅ (부품 촬영 실거리 450~500mm와 일치)
# 🐛 7/29 실제 사고: raw를 mm로 오해해 z가 3136~3358mm로 나왔다(6~7배 과대).
#    "400~600mm 픽셀이 0개"라는 사실이 스케일 오류를 잡아냈다 — 값이 그럴싸해도 검산할 것.
REAL_UINT16_MAX_DEPTH_M = 10.0


def raw_to_mm(raw: np.ndarray) -> np.ndarray:
    """실측 uint16 → mm. 0(무효)은 0으로 유지."""
    out = raw.astype(np.float32) * (REAL_UINT16_MAX_DEPTH_M / 65535.0) * 1000.0
    out[raw == 0] = 0.0
    return out


def safe_depth_at(
    depth_mm: np.ndarray, x: int, y: int, window: int = 5,
) -> tuple[float, str]:
    """(x,y) 주변 window median. 유효 픽셀(>0, 유한)만 사용.

    ⚠️ 입력은 **이미 mm로 변환된** 배열이어야 한다(`raw_to_mm`).
    ⚠️ 단일 픽셀은 쓰지 않는다 — Blaze 양자화·노이즈 때문(7/28 검증).
    """
    h, w = depth_mm.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        return 0.0, "out_of_bounds"
    half = window // 2
    x0, x1 = max(0, x - half), min(w, x + half + 1)
    y0, y1 = max(0, y - half), min(h, y + half + 1)
    patch = depth_mm[y0:y1, x0:x1].astype(np.float32)
    valid = patch[(patch > 0) & np.isfinite(patch)]
    if valid.size == 0:
        return 0.0, "no_valid_depth"
    return float(np.median(valid)), f"median_{window}x{window}_valid={valid.size}"


def _bbox_median_depth(
    depth_mm: np.ndarray, x1: float, y1: float, x2: float, y2: float,
) -> tuple[float, str]:
    """bbox 영역 전체의 유효 depth median — 중심이 비었을 때의 fallback.

    ⚠️ 배경 픽셀이 섞일 수 있다. 로봇이 z를 쓰기 전에 `notes`의 출처를 확인할 것.
    구멍이 큰 부품(얇은 브래킷·반사면)에서 이 경로를 탄다.
    """
    h, w = depth_mm.shape[:2]
    ix1, iy1 = max(0, int(round(x1))), max(0, int(round(y1)))
    ix2, iy2 = min(w, int(round(x2))), min(h, int(round(y2)))
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0, "no_valid_depth_bbox_empty"
    reg = depth_mm[iy1:iy2, ix1:ix2].astype(np.float32)
    valid = reg[(reg > 0) & np.isfinite(reg)]
    if valid.size == 0:
        return 0.0, "no_valid_depth"
    ratio = 100.0 * valid.size / reg.size
    return float(np.median(valid)), f"bbox_median_fallback_valid={valid.size}({ratio:.0f}%)"


def pixel_to_camera_3d(u: float, v: float, z_mm: float, intr: dict) -> tuple[float, float, float]:
    """핀홀 역투영 — 협력사·detect_and_output.py와 동일 모델."""
    fx, fy = intr["fx"], intr["fy"]
    ppx = intr.get("ppx", intr.get("cx"))
    ppy = intr.get("ppy", intr.get("cy"))
    return ((u - ppx) * z_mm / fx, (v - ppy) * z_mm / fy, float(z_mm))


def bbox_to_edge_corners(x1: float, y1: float, x2: float, y2: float) -> list[list[int]]:
    """축정렬 4코너 (좌상→우상→우하→좌하). 마스크가 없을 때의 fallback."""
    return [[int(round(x1)), int(round(y1))], [int(round(x2)), int(round(y1))],
            [int(round(x2)), int(round(y2))], [int(round(x1)), int(round(y2))]]


def _label_from(pred: dict) -> str:
    """cad_id에서 사람이 읽는 라벨을 뽑는다.

    cad_id 예: '18_button_function_niro__d790553b' → '18_button_function_niro'
    (뒤 해시는 CAD 파일 식별자라 로봇 쪽엔 의미 없다)
    """
    cad = pred.get("cad_id") or ""
    if cad:
        return str(cad).split("__")[0]
    cid = pred.get("class_id")
    return f"class_{cid}" if cid is not None else "unknown"


def convert(
    pred_json: dict,
    depth: Optional[np.ndarray] = None,
    blaze_intrinsics: Optional[dict] = None,
    depth_window: int = 5,
    require_intrinsics: bool = True,
) -> dict:
    """depth_track 예측 1장 → 6요소 dict.

    depth 가 주어지면 z와 camera_3d를 채운다. 없으면 z=0으로 두고 notes에 남긴다
    (형식 검증만 할 때 유용).

    ⚠️ `depth`는 **raw uint16이든 mm float이든 그대로** 넘겨도 된다. 내부에서
       `depth_units.to_mm()`으로 정규화한다(⭐7/31 신설한 단일 출처. dtype 기준
       규약이라 추측하지 않는다). **호출자가 미리 변환할 필요 없다.**

    🚨 `require_intrinsics=True`(기본)면 intrinsics가 없을 때 **예외를 던진다.**
       ⭐8/5 발견 = 예전엔 조용히 `camera_3d`를 생략했고, 그러면 소켓 서버가
       "camera_3d 없음"으로 **전건 거부**해 로봇에 좌표가 하나도 안 간다.
       intrinsics는 `main()`에서만 로드되고 있어서 **라이브러리로 호출하면
       무조건 None**이었다 → 실환경에서 조용히 실패하는 종류의 버그.
       형식만 볼 때는 `require_intrinsics=False`.
    """
    crop = pred_json.get("crop_bbox_yxyx")
    inshape = pred_json.get("input_shape_hw")
    srch, srcw = pred_json.get("source_depth_hw", [None, None])
    if not crop or not inshape:
        raise BridgeError("예측 JSON에 crop_bbox_yxyx / input_shape_hw 가 없다 "
                          "— 좌표 역변환 불가(원본 좌표계로 되돌릴 수 없음)")

    # ⭐ intrinsics를 여기서 자동 로드한다(호출자가 잊어도 되게).
    if blaze_intrinsics is None:
        blaze_intrinsics = _load_blaze_intr()
    if blaze_intrinsics is None and depth is not None and require_intrinsics:
        raise BridgeError(
            "Blaze intrinsics를 로드할 수 없다 → camera_3d를 만들 수 없고, "
            "그러면 로봇에 보낼 좌표가 없다(소켓 서버가 전건 거부한다). "
            "config/blaze_intrinsics.json 확인. 형식만 볼 때는 "
            "require_intrinsics=False.")

    # 🔴 단위 정규화 — nan/mm/raw를 여기서 한 번만 정리한다.
    #    ⚠️ 나흘에 네 번 밟은 그 버그다(raw를 mm로 착각 → z가 6~7배 과대).
    #    8/5에 **다섯 번째**로 같은 자리를 밟았다: convert()가 raw를 그대로 써서
    #    z=2976mm(실제 442mm)가 나왔고, 그 값이 유효범위를 벗어나 전건 거부됐다.
    depth_mm, unit_note = None, "depth_not_provided"
    if depth is not None:
        depth_mm, unit_note = _to_mm_normalized(depth)

    detections = []
    for p in pred_json.get("predictions", []):
        bx1, by1, bx2, by2 = crop_to_source(p["bbox_xyxy"], crop, inshape)
        cx, cy = (bx1 + bx2) / 2.0, (by1 + by2) / 2.0

        if depth is not None:
            z, znote = safe_depth_at(depth_mm, int(round(cx)), int(round(cy)), depth_window)
            if z <= 0:
                # ⚠️ 7/29 실측: 중심 5x5가 비어도 **bbox 안에는 depth가 9~37% 남아 있다**
                #    (Blaze ToF가 부품 경계·반사면에서 구멍을 낸다. 장면 전체 유효율이
                #     3%까지 떨어지는 프레임도 있음). 이때 bbox median으로 살리면
                #     490~500mm로 정상 복구된다 → 버리지 말고 fallback.
                # ⚠️ 단 bbox median은 배경을 섞을 위험이 있으므로 출처를 notes에 남긴다.
                z, znote = _bbox_median_depth(depth_mm, bx1, by1, bx2, by2)
        else:
            z, znote = 0.0, "depth_not_provided"

        # ⭐ angle/edge — eval이 마스크에서 뽑아 심어준 값을 쓴다 (2026-07-30).
        #    없으면(옛 예측 JSON) 종전대로 축정렬 bbox + angle=0으로 떨어진다.
        #    🔴 angle이 필요한 이유 = 27종 중 22종·검출 82%가 종횡비 1.5 초과
        #       (tests/survey_rotation_asymmetry.py). 0은 "회전 없음"이 아니라 "모름".
        has_angle = p.get("angle_deg") is not None
        if has_angle:
            angle_val = float(p["angle_deg"])
            edge_val = p.get("obb_edge") or bbox_to_edge_corners(bx1, by1, bx2, by2)
            # ⚠️ reliable=False = 거의 정사각형(각도 무의미) 또는 마스크 깨짐.
            #    값은 주되 로봇이 걸러쓸 수 있게 플래그를 그대로 넘긴다.
            ang_note = ("angle=obb_minAreaRect"
                        if p.get("angle_reliable")
                        else f"angle=obb_unreliable({p.get('angle_note','')})")
            edge_note = "edge_source=obb_rotated"
        else:
            angle_val = 0.0
            edge_val = bbox_to_edge_corners(bx1, by1, bx2, by2)
            ang_note = "angle=0_mask_not_saved"
            edge_note = "edge_source=bbox_axis_aligned"

        det = {
            # --- 6요소 (필수) ---
            "x": int(round(cx)),
            "y": int(round(cy)),
            "z": round(z, 1),
            "edge": edge_val,
            "angle": round(angle_val, 2),
            "label": _label_from(p),
            # --- 부가 ---
            "bbox_pixel": {
                "cx": int(round(cx)), "cy": int(round(cy)),
                "w": int(round(bx2 - bx1)), "h": int(round(by2 - by1)),
                "x1": int(round(bx1)), "y1": int(round(by1)),
                "x2": int(round(bx2)), "y2": int(round(by2)),
            },
            "confidence": round(float(p.get("score", 0.0)), 4),
            "source": SOURCE_TAG,
            "cad_id": p.get("cad_id"),
            "cad_score": round(float(p.get("cad_score", 0.0)), 4),
            "mask_area": p.get("mask_area"),
        }
        if has_angle:
            # 로봇 쪽에서 각도를 믿을지 판단할 근거를 같이 넘긴다.
            det["angle_reliable"] = bool(p.get("angle_reliable"))
            det["obb_aspect"] = p.get("obb_aspect")
        if blaze_intrinsics is not None and z > 0:
            xc, yc, zc = pixel_to_camera_3d(cx, cy, z, blaze_intrinsics)
            det["camera_3d"] = {"Xc": round(xc, 1), "Yc": round(yc, 1), "Zc": round(zc, 1)}
        det["notes"] = (f"depth_source={znote} | {edge_note} "
                        f"| {ang_note} | coord=source_depth_frame")
        detections.append(det)

    out = {
        "scene_id": pred_json.get("scene_id"),
        "image_shape": [srch, srcw],          # 원본 depth [H, W]
        "spec_version": SPEC_VERSION,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "recognition_track": SOURCE_TAG,
        "coord_frame": "blaze_depth_pixel_and_camera_mm",
        "detections": detections,
        "notes": (
            "depth_track(depth-only) 추론 결과를 협력사 6요소로 변환. "
            "좌표는 crop/resize 역변환으로 원본 depth 프레임(848x480) 기준. "
            "⚠️ angle=0·edge=축정렬 bbox = 예측 마스크가 저장되지 않아서(mask_area만 있음). "
            "⚠️ camera_3d는 Blaze 카메라 좌표계이며 로봇 Base 변환(hand-eye)은 미착수."
        ),
    }
    if blaze_intrinsics is not None:
        out["intrinsics"] = dict(blaze_intrinsics)
    return out


def _src_on_path() -> None:
    """`bin_picking/src`를 import 경로에 넣는다(모듈 직접 실행/라이브러리 겸용)."""
    import sys
    root = Path(__file__).resolve().parents[1]   # .../bin_picking/src
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _to_mm_normalized(depth: np.ndarray) -> tuple[np.ndarray, str]:
    """raw uint16 / mm float 무엇이 와도 mm로 정규화. → (mm 배열, 설명)

    ⭐ 7/31 신설한 `depth_units.to_mm`을 단일 출처로 쓴다(dtype 기준 규약).
       ⚠️ 폴백으로 자체 변환하지 않는다 — 그게 단위 버그의 원천이었다.
       ⚠️ `to_mm`은 **(배열, 메시지) 튜플**을 돌려준다(시그니처 확인 필수).
    """
    _src_on_path()
    from acquisition.depth_units import to_mm as _to_mm
    return _to_mm(depth, verbose=False)


def _load_blaze_intr() -> Optional[dict]:
    """실측 intrinsics를 쓴다. ⚠️7/28 교훈 = 추정값 하드코딩 금지."""
    try:
        import sys
        root = Path(__file__).resolve().parents[3]
        sys.path.insert(0, str(root / "bin_picking" / "src"))
        from acquisition.rgbd_fusion import load_blaze_intrinsics
        i = load_blaze_intrinsics()
        return {"camera": "Basler_Blaze_112_measured", "fx": i.fx, "fy": i.fy,
                "ppx": i.cx, "ppy": i.cy, "width": i.width, "height": i.height,
                "unit": "pixel for fx/fy/ppx/ppy; z in mm"}
    except Exception as e:
        print(f"  ⚠️ Blaze intrinsics 로드 실패 → camera_3d 생략: {e}")
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pred", type=Path, help="예측 JSON 1건")
    g.add_argument("--pred-dir", type=Path, help="예측 JSON 디렉토리 (일괄)")
    ap.add_argument("--out", type=Path, help="--pred 용 출력 경로")
    ap.add_argument("--out-dir", type=Path, help="--pred-dir 용 출력 디렉토리")
    ap.add_argument("--depth-dir", type=Path, default=None,
                    help="원본 .npy depth 디렉토리. 생략하면 예측 JSON의 file 경로를 쓴다")
    ap.add_argument("--no-depth", action="store_true", help="z 계산 생략(형식만 확인)")
    ap.add_argument("--depth-window", type=int, default=5)
    # ⭐ 게이트는 **기본 적용**이다 — 껐을 때만 옵션이 필요하게 둔다.
    #   8/5에 `depth_units.py`를 단일 출처로 만들었으나 호출자가 안 써서 좌표가
    #   전건 무효였던 전례가 있다. "만들어두고 안 쓰는" 상태를 기본값으로 막는다.
    ap.add_argument("--no-gate", action="store_true",
                    help="입력·출력 게이트 끄기(부품 아닌 큰 예측 제거·장면 분포 판정)")
    args = ap.parse_args()

    intr = None if args.no_depth else _load_blaze_intr()

    def one(pred_path: Path, out_path: Path) -> tuple[int, int]:
        pj = json.loads(pred_path.read_text(encoding="utf-8"))
        depth = None
        if not args.no_depth:
            dpath = None
            if args.depth_dir:
                cand = args.depth_dir / (pj.get("scene_id", pred_path.stem) + ".npy")
                dpath = cand if cand.exists() else None
            if dpath is None and pj.get("file"):
                cand = Path(pj["file"])
                dpath = cand if cand.exists() else None
            if dpath is None:
                print(f"  ⚠️ {pred_path.name}: depth 파일을 못 찾음 → z=0")
            else:
                raw = np.load(dpath)
                # ⚠️ uint16 → mm 변환 필수 (raw는 mm가 아니다)
                depth = raw_to_mm(raw) if raw.dtype == np.uint16 else raw.astype(np.float32)
        res = convert(pj, depth=depth, blaze_intrinsics=intr, depth_window=args.depth_window)
        if not args.no_gate:
            # 이 모듈의 다른 곳(`depth_units`)과 같은 지연 import 방식.
            try:
                from . import input_gate  # type: ignore
            except ImportError:
                import input_gate  # type: ignore
            # ⭐ 장면 판정에는 **원본 depth**가 필요하다(유효율은 0 여부만 보므로 단위 무관).
            res = input_gate.apply(res, depth=depth)
            s = res["gate_summary"]
            if s["n_dropped"]:
                print(f"  🛡️ {pred_path.name}: 게이트 제거 {s['n_dropped']}건 "
                      f"(>{s['max_side_px']}px)")
            sc = res.get("gate_scene")
            if sc and not sc["trusted"]:
                print(f"  ⚠️ {pred_path.name}: 장면 {sc['verdict']} — {sc['note']}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(res, indent=2, ensure_ascii=False),
                            encoding="utf-8")
        n = len(res["detections"])
        nz = sum(1 for d in res["detections"] if d["z"] > 0)
        return n, nz

    if args.pred:
        out = args.out or args.pred.with_name(args.pred.stem + "_6elem.json")
        n, nz = one(args.pred, out)
        print(f"✅ {args.pred.name} → {out}")
        print(f"   검출 {n}건 / z 유효 {nz}건")
        return 0

    files = sorted(args.pred_dir.glob("*.json"))
    if not files:
        print(f"❌ {args.pred_dir} 에 json 없음")
        return 1
    outdir = args.out_dir or args.pred_dir.parent / "6elements"
    tot = totz = 0
    for f in files:
        n, nz = one(f, outdir / (f.stem + "_6elem.json"))
        tot += n
        totz += nz
    print(f"✅ {len(files)}개 파일 → {outdir}")
    print(f"   검출 총 {tot}건 / z 유효 {totz}건 ({100.0*totz/max(1,tot):.1f}%)")
    return 0


if __name__ == "__main__":
    # 🚨 Windows(cp949)에서 이모지 print가 UnicodeEncodeError로 죽는 것을 막는다
    #    (8/28 IPC 실사고 — 추론은 됐는데 출력 단계에서 5/5 실패) → utils/console_utf8.py
    try:
        from bin_picking.src.utils.console_utf8 import enable_utf8_console

        enable_utf8_console()
    except Exception:
        pass  # 콘솔 설정 실패가 본 작업을 막지 않는다
    raise SystemExit(main())
