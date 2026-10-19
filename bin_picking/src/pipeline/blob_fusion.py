"""
검출 ∩ 깊이 덩어리 융합 — 모델 검출을 "실제로 솟아 있는 덩어리"와 맞춰 보고, 좌표는 덩어리에서 가져온다
================================================================================================

🎯 왜 있는가 (10/19 · 10/16 공장 실측 2장이 정답지)
  10/16 빈피킹 3사이클 중 성공한 것은 **깊이 덩어리 중심을 손으로 넘긴 사이클 2** 하나였다.
  모델 검출을 그대로 보낸 사이클 1·3 은 둘 다 엉뚱한 곳으로 갔다 — 원인을 six.json 으로 다시 보니:
  ① 사이클 1: 1순위 검출 "02"(신뢰 0.97)의 **테두리(OBB)는 진짜 02 덩어리 위**에 있었다. 그런데 좌표(x,y)는
     흩어진 마스크 조각을 감싼 **166×168px 상자의 중심**(343,174)이라 빈 바닥에 떨어졌고, 깊이도 그 빈 곳 값(470)을 썼다.
     ⇒ 모델은 02 를 봤다. **좌표를 뽑는 단계가 틀린 자리를 골랐다.**
  ② 사이클 3: "02"(신뢰 0.26 · 마스크 32px)가 13_x2 덩어리 가장자리에 걸려 있었고 깊이 493(바닥보다 깊음)을 썼다
     → 로봇이 13_x2 위로 내려가 충돌 감지 정지(파손 0). 진짜 02 덩어리에는 검출이 하나도 없었다.

규칙 (순서대로 · 버린 것은 이유와 함께 남긴다 — 조용히 고치지 않는다)
  R1 덩어리 = `find_calib_blobs.find_blobs`(ROI 적용 depth · 근접 컷 · 연결 성분) — 사이클 2 성공 좌표를 낸 그 함수
  R2 덩어리 거름: 면적 < MIN_BLOB_AREA_PX(조각) · 높이 > MAX_HEIGHT_MM(빈 벽·케이블 · 10/16 = 47~68mm) ·
       ROI include 사각형 테두리에 닿음(빈 벽 밑동 · 10/16 덩어리 7 = 높이 34mm 인데 왼쪽 경계에 붙음) 은 집기 후보에서 뺀다
       (exclude 사각형 경계는 보지 않는다 — 10/16 진짜 13_x2 덩어리가 exclude 모서리에 걸쳐 있었다)
  R3 검출 영역 = OBB 테두리(`edge`) 다각형. 그 영역과 겹침이 가장 큰 덩어리에 붙이되
       겹침/덩어리면적 ≥ MIN_BLOB_COVER **그리고** 겹침/검출영역 ≥ MIN_DET_COVER 일 때만 — 못 넘으면 검출을 버린다
  R4 한 덩어리에 검출이 여럿이면 신뢰도가 가장 높은 것 하나만(이름도 그것)
  R5 남은 검출의 좌표 = 덩어리 중심(u,v) + 윗면 깊이(가까운 20%) → camera_3d 교체. 각도·테두리·이름은 검출 것을 유지
     ⇒ 로봇·캘리브(`cam_to_base`)는 camera_3d 만 읽으므로 다른 코드는 바뀌지 않는다
  (선택) pick_unmatched = 검출이 안 붙은 덩어리 중 R2 를 통과한 것을 "unlabeled" 로 뒤에 붙인다(이름 없이 찾아 집기)

🚨 한계(정직하게)
  - 덩어리끼리 붙어 있으면(화면 30px 미만) 한 덩어리로 합쳐진다 → 한 층·띄워 놓기 전제(10/31 합격선과 같다)
  - 높이는 바닥이 안 보일 때(골판지) ROI p90 참고값 기준이라 ±10mm 흔들린다 → MAX_HEIGHT_MM 은 넉넉히(40)
  - 이름은 여전히 모델 것이다. 덩어리가 맞아도 이름이 틀릴 수 있다(10/16: 진짜 02 를 "guide_paper"로) — 그리퍼 벌림만 이름을 쓴다
"""
from __future__ import annotations

import copy
from pathlib import Path

import numpy as np

MIN_BLOB_AREA_PX = 150     # 10/16: 진짜 부품 덩어리 602~1028px · 조각 66px
MAX_HEIGHT_MM = 40.0       # 10/16: 부품 15~21mm · 빈 벽·케이블 34~68mm (03 처럼 키 큰 부품을 쓰면 올린다)
MIN_BLOB_COVER = 0.30      # 검출 영역이 덩어리의 30% 이상을 덮어야 "그 덩어리를 본 것"
MIN_DET_COVER = 0.30       # 검출 영역의 30% 이상이 덩어리 위여야 "덩어리 위에 있는 검출"
ROI_EDGE_MARGIN_PX = 2     # include 테두리에서 이만큼 안이면 "닿음"


def _det_region(det: dict, shape: tuple[int, int]) -> np.ndarray:
    """검출이 화면에서 차지하는 영역(불리언). OBB 테두리 → 없으면 bbox_pixel → 없으면 빈 영역."""
    import cv2
    h, w = shape
    reg = np.zeros((h, w), np.uint8)
    edge = det.get("edge")
    if edge and len(edge) >= 3:
        pts = np.round(np.asarray(edge, dtype=np.float64)).astype(np.int32)
        cv2.fillPoly(reg, [pts], 1)
    else:
        bb = det.get("bbox_pixel") or {}
        if all(k in bb for k in ("x1", "y1", "x2", "y2")):
            reg[max(0, int(bb["y1"])):min(h, int(bb["y2"]) + 1), max(0, int(bb["x1"])):min(w, int(bb["x2"]) + 1)] = 1
    return reg.astype(bool)


def _blob_ok(b: dict, max_height_mm: float, min_area_px: int, roi_include: list | None = None) -> str | None:
    """집기 후보로 못 쓰는 덩어리면 이유, 쓸 수 있으면 None."""
    if roi_include:
        x1, y1, x2, y2 = roi_include
        bx, by, bw, bh = b["bbox"]
        m = ROI_EDGE_MARGIN_PX
        if bx <= x1 + m or by <= y1 + m or bx + bw - 1 >= x2 - m or by + bh - 1 >= y2 - m:
            return f"덩어리 {b['id']} ROI 테두리에 닿음(빈 벽 밑동 의심)"
    if b["area_px"] < min_area_px:
        return f"덩어리 {b['id']} 면적 {b['area_px']}px < {min_area_px}(조각)"
    if b["height_mm"] > max_height_mm:
        return f"덩어리 {b['id']} 높이 {b['height_mm']}mm > {max_height_mm}(빈 벽·케이블 의심)"
    return None


def fuse_detections(six: dict, depth_mm: np.ndarray, intr: dict, *,
                    max_height_mm: float = MAX_HEIGHT_MM, min_blob_area_px: int = MIN_BLOB_AREA_PX,
                    min_blob_cover: float = MIN_BLOB_COVER, min_det_cover: float = MIN_DET_COVER,
                    pick_unmatched: bool = False, roi_include: list | None = None) -> dict:
    """six.json(dict) 을 받아 융합된 새 six dict 를 돌려준다(원본은 건드리지 않는다). 요약은 out["fusion"]."""
    import sys
    repo = Path(__file__).resolve().parents[3]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from bin_picking.tests.find_calib_blobs import find_blobs  # 사이클 2 성공 좌표를 낸 그 함수

    res = find_blobs(depth_mm, intr, return_labels=True)
    labels = res.pop("_labels")
    blobs = res["blobs"]
    blob_reject = {b["id"]: _blob_ok(b, max_height_mm, min_blob_area_px, roi_include) for b in blobs}
    blob_px = {b["id"]: labels == b["comp"] for b in blobs}

    kept_by_blob: dict[int, dict] = {}
    rejected: list[dict] = []
    for idx, det in enumerate(six.get("detections") or []):
        name = det.get("label")
        conf = float(det.get("confidence") or 0.0)
        reg = _det_region(det, depth_mm.shape)
        reg_area = int(reg.sum())
        if reg_area == 0:
            rejected.append({"det_index": idx, "label": name, "reason": "검출 영역 없음(테두리·bbox 둘 다 없음)"})
            continue
        best, best_inter = None, 0
        for b in blobs:
            inter = int((reg & blob_px[b["id"]]).sum())
            if inter > best_inter:
                best, best_inter = b, inter
        if best is None:
            rejected.append({"det_index": idx, "label": name, "confidence": conf,
                             "reason": "솟아 있는 덩어리와 겹침 0 — 빈 바닥·빈 곳 검출"})
            continue
        cover_blob = best_inter / best["area_px"]
        cover_det = best_inter / reg_area
        if cover_blob < min_blob_cover or cover_det < min_det_cover:
            rejected.append({"det_index": idx, "label": name, "confidence": conf, "blob_id": best["id"],
                             "reason": f"덩어리 {best['id']} 와 겹침 부족(덩어리의 {cover_blob:.0%} · 검출의 {cover_det:.0%} · "
                                       f"기준 {min_blob_cover:.0%}/{min_det_cover:.0%})"})
            continue
        if blob_reject[best["id"]]:
            rejected.append({"det_index": idx, "label": name, "confidence": conf, "blob_id": best["id"],
                             "reason": blob_reject[best["id"]]})
            continue
        prev = kept_by_blob.get(best["id"])
        cand = {"det_index": idx, "det": det, "blob": best, "conf": conf,
                "cover_blob": cover_blob, "cover_det": cover_det}
        if prev is None or conf > prev["conf"]:
            if prev is not None:
                rejected.append({"det_index": prev["det_index"], "label": prev["det"].get("label"), "confidence": prev["conf"],
                                 "blob_id": best["id"], "reason": f"같은 덩어리에 더 높은 신뢰 검출({name} {conf:.2f})"})
            kept_by_blob[best["id"]] = cand
        else:
            rejected.append({"det_index": idx, "label": name, "confidence": conf, "blob_id": best["id"],
                             "reason": f"같은 덩어리에 더 높은 신뢰 검출({prev['det'].get('label')} {prev['conf']:.2f})"})

    out = copy.deepcopy(six)
    new_dets = []
    for c in sorted(kept_by_blob.values(), key=lambda c: -c["conf"]):
        d = copy.deepcopy(c["det"])
        b = c["blob"]
        x, y, z = b["cam_xyz_mm"]
        d["fusion"] = {"blob_id": b["id"], "cover_blob": round(c["cover_blob"], 2), "cover_det": round(c["cover_det"], 2),
                       "blob_height_mm": b["height_mm"], "orig_xy": [d.get("x"), d.get("y")], "orig_z": d.get("z"),
                       "orig_camera_3d": d.get("camera_3d")}
        d["x"], d["y"], d["z"] = int(round(b["u"])), int(round(b["v"])), b["top_depth_mm"]
        d["camera_3d"] = {"Xc": x, "Yc": y, "Zc": z}
        d["notes"] = (d.get("notes") or "") + f" | coord=blob_fusion(blob {b['id']})"
        new_dets.append(d)

    unmatched = [b for b in blobs if b["id"] not in kept_by_blob and not blob_reject[b["id"]]]
    if pick_unmatched:
        for b in unmatched:
            x, y, z = b["cam_xyz_mm"]
            new_dets.append({
                "label": "unlabeled", "confidence": 0.0, "x": int(round(b["u"])), "y": int(round(b["v"])),
                "z": b["top_depth_mm"], "angle": 0.0, "edge": None, "mask_area": b["area_px"],
                "camera_3d": {"Xc": x, "Yc": y, "Zc": z}, "source": "blob_only",
                "notes": f"coord=blob_fusion(blob {b['id']} · 검출 없음 · 이름 없음)",
                "fusion": {"blob_id": b["id"], "blob_height_mm": b["height_mm"], "unmatched": True},
            })

    out["detections"] = new_dets
    out["fusion"] = {
        "rule": "검출∩덩어리 v1(10/19)",
        "params": {"max_height_mm": max_height_mm, "min_blob_area_px": min_blob_area_px,
                   "min_blob_cover": min_blob_cover, "min_det_cover": min_det_cover, "pick_unmatched": pick_unmatched,
                   "roi_include": roi_include},
        "floor": {"depth_mm": res["floor_depth_mm"], "visible": res["floor_visible"], "how": res["floor_how"]},
        "blobs": [{**{k: b[k] for k in ("id", "u", "v", "area_px", "top_depth_mm", "height_mm", "cam_xyz_mm")},
                   "excluded": blob_reject[b["id"]]} for b in blobs],
        "n_in": len(six.get("detections") or []), "n_kept": len(kept_by_blob),
        "rejected": rejected,
        "unmatched_blob_ids": [b["id"] for b in unmatched],
    }
    return out


def fuse_file(six_path: Path, depth_path: Path, intr_path: Path, out_path: Path | None = None,
              roi_path: Path | None = None, **kw) -> tuple[Path, dict]:
    """파일 → 파일. 반환 = (융합 six 경로, fusion 요약). roi_path 를 주면 include 테두리 규칙(R2)을 쓴다."""
    import json
    import sys
    repo = Path(__file__).resolve().parents[3]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from bin_picking.src.acquisition.depth_units import to_mm

    six = json.loads(Path(six_path).read_text(encoding="utf-8"))
    depth_mm, _ = to_mm(np.load(depth_path), verbose=False)
    intr = json.loads(Path(intr_path).read_text(encoding="utf-8"))
    if roi_path is not None and "roi_include" not in kw:
        kw["roi_include"] = json.loads(Path(roi_path).read_text(encoding="utf-8"))["include"]
    fused = fuse_detections(six, depth_mm, intr, **kw)
    out_path = out_path or Path(str(six_path).replace(".six.json", ".fused.six.json"))
    out_path.write_text(json.dumps(fused, ensure_ascii=False, indent=1), encoding="utf-8")
    return out_path, fused["fusion"]


def print_summary(fusion: dict) -> None:
    f = fusion
    print(f"[융합] 검출 {f['n_in']} → 로봇 후보 {f['n_kept']} · 덩어리 {len(f['blobs'])}개(바닥 {f['floor']['depth_mm']}mm · {f['floor']['how']})")
    for b in f["blobs"]:
        tag = f"✗ {b['excluded']}" if b["excluded"] else "후보"
        print(f"   덩어리 {b['id']}: ({b['u']},{b['v']}) {b['area_px']}px 높이 {b['height_mm']}mm 윗면 {b['top_depth_mm']}mm · {tag}")
    for r in f["rejected"]:
        print(f"   ✗ 검출 {r['det_index']} {r.get('label')} ({r.get('confidence', 0):.2f}) — {r['reason']}")
    if f["unmatched_blob_ids"]:
        print(f"   ⚠️ 검출이 안 붙은 후보 덩어리 {f['unmatched_blob_ids']} — 모델이 못 본 부품일 수 있다(--pick-unmatched 로 이름 없이 집기)")
