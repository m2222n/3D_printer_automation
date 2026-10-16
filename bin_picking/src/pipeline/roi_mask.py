"""ROI 마스크 — 카메라 화면에서 **빈 안쪽만** 남기고 나머지(벽·브라켓·케이블)를 무효(0)로 만든다.

왜 필요한가 (10/12 공장 실측 · 브라켓 v4 · P_capture 447mm):
  · 빈 안쪽(약 39×38cm)이 모델 평가 크롭(1/6~5/6 = 55×31cm)보다 **좁다** ⇒ 좌우 벽과 오른쪽 브라켓이 크롭 안에 들어온다.
  · 그 상태로 추론하면 장면 유효율 48%(분포 밖) · 모델 박스 8개 중 7개가 400px 벽 덩어리 · **부품 3개 중 1개만 검출**.
  · 같은 프레임에서 빈 안쪽만 남기면 유효율 4.9%(분포 안) · 진짜 부품이 다시 나온다.
  ⇒ 벽은 "부품으로 잘못 잡히는" 문제가 아니라 **"프레임 정규화를 틀어 진짜 부품을 지우는"** 문제다.
  📌 8/6 input_gate 가 *"ROI 크롭은 빈 확정 후"* 로 미뤄둔 항목 — 10/12 빈 확정(시연용 나무종이 빈 그대로).

설계
  · 설정 = JSON 한 파일: include [u0,v0,u1,v1] (빈 안쪽) + exclude [[u0,v0,u1,v1],…] (빈 안인데 못 쓰는 자리 · 10/12 왼쪽 주황 덩어리)
  · 좌표는 **전체 프레임(848×480) 픽셀** · 반열림 [u0,u1) [v0,v1) · 크롭 좌표가 아니다(크롭은 러너가 따로 한다).
  · `propose` = 새 프레임에서 빈 안쪽 사각형을 자동 제안(바닥이 IR 흡수라 **무효(0) 픽셀의 가장 큰 덩어리** = 빈 안쪽 · 벽은 유효라 경계가 된다).
    레이아웃이 바뀌면 사진 1장 → propose 한 줄 → 파일 교체. 코드는 그대로.
  · 마스크는 **raw uint16 그대로** 받아 0 으로 지운다(단위 변환 없음 · 학습셋 포맷 유지). 원본 npy 는 덮어쓰지 않고 `<stem>_roi.npy` 로 옆에 저장.

🚨 "짜여 있다 ≠ 호출된다"(9/1) — 이 모듈은 run_live_pick(--roi)·find_calib_blobs(--roi) 가 **실제로 부른다**. 배선 검사 = tests/test_roi_mask.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SCHEMA = "orinu_roi_mask_v1"
FRAME_HW = (480, 848)                 # Blaze Range · 학습셋과 동일
PROPOSE_MARGIN_PX = 6                 # 벽 윗면(가는 띠)이 안쪽으로 번지는 몫 · 10/12 실측 3~5px
PROPOSE_MIN_AREA_FRAC = 0.10          # 빈 안쪽은 화면의 10% 이상(10/12 실측: 447mm 에서 ~35% · 517mm 에서 14.5%)
PROPOSE_SEAL_PX = 4                   # 벽 띠의 틈을 메우는 두께(유효 픽셀 팽창) · 10/12 실물 틈 ≤ 8px


class RoiError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# 설정 파일
# ---------------------------------------------------------------------------
def _rect(r: Any, name: str) -> list[int]:
    try:
        u0, v0, u1, v1 = (int(round(float(x))) for x in r)
    except Exception:
        raise RoiError(f"{name}: [u0,v0,u1,v1] 네 정수여야 한다 — {r!r}")
    if not (0 <= u0 < u1 <= FRAME_HW[1] and 0 <= v0 < v1 <= FRAME_HW[0]):
        raise RoiError(f"{name}: 프레임 {FRAME_HW[1]}×{FRAME_HW[0]} 안의 올바른 사각형이 아니다 — {[u0, v0, u1, v1]}")
    return [u0, v0, u1, v1]


def load_roi(path: Path | str) -> dict:
    p = Path(path)
    if not p.exists():
        raise RoiError(f"ROI 파일이 없다: {p}")
    d = json.loads(p.read_text(encoding="utf-8"))
    if d.get("schema") != SCHEMA:
        raise RoiError(f"schema 가 {SCHEMA} 가 아니다: {d.get('schema')!r} — 다른 종류의 JSON 을 넣었나")
    inc = _rect(d.get("include"), "include")
    exc = [_rect(r, f"exclude[{i}]") for i, r in enumerate(d.get("exclude") or [])]
    return {"schema": SCHEMA, "include": inc, "exclude": exc, "notes": d.get("notes", ""),
            "source": d.get("source", ""), "capture_pose": d.get("capture_pose")}


def save_roi(roi: dict, path: Path | str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    out = {"schema": SCHEMA, "frame_hw": list(FRAME_HW), "include": roi["include"],
           "exclude": roi.get("exclude", []), "notes": roi.get("notes", ""),
           "source": roi.get("source", ""), "capture_pose": roi.get("capture_pose")}
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 적용
# ---------------------------------------------------------------------------
def roi_to_mask(roi: dict, hw: tuple[int, int] = FRAME_HW) -> np.ndarray:
    """True = 남긴다. include 안이면서 어떤 exclude 에도 안 들어가는 픽셀."""
    m = np.zeros(hw, dtype=bool)
    u0, v0, u1, v1 = roi["include"]
    m[v0:v1, u0:u1] = True
    for (a, b, c, d) in roi.get("exclude", []):
        m[b:d, a:c] = False
    return m


def apply_roi(depth: np.ndarray, roi: dict) -> np.ndarray:
    """raw uint16(또는 mm float) 프레임에서 ROI 밖을 0(무효)으로. 원본은 건드리지 않는다."""
    depth = np.asarray(depth)
    if depth.ndim != 2:
        raise RoiError(f"depth 가 2차원이 아니다 {depth.shape}")
    if tuple(depth.shape) != FRAME_HW:
        # (960,848) = Intensity 동봉(9/16 함정) 같은 것을 여기서 크게 막는다
        raise RoiError(f"depth 모양 {depth.shape} ≠ {FRAME_HW} — 학습셋 포맷이 아니다(Intensity 동봉? 다른 카메라?)")
    out = depth.copy()
    out[~roi_to_mask(roi, depth.shape)] = 0
    return out


def roi_stats(depth: np.ndarray, roi: dict, band_mm: tuple[float, float] = (400.0, 600.0)) -> dict:
    """마스크 전/후 장면 숫자(러너의 scene_valid_ratio 와 같은 뜻 · 전체 프레임 유효 %) + 크롭 안 대역 %."""
    from bin_picking.src.acquisition.depth_units import raw_to_mm
    h, w = depth.shape
    cy0, cy1, cx0, cx1 = h // 6, h * 5 // 6, w // 6, w * 5 // 6
    def _s(a: np.ndarray) -> dict:
        mm = raw_to_mm(a) if a.dtype == np.uint16 else a.astype(np.float32)
        crop = mm[cy0:cy1, cx0:cx1]
        band = (crop >= band_mm[0]) & (crop <= band_mm[1])
        return {"valid_pct": round(float((a > 0).mean() * 100), 2),
                "crop_band_pct": round(float(band.mean() * 100), 2)}
    return {"before": _s(depth), "after": _s(apply_roi(depth, roi))}


def apply_to_file(depth_path: Path | str, roi_path: Path | str, out_path: Path | str | None = None) -> tuple[Path, dict]:
    """npy → 마스크 → `<stem>_roi.npy`(기본) 저장. (저장 경로, 통계) 를 돌려준다."""
    depth_path = Path(depth_path)
    raw = np.load(depth_path)
    roi = load_roi(roi_path)
    masked = apply_roi(raw, roi)
    out = Path(out_path) if out_path else depth_path.with_name(depth_path.stem + "_roi.npy")
    np.save(out, masked)
    return out, roi_stats(raw, roi)


def rescore_scene_in_roi(six_path: Path | str, masked_depth_path: Path | str, roi_path: Path | str) -> dict:
    """six.json 의 gate_scene 을 **ROI 안 유효율** 로 바꿔 쓴다.
    이유: 러너의 장면 게이트(input_gate.check_scene)는 전체 프레임 유효율(학습 2~25%)을 본다. 마스크 뒤엔 ROI 밖이 전부 0 이라
    전체 기준 유효율이 1~2% 로 떨어져 '거의 비어 있다' 경고가 항상 뜬다(10/12 실측 1.6%). 빈 안쪽 면적으로 나누면 4.6% = 분포 안.
    🚨 수치 조작이 아니라 **분모를 바꾸는 것** — 원래 값은 scene['full_frame'] 에 남긴다."""
    from bin_picking.src.pipeline import input_gate
    six_path = Path(six_path)
    d = json.loads(six_path.read_text(encoding="utf-8"))
    roi = load_roi(roi_path)
    u0, v0, u1, v1 = roi["include"]
    sub = np.load(masked_depth_path)[v0:v1, u0:u1]
    new = input_gate.check_scene(sub)
    old = d.get("gate_scene") or {}
    new["note"] = "[ROI 안 기준] " + str(new.get("note", ""))
    new["roi"] = roi["include"]
    new["full_frame"] = {"valid_ratio_pct": old.get("valid_ratio_pct"), "verdict": old.get("verdict")}
    d["gate_scene"] = new
    # 🐛 10/16: 요약 판정도 같이 바꾼다 — 웹 보고(web_reporter._scene_verdict)는 gate_summary.scene_verdict 를 읽는다.
    #    안 바꾸면 화면엔 "분포 밖"·신뢰 True·메모 "분포 안"이 한 장면에 같이 뜬다(셀B 배선 실물 시험에서 발견).
    summ = d.get("gate_summary")
    if isinstance(summ, dict):
        summ["scene_verdict_full_frame"] = summ.get("scene_verdict")
        summ["scene_verdict"] = new.get("verdict")
    six_path.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[ROI] 장면 게이트 재판정(빈 안쪽 기준) = {new['verdict']}({new['valid_ratio_pct']}%) · 전체 화면 기준은 {old.get('valid_ratio_pct')}%")
    return new


# ---------------------------------------------------------------------------
# 제안 — 빈 안쪽 사각형을 프레임에서 찾는다
# ---------------------------------------------------------------------------
def propose_roi(depth: np.ndarray, *, margin_px: int = PROPOSE_MARGIN_PX,
                min_area_frac: float = PROPOSE_MIN_AREA_FRAC, seal_px: int = PROPOSE_SEAL_PX) -> dict:
    """빈 바닥은 IR 을 흡수해 **무효(0)** 로 찍히고 벽·브라켓은 유효로 찍힌다(8/18 · 10/12 실측).
    ⇒ 무효 픽셀의 연결 덩어리 중 **화면 중앙을 포함하는(없으면 가장 큰)** 것의 bbox 를 안쪽으로 margin 만큼 줄인 것이 빈 안쪽.
    🚨 바닥이 보이는(유효) 테이블 위에서는 성립하지 않는다 — 그때는 사람이 include 를 적는다."""
    import cv2
    depth = np.asarray(depth)
    if tuple(depth.shape) != FRAME_HW:
        raise RoiError(f"depth 모양 {depth.shape} ≠ {FRAME_HW}")
    # 벽 윗면은 가는 띠(3~5px)라 군데군데 끊긴다 → 유효 픽셀을 seal_px 만큼 두껍게 해 틈을 메운 뒤 무효 덩어리를 센다.
    # (10/12 실물: 안 메우면 오른쪽 브라켓 틈·아래 벽 틈으로 새어 [204,27,636,474] 가 나왔다 — 실제 빈 안쪽은 ~[205,45,605,430])
    valid = (depth > 0).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * seal_px + 1, 2 * seal_px + 1))
    sealed = cv2.dilate(valid, k)
    invalid = (sealed == 0).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(invalid, connectivity=4)
    if n <= 1:
        raise RoiError("무효 픽셀 덩어리가 없다 — 바닥이 IR 을 반사하는 조건(빈 밖 · 플라스틱 바닥)이라 자동 제안 불가")
    h, w = depth.shape
    center_lab = int(lab[h // 2, w // 2])
    cand = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= min_area_frac * h * w]
    if not cand:
        big = max(range(1, n), key=lambda i: stats[i, cv2.CC_STAT_AREA])
        raise RoiError(f"화면의 {min_area_frac*100:.0f}% 넘는 무효 덩어리가 없다(가장 큰 것 {stats[big, cv2.CC_STAT_AREA] / (h * w) * 100:.1f}%) "
                       "— 카메라가 빈 안을 보고 있나(바닥 검정 + 부품만 색) · 멀면 빈이 작게 보인다")
    pick = center_lab if center_lab in cand else max(cand, key=lambda i: stats[i, cv2.CC_STAT_AREA])
    x, y, bw, bh = (int(stats[pick, k]) for k in (cv2.CC_STAT_LEFT, cv2.CC_STAT_TOP, cv2.CC_STAT_WIDTH, cv2.CC_STAT_HEIGHT))
    inc = [x + margin_px, y + margin_px, x + bw - margin_px, y + bh - margin_px]
    inc = _rect(inc, "include(proposed)")
    area_frac = float(stats[pick, cv2.CC_STAT_AREA]) / (h * w)
    return {"schema": SCHEMA, "include": inc, "exclude": [],
            "notes": f"propose: 무효 덩어리 bbox(화면 {area_frac*100:.1f}%) 안쪽 {margin_px}px · "
                     f"{'중앙 포함' if pick == center_lab else '최대 덩어리(중앙은 유효 픽셀 위)'}",
            "_area_frac": area_frac}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _self_test() -> int:
    ok = True
    def check(name: str, cond: bool) -> None:
        nonlocal ok
        print(("  🟢 " if cond else "  🔴 ") + name)
        ok = ok and bool(cond)
    h, w = FRAME_HW
    # 합성: 빈 바닥 무효(0) · 벽 유효(raw 2000≈305mm) · 부품 유효(raw 2800≈427mm) · 왼쪽 그리퍼 띠 유효(raw 900)
    f = np.full((h, w), 2000, np.uint16)
    f[40:440, 200:600] = 0
    f[:, :110] = 900; f[:, 740:] = 900
    f[200:240, 400:440] = 2800
    print("① propose = 합성 빈(200~600 × 40~440)")
    r = propose_roi(f)
    check(f"include 가 벽 안쪽을 찾는다 {r['include']}", r["include"] == [200 + PROPOSE_SEAL_PX + PROPOSE_MARGIN_PX, 40 + PROPOSE_SEAL_PX + PROPOSE_MARGIN_PX, 600 - PROPOSE_SEAL_PX - PROPOSE_MARGIN_PX, 440 - PROPOSE_SEAL_PX - PROPOSE_MARGIN_PX])
    m = apply_roi(f, r)
    check("밖(벽·띠)은 0 · 안(부품)은 그대로", m[0, 0] == 0 and m[300, 50] == 0 and m[220, 420] == 2800 and (m[:, :r["include"][0]] == 0).all())
    st = roi_stats(f, r)
    check(f"유효% 가 내려간다 {st['before']['valid_pct']} → {st['after']['valid_pct']}", st["after"]["valid_pct"] < st["before"]["valid_pct"])
    print("② exclude")
    r2 = {**r, "exclude": [[395, 195, 445, 245]]}
    check("exclude 안의 부품이 0 이 된다", apply_roi(f, r2)[220, 420] == 0)
    print("③ 그물")
    bad = False
    try:
        apply_roi(np.zeros((960, 848), np.uint16), r)
    except RoiError:
        bad = True
    check("(960,848) 은 거부(Intensity 동봉 9/16 함정)", bad)
    bad = False
    try:
        load_roi(Path(__file__))  # 아무 파일이나
    except Exception:
        bad = True
    check("엉뚱한 파일은 거부", bad)
    check("벽이 없는 전부-무효 프레임은 전체를 제안", propose_roi(np.zeros((h, w), np.uint16))["include"] == [PROPOSE_MARGIN_PX, PROPOSE_MARGIN_PX, w - PROPOSE_MARGIN_PX, h - PROPOSE_MARGIN_PX])
    print("④ 틈 메우기 — 벽 띠에 8px 구멍이 있어도 밖으로 새지 않는다")
    g = f.copy(); g[230:238, 598:604] = 0; g[436:444, 300:308] = 0     # 오른쪽 벽·아래 벽에 구멍
    rg = propose_roi(g)
    check(f"구멍이 있어도 같은 사각형 {rg['include']}", rg["include"] == r["include"])
    print("  ✅ 통과" if ok else "  🔴 실패")
    return 0 if ok else 1


def main() -> int:
    from bin_picking.src.utils.console_utf8 import enable_utf8_console
    enable_utf8_console()
    ap = argparse.ArgumentParser(description="ROI 마스크 — 빈 안쪽만 남긴다 (propose / apply / stats)")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("propose", help="프레임에서 빈 안쪽 사각형을 자동 제안 → JSON")
    p.add_argument("--depth", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--exclude", action="append", default=[], metavar="u0,v0,u1,v1", help="빈 안인데 못 쓰는 자리(여러 번 가능)")
    p.add_argument("--notes", default="")
    p.add_argument("--capture-pose", type=float, nargs=6, metavar=("X", "Y", "Z", "RX", "RY", "RZ"), help="이 ROI 가 유효한 P_capture(기록용)")
    p.add_argument("--margin", type=int, default=PROPOSE_MARGIN_PX)
    a_ = sub.add_parser("apply", help="npy 에 ROI 적용 → <stem>_roi.npy")
    a_.add_argument("--depth", required=True, type=Path)
    a_.add_argument("--roi", required=True, type=Path)
    a_.add_argument("--out", type=Path, default=None)
    s = sub.add_parser("stats", help="마스크 전/후 숫자만")
    s.add_argument("--depth", required=True, type=Path)
    s.add_argument("--roi", required=True, type=Path)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return _self_test()
    if a.cmd == "propose":
        raw = np.load(a.depth)
        roi = propose_roi(raw, margin_px=a.margin)
        roi["exclude"] = [_rect([float(x) for x in e.split(",")], "exclude") for e in a.exclude]
        roi["notes"] = (a.notes + " · " if a.notes else "") + roi["notes"]
        roi["source"] = str(a.depth)
        roi["capture_pose"] = a.capture_pose
        out = save_roi(roi, a.out)
        st = roi_stats(raw, roi)
        print(f"include {roi['include']} · exclude {roi['exclude']}")
        print(f"유효% {st['before']['valid_pct']} → {st['after']['valid_pct']} · 크롭 대역% {st['before']['crop_band_pct']} → {st['after']['crop_band_pct']}")
        print(f"저장 {out}")
        if st["after"]["valid_pct"] > 25:
            print("⚠️ 마스크 뒤에도 유효 25% 초과 — 빈 안에 무언가 많이 보인다(부품이 너무 많거나 바닥이 반사)")
        return 0
    if a.cmd == "apply":
        out, st = apply_to_file(a.depth, a.roi, a.out)
        print(f"저장 {out} · 유효% {st['before']['valid_pct']} → {st['after']['valid_pct']} · 크롭 대역% {st['before']['crop_band_pct']} → {st['after']['crop_band_pct']}")
        return 0
    if a.cmd == "stats":
        st = roi_stats(np.load(a.depth), load_roi(a.roi))
        print(json.dumps(st, ensure_ascii=False))
        return 0
    ap.error("propose / apply / stats / --self-test")
    return 2


if __name__ == "__main__":
    sys.exit(main())
