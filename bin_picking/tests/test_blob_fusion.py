"""
검출∩덩어리 융합(blob_fusion) 테스트 — 자체 실행 스크립트(pytest 아님 · 다른 bin_picking/tests 와 같은 방식)

  python bin_picking/tests/test_blob_fusion.py

① 합성 장면: 빈 곳 검출 거부 · 덩어리 좌표로 교체 · 겹침 부족 거부 · 같은 덩어리 중복 · 높이·테두리·조각 거름 · pick_unmatched · 원본 불변
② 🥇 실물 회귀(10/16 공장 2장 · /data 에 있을 때만): 사이클 1 → 로봇 좌표 = 사이클 2 성공 좌표(-9.8,-13.4,464.6) ·
   사이클 3 → 후보 0(13_x2 위로 가던 "02" 거부) · pick_unmatched → 진짜 부품 덩어리 3개(벽·조각 제외)
③ 배선: run_live_pick 이 추론 뒤·소켓 앞에 fuse_file 을 부르고, 그 결과 파일을 서버에 넘기는가
   (9/1 교훈: 함수를 부르는 테스트는 "러너가 부르는지"를 검사하지 못한다)
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from bin_picking.src.utils.console_utf8 import enable_utf8_console  # noqa: E402
from bin_picking.src.pipeline import blob_fusion  # noqa: E402

INTR = json.loads((REPO / "bin_picking" / "config" / "blaze_intrinsics.json").read_text(encoding="utf-8"))
REAL = Path("/data/jtm/handover_1016/r1016")
ROI = REPO / "bin_picking" / "config" / "roi" / "roi_1012_pcapture447.json"

fails = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global fails
    print(f"  {'🟢' if cond else '🔴'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails += 1


def box(u0, v0, u1, v1):
    return [[u0, v0], [u1, v0], [u1, v1], [u0, v1]]


def synth_scene() -> np.ndarray:
    """바닥 무효(골판지) · 부품 A(높이 18) · 부품 B(높이 20) · 벽(높이 60) · 조각(높이 15·면적 작음) · 테두리 덩어리(높이 25)."""
    d = np.zeros((480, 848), np.float32)
    d[220:255, 380:420] = 465.0          # A  (u≈400, v≈237)
    d[290:325, 450:490] = 463.0          # B  (u≈470, v≈307)
    d[60:110, 300:350] = 423.0           # 벽 (높이 ≈ 60)
    d[150:158, 500:510] = 468.0          # 조각 80px(find_blobs 최소 40 이상 · 융합 최소 150 미만)
    d[330:360, 212:250] = 458.0          # 테두리(ROI include x0 = 212)
    d[100:101, 600:700] = 483.0          # 바닥 참고(p90 ≈ 483 이 되게 깊은 띠)
    d[400:404, 300:700] = 483.0
    return d


def det(label, conf, edge, x=0, y=0, z=470.0):
    return {"label": label, "confidence": conf, "x": x, "y": y, "z": z, "edge": edge, "angle": 0.0,
            "mask_area": 500, "camera_3d": {"Xc": 1.0, "Yc": 2.0, "Zc": z}, "notes": "orig"}


def test_synthetic() -> None:
    print("① 합성 장면")
    depth = synth_scene()
    six = {"scene_id": "synth", "detections": [
        det("02_sol_block_b", 0.97, box(382, 222, 418, 253), x=300, y=150),     # A 위 · 중심은 엉뚱 → 덩어리로 교체돼야
        det("guide_paper_roll_cover_right", 0.50, box(384, 224, 416, 250)),     # A 위 · 신뢰 낮음 → 중복 제거
        det("02_sol_block_b", 0.90, box(520, 180, 560, 215)),                   # 아무것도 없는 곳 → 겹침 0
        det("13_x2_bcf8ccb4", 0.30, box(452, 292, 458, 297)),                   # B 가장자리 조각 검출 → 겹침 부족
        det("plate_e", 0.80, box(302, 62, 348, 108)),                           # 벽 위 → 높이 거부
        det("plate_e", 0.70, box(214, 332, 248, 358)),                          # 테두리 덩어리 → 거부
    ]}
    original = json.dumps(six, sort_keys=True)
    out = blob_fusion.fuse_detections(six, depth, INTR, roi_include=[212, 32, 590, 406])
    f = out["fusion"]
    reasons = {r["det_index"]: r["reason"] for r in f["rejected"]}
    check("원본 six 는 바뀌지 않는다", json.dumps(six, sort_keys=True) == original)
    check("로봇 후보 = 1(A 위 02 하나)", f["n_kept"] == 1 and len(out["detections"]) == 1, f"{f['n_kept']} · {reasons}")
    d0 = out["detections"][0]
    check("남은 것은 신뢰가 높은 02", d0["label"] == "02_sol_block_b" and d0["confidence"] == 0.97)
    check("좌표가 덩어리 중심으로 교체(u≈399.5 v≈237)", abs(d0["x"] - 399.5) <= 1 and abs(d0["y"] - 237) <= 1, f"{d0['x']},{d0['y']}")
    check("Zc = 덩어리 윗면 465", abs(d0["camera_3d"]["Zc"] - 465.0) < 0.6, str(d0["camera_3d"]))
    check("원래 좌표는 fusion.orig_* 에 보존", d0["fusion"]["orig_xy"] == [300, 150] and d0["fusion"]["orig_camera_3d"]["Xc"] == 1.0)
    check("같은 덩어리 낮은 신뢰는 이유와 함께 버림", "더 높은 신뢰" in reasons.get(1, ""), reasons.get(1))
    check("빈 곳 검출 거부(겹침 0)", "겹침 0" in reasons.get(2, ""), reasons.get(2))
    check("가장자리 조각 검출 거부(겹침 부족)", "겹침 부족" in reasons.get(3, ""), reasons.get(3))
    check("벽 위 검출 거부(높이)", "높이" in reasons.get(4, ""), reasons.get(4))
    check("테두리 덩어리 위 검출 거부", "테두리" in reasons.get(5, ""), reasons.get(5))
    check("조각 덩어리는 후보에서 빠진다", any("조각" in (b["excluded"] or "") for b in f["blobs"]))
    check("검출 안 붙은 후보 = B 하나", len(f["unmatched_blob_ids"]) == 1, str(f["unmatched_blob_ids"]))

    out2 = blob_fusion.fuse_detections(six, depth, INTR, roi_include=[212, 32, 590, 406], pick_unmatched=True)
    labs = [d["label"] for d in out2["detections"]]
    check("pick_unmatched = 02 다음에 unlabeled(B) 하나", labs == ["02_sol_block_b", "unlabeled"], str(labs))
    u = out2["detections"][1]
    check("unlabeled 좌표 = B 덩어리(u≈469.5)", abs(u["x"] - 469.5) <= 1 and abs(u["camera_3d"]["Zc"] - 463.0) < 0.6, f"{u['x']} {u['camera_3d']}")

    none = blob_fusion.fuse_detections({"detections": []}, depth, INTR)
    check("검출 0 이면 후보 0(예외 없음)", none["fusion"]["n_kept"] == 0 and none["detections"] == [])


def test_real() -> None:
    print("② 실물 회귀(10/16 공장)")
    s1 = REAL / "six" / "live_20261016_173920_roi.six.json"
    if not s1.exists():
        print("  ⚪ 건너뜀 — 10/16 실물 파일 없음(6000 /data/jtm/handover_1016/r1016)")
        return
    intr_p = REPO / "bin_picking" / "config" / "blaze_intrinsics.json"
    tmp = Path("/tmp")
    p1, f1 = blob_fusion.fuse_file(s1, REAL / "live_20261016_173920_roi.npy", intr_p,
                                   out_path=tmp / "t1.fused.json", roi_path=ROI)
    d1 = json.loads(p1.read_text(encoding="utf-8"))["detections"]
    check("사이클 1: 후보 1", len(d1) == 1, str(len(d1)))
    if d1:
        c = d1[0]["camera_3d"]
        check("사이클 1: 로봇 좌표 = 사이클 2 성공 좌표(-9.8,-13.4,464.6)",
              (c["Xc"], c["Yc"], c["Zc"]) == (-9.8, -13.4, 464.6), str(c))
        check("사이클 1: 원래 1순위 좌표(-102.1,-114.1,470)는 빈 바닥이었다",
              d1[0]["fusion"]["orig_camera_3d"]["Xc"] == -102.1)

    s3 = REAL / "six" / "live_20261016_175745_roi.six.json"
    p3, f3 = blob_fusion.fuse_file(s3, REAL / "live_20261016_175745_roi.npy", intr_p,
                                   out_path=tmp / "t3.fused.json", roi_path=ROI)
    check("사이클 3: 후보 0(13_x2 위로 가던 '02' 거부)", f3["n_kept"] == 0, str(f3["rejected"]))
    check("사이클 3: '02'(0.26) 거부 사유 = 겹침 부족",
          any(r.get("label") == "02_sol_block_b" and "겹침 부족" in r["reason"] for r in f3["rejected"]))
    p3b, f3b = blob_fusion.fuse_file(s3, REAL / "live_20261016_175745_roi.npy", intr_p,
                                     out_path=tmp / "t3b.fused.json", roi_path=ROI, pick_unmatched=True)
    d3 = json.loads(p3b.read_text(encoding="utf-8"))["detections"]
    xy = sorted((round(d["camera_3d"]["Xc"], 1), round(d["camera_3d"]["Yc"], 1)) for d in d3)
    check("사이클 3 + pick_unmatched: 진짜 부품 덩어리 3개(13_x2·02·plate_e)만",
          xy == [(-109.6, -99.5), (3.9, -17.3), (86.8, 80.6)], str(xy))


def test_wiring() -> None:
    print("③ 배선(run_live_pick)")
    from bin_picking.src import run_live_pick
    src = inspect.getsource(run_live_pick.main)
    i_e2e = src.find("run_e2e(")
    i_fuse = src.find("blob_fusion.fuse_file(")
    i_serve = src.find("return serve(")
    check("main 이 blob_fusion.fuse_file 을 부른다", i_fuse > 0)
    check("순서 = 추론 → 융합 → 소켓", 0 < i_e2e < i_fuse < i_serve, f"{i_e2e} {i_fuse} {i_serve}")
    check("융합 결과가 six 로 다시 묶인다(서버가 융합 파일을 받는다)", "six, fusion = blob_fusion.fuse_file(" in src)
    check("--no-fuse 일 때만 건너뛴다", "if args.no_fuse:" in src)


if __name__ == "__main__":
    enable_utf8_console()
    test_synthetic()
    test_real()
    test_wiring()
    print(f"\n{'✅ 전부 통과' if fails == 0 else f'🔴 실패 {fails}'}")
    sys.exit(0 if fails == 0 else 1)
