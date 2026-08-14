#!/usr/bin/env python3
"""27종 STL 실측 → 그리퍼 파지 가능성 판정 (방침: 못 잡는 것은 공정 대상에서 제외).

⭐⭐ 전제 = 부품은 빈에 **눕혀 있다** (태민님 확정, 2026-08-06).
  빈 안 무작위 적재는 **안정 자세로 수렴**한다 — 가장 얇은 면이 바닥에 닿는다.
  (19x19x1mm 판이 1mm 면으로 서 있을 수는 없다. 넘어진다.)
  ⇒ 그리퍼는 위에서 내려와 **수평면의 짧은 변**을 물고,
     조우는 부품 옆의 **부품 높이만큼의 공간**으로 진입해야 한다.
  ⇒ "세워서 두께를 문다"는 경로는 이 전제에서 **존재하지 않는다.**

  판정에 쓰는 두 값:
    span_flat  = 두 번째로 작은 변 (= sorted(dims)[1])  ← ⭐ 그리퍼가 무는 변
    span_thin  = 가장 작은 변      (= sorted(dims)[0])  ← ⭐ 눕혔을 때 부품 높이

  ⚠️ 그래서 판정 기준은 두 개다: **벌림이 스트로크 안인가** + **조우가 진입할 높이가 있는가**.
     후자가 JEGB에서 유일하게 남은 실질 제약이다(0mm까지 닫히므로 얇아서 못 무는 경우는 없다).

  📌 참고 = 기존 `grasp_database.yaml`의 `gripper_width_mm`를 전수 대조하니
     20종은 중간변+여유, 7종은 최소변+여유로 **방향이 섞여 있었다**(`01_sol_block_a` 20mm
     = 11.5+여유). 즉 DB는 눕힘 전제로 일관되게 작성된 것이 아니므로,
     이 판정 결과와 DB 값이 어긋나는 7종은 **DB 쪽을 티칭 때 교정**해야 한다.

✅ 그리퍼 확정 (2026-08-06, 협력사 회신) = **주강로보테크 JEGB-4285P-3MA**
   모델명 해독: JEGB(전동 평행 그리퍼) - 42(본체 크기) 85(**스트로크 85mm**) P / 3MA(옵션)
   시리즈 사양(JEGB-4140 공개 자료 기준, 85형은 스트로크만 다름):
     - 개폐 범위: **0 ~ 스트로크**  ⭐ 완전히 닫힌다 = **최소 벌림 제약이 없다**
     - 파지력: **15~150N 프로그래머블**  (DB 안전상한 40N 이내로 쓸 수 있다)
     - 통신: RS-485 half-duplex + 디지털 I/O (입력 5 / 출력 3)
     - 위치·속도·힘 프로그래머블, **최대 15점** 사전 등록 · Self-lock(전원 차단 시 낙하 방지)
     - 자중 1.25kg(140형) · 권장 페이로드 3kg

🚨🚨 이 사양이 판정 기준을 뒤집었다 — 8/6 오전에 세운 `--min-span 10` 전제는 무효다:
   "최소 벌림보다 얇으면 못 집는다"는 **평행 그리퍼 일반론이었고 이 제품엔 안 맞는다**
   (0mm까지 닫히므로 얇아서 못 집는 경우가 없다).
   ⇒ **진짜 제약은 두 개뿐**:
     ① **최대 85mm** — 이보다 두꺼운 방향으로는 물 수 없다
     ② **손가락(조우) 두께 + 진입 공간** — 얇은 판재는 벌림과 무관하게
        손가락이 부품 옆으로 들어가지 못한다. ⭐이것이 유일하게 남은 실질 제약이다.

⚠️ [미확인] 2건 = ①**조우(finger) 실물 형상·두께**(부품별 맞춤 제작 대상)
   ②**JEGB-4285P의 자중**(140형 1.25kg 이하 추정) → 로봇 TCP payload 설정 갱신 확인 필요

사용법:
  python survey_graspability.py                             # JEGB-4285 확정 사양
  python survey_graspability.py --min-height 8              # 조우가 두꺼우면
  python survey_graspability.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np

STL_DIR_DEFAULT = "/home/jtm/kaist_render/stl"

# ⭐⭐ 사람이 내린 결정으로 계산 판정을 덮어쓴다 (2026-08-06 태민님).
#   계산은 경계선을 "실물 확인 필요"로만 낼 수 있고, **빼느냐 마느냐는 공정 결정**이다.
#   🚨 이것을 코드에 박아두지 않으면 스크립트를 다시 돌릴 때 조용히 되돌아간다.
#   (`main_body`는 계산상 needs_review였으나 태민님이 제외로 확정.
#    나머지 경계선 4종은 "잠시 보류" = needs_review 유지.)
MANUAL_OVERRIDES: dict[str, tuple[str, str]] = {
    "main_body": ("not_pickable", "태민님 확정(8/6) — 경계선이었으나 제외로 결정"),
    # ⭐ 8/14 실물 확인 — 보류(needs_review) 4종 중 2종을 제외로 확정했다.
    #    배경: 조우(finger) 실물 두께가 제조사 비공개라 사양서로는 판정 불가
    #    (웹 검색·jrtfa.com 확인 결과 JEGB-4285 조우 규격 미공개).
    #    ⇒ 계산으로 못 가르는 자리라 실물을 본 사람의 판단을 기준으로 삼는다.
    "11_sw_block": ("not_pickable", "태민님 실물 확인(8/14) — 너무 작다(무는 변 7.1mm)"),
    "17_mks_holder": ("not_pickable", "태민님 실물 확인(8/14) — 크고 높이가 없다"
                                      "(무는 변 82.5mm = 스트로크 85mm에 여유 2.5mm)"),
    # 🟢 유지 = 13_variant · 14_13
    #    무는 변 42.2mm로 스트로크의 절반이라 벌림 여유가 크고, 걸린 것은 높이 6.0mm 하나뿐.
    #    태민님 실물 판단도 "집을 만해 보인다" → needs_review 유지(좌표 전송은 아직 X).
}



# ---------------------------------------------------------------------------
# STL 파싱 (trimesh 없이 — depth_venv에 없고 추가 설치는 불필요)
# ---------------------------------------------------------------------------
def load_stl_vertices(path: Path) -> np.ndarray:
    """STL(바이너리/ASCII 자동 판별) → (N,3) 정점 배열."""
    raw = path.read_bytes()
    if len(raw) < 84:
        raise ValueError(f"{path.name}: 파일이 너무 작다 ({len(raw)} bytes)")

    # 바이너리 판정: 헤더 80바이트 뒤 삼각형 개수와 실제 파일 크기가 맞는가
    n_tri = struct.unpack("<I", raw[80:84])[0]
    if 84 + n_tri * 50 == len(raw) and n_tri > 0:
        # 바이너리: 삼각형당 50바이트 = 법선 12 + 정점 36 + attr 2
        data = np.frombuffer(raw, dtype=np.uint8, count=n_tri * 50, offset=84)
        data = data.reshape(n_tri, 50)
        verts = np.zeros((n_tri, 3, 3), dtype=np.float32)
        for i in range(3):
            off = 12 + i * 12
            verts[:, i, :] = data[:, off:off + 12].copy().view(np.float32).reshape(-1, 3)
        return verts.reshape(-1, 3).astype(np.float64)

    # ASCII 폴백
    verts = []
    for line in raw.decode("utf-8", errors="ignore").splitlines():
        s = line.strip()
        if s.startswith("vertex"):
            parts = s.split()
            if len(parts) >= 4:
                verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
    if not verts:
        raise ValueError(f"{path.name}: 정점을 못 읽었다 (바이너리도 ASCII도 아님)")
    return np.asarray(verts, dtype=np.float64)


def measure(path: Path) -> dict:
    """축정렬 bbox 실측 → 두 파지 방향의 후보 변을 함께 산출."""
    v = load_stl_vertices(path)
    dims = (v.max(axis=0) - v.min(axis=0)).astype(float)  # (dx, dy, dz)
    srt = sorted(dims)  # 오름차순
    return {
        "name": path.stem,
        "bbox_mm": [round(float(d), 2) for d in dims],
        "dims_sorted_mm": [round(float(d), 2) for d in srt],
        # ⭐ 눕힘 전제: 최소변이 높이가 되고, 두 번째 변을 그리퍼가 문다
        "span_thin_mm": round(float(srt[0]), 2),  # 눕혔을 때 부품 높이 (조우 진입 공간)
        "span_flat_mm": round(float(srt[1]), 2),  # 그리퍼가 무는 변
        "long_mm": round(float(srt[2]), 2),
        "n_vertices": int(len(v)),
    }


# ---------------------------------------------------------------------------
# 판정
# ---------------------------------------------------------------------------
def classify(m: dict, min_span: float, max_span: float, min_height: float) -> dict:
    """3분류 판정. 이유를 반드시 함께 돌려준다(보고 근거).

    ⭐ 원칙 = 두 파지 방향 중 하나라도 성립하면 제외하지 않는다.
       제외는 "어느 방향으로도 안 된다"가 확실할 때만.
    """
    height = m["span_thin_mm"]  # 눕혔을 때 부품 높이 (= 최소변)
    span = m["span_flat_mm"]    # 눕혔을 때 그리퍼가 무는 변 (= 두 번째로 작은 변)
    reasons: list[str] = []

    # ⭐⭐ 전제 = 부품은 빈에 **눕혀 있다**(태민님 확정, 8/6).
    #   무작위 적재는 안정 자세로 수렴하므로 가장 얇은 면이 바닥에 닿는다.
    #   ⇒ 그리퍼는 위에서 내려와 **수평면의 짧은 변(span)** 을 물고,
    #      조우는 부품 옆으로 **높이(height)** 만큼의 공간에 진입해야 한다.
    #   ⇒ "세워서 두께를 문다"는 경로는 이 전제에서 존재하지 않는다.

    # ① 벌림: 무는 변이 스트로크 안에 들어와야 한다
    if span > max_span:
        reasons.append(
            f"벌림 초과: 짧은 변 {span}mm > 스트로크 {max_span}mm "
            "(눕힌 자세에서 이 변을 물 수 없다)"
        )
    elif span < min_span:
        reasons.append(f"벌림 미달: 짧은 변 {span}mm < 최소 벌림 {min_span}mm")

    # ② 진입: 조우가 부품 옆으로 들어갈 높이가 있어야 한다
    #   🚨 이것이 JEGB에서 **유일하게 남은 실질 제약**이다
    #      (0mm까지 닫히므로 "얇아서 못 문다"는 경우는 없다).
    if height < min_height:
        reasons.append(
            f"조우 진입 불가: 눕힌 높이 {height}mm < {min_height}mm "
            "(조우가 부품 옆으로 들어갈 공간이 없어 바닥을 긁는다)"
        )

    if reasons:
        verdict = "not_pickable"
    elif height < min_height * 1.5 or span > max_span * 0.9:
        # 경계선 = 계산상 되지만 여유가 작아 실물 확인이 필요하다
        verdict = "needs_review"
        reasons.append(
            f"경계선: 높이 {height}mm(하한 {min_height}) · 벌림 {span}mm(상한 {max_span})"
            " → 여유가 작아 실물 파지 확인 필요"
        )
    else:
        verdict = "pickable"
        reasons.append(
            f"눕힌 자세에서 짧은 변 {span}mm를 물고 높이 {height}mm로 조우 진입 가능"
        )

    # ⭐ 사람 결정이 계산을 덮어쓴다. 덮어썼다는 사실을 결과에 남긴다(조용히 바꾸지 않는다).
    ov = MANUAL_OVERRIDES.get(m["name"])
    if ov and ov[0] != verdict:
        reasons.insert(0, f"⭐ 수동 확정 '{ov[0]}' (계산 판정은 '{verdict}') — {ov[1]}")
        verdict = ov[0]

    return {**m, "verdict": verdict, "reasons": reasons}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stl-dir", default=STL_DIR_DEFAULT)
    # ✅ JEGB-4285P-3MA 확정 사양(2026-08-06). 0mm까지 닫히므로 최소 벌림 제약이 없다.
    ap.add_argument("--min-span", type=float, default=0.0,
                    help="그리퍼 최소 파지 폭 mm (JEGB는 0까지 닫혀 제약 없음)")
    ap.add_argument("--max-span", type=float, default=85.0,
                    help="그리퍼 스트로크 mm (JEGB-4285 = 85mm)")
    ap.add_argument("--min-height", type=float, default=5.0,
                    help="조우가 부품 옆으로 진입하는 데 필요한 최소 부품 높이 mm "
                         "([미확인] 조우 실물 확인 후 조정)")
    ap.add_argument("--json", default=None, help="결과 JSON 저장 경로")
    args = ap.parse_args()

    stl_dir = Path(args.stl_dir)
    files = sorted(stl_dir.glob("*.stl"))
    if not files:
        print(f"🔴 STL을 못 찾음: {stl_dir}", file=sys.stderr)
        return 1

    print("=" * 100)
    print(f"{len(files)}종 STL 파지 가능성 실측 — 그리퍼 JEGB-4285P-3MA (주강로보테크)")
    print(f"  전제: 부품은 빈에 **눕혀 있다** / 스트로크 {args.min_span}~{args.max_span}mm · "
          f"조우 진입 최소 높이 {args.min_height}mm")
    print("  ⚠️ 조우(finger) 실물 두께가 [미확인] → --min-height 로 재판정할 것")
    print("=" * 100)

    results = []
    for f in files:
        try:
            results.append(classify(measure(f), args.min_span, args.max_span, args.min_height))
        except Exception as e:  # 파싱 실패를 조용히 넘기지 않는다
            print(f"🔴 {f.name}: 실측 실패 — {e}", file=sys.stderr)
            return 1

    order = {"not_pickable": 0, "needs_review": 1, "pickable": 2}
    results.sort(key=lambda r: (order[r["verdict"]], r["span_thin_mm"]))

    icon = {"pickable": "🟢", "needs_review": "🟡", "not_pickable": "🔴"}
    print(f"\n{'':2s} {'부품명':<30s} {'bbox (mm)':<26s} {'무는변':>7s} {'높이':>6s}  판정")
    print("-" * 100)
    for r in results:
        b = r["bbox_mm"]
        bbox_s = f"{b[0]:.1f} x {b[1]:.1f} x {b[2]:.1f}"
        print(f"{icon[r['verdict']]} {r['name']:<30s} {bbox_s:<26s} "
              f"{r['span_flat_mm']:>7.1f} {r['span_thin_mm']:>6.1f}  {r['verdict']}")

    print("\n" + "=" * 100)
    for v in ("not_pickable", "needs_review", "pickable"):
        sel = [r for r in results if r["verdict"] == v]
        print(f"{icon[v]} {v}: {len(sel)}종")
        for r in sel:
            for why in r["reasons"]:
                print(f"     - {r['name']}: {why}")
    print("=" * 100)

    n_excl = sum(1 for r in results if r["verdict"] == "not_pickable")
    n_rev = sum(1 for r in results if r["verdict"] == "needs_review")
    print(f"\n📊 총 {len(results)}종 → 제외 후보 {n_excl}종 · 검토 {n_rev}종 · "
          f"공정 대상 {len(results) - n_excl}종")

    if args.json:
        out = {
            "criteria": {
                "min_span_mm": args.min_span,
                "max_span_mm": args.max_span,
                "min_height_mm": args.min_height,
                "note": "기준선 [미확인] — 그리퍼 사양 확정 후 재실행",
            },
            "method": (
                "파지 방향 2후보를 함께 본다. span_thin=최소변(세워 두께를 뭄) / "
                "span_flat=두 번째 변(눕혀 짧은 변을 뭄, 이때 손가락 진입 높이=span_thin 필요). "
                "제외는 두 방향 모두 불가할 때만 확정한다. "
                "근거=grasp_database.yaml 27종 대조에서 DB가 20종은 중간변+여유, "
                "7종은 최소변+여유로 설계돼 방향이 부품마다 달랐다."
            ),
            "parts": results,
            "summary": {
                "total": len(results),
                "not_pickable": n_excl,
                "needs_review": n_rev,
                "pickable": len(results) - n_excl - n_rev,
            },
        }
        Path(args.json).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"📄 저장: {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
