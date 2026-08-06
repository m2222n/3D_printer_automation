#!/usr/bin/env python3
"""STL 27종 → 라벨링용 부품 도감(atlas) 생성.

⭐ 왜 필요한가
   라벨링에서 진짜 어려운 것은 폴리곤을 그리는 것이 아니라 **"이게 어느 부품인가"**다.
   특히 `sol_block` 4종은 실측 라벨 기준 크기가 86~90px로 사실상 같고
   (`01_sol_block_a` 90 / `02_sol_block_b` 90 / `03_sol_block_front` 88 /
   `06_sol_block_back` 86), 이름만 봐서는 구분할 수 없다.

   🚨 라벨을 잘못 달면 F1이 무의미해진다 — 모델이 맞았는데 라벨이 틀려서
   오답으로 잡히면, 그 결과로 "cross-session 폭락"이라는 잘못된 판단을 내리고
   8월 계획을 틀게 된다. 그래서 **눈으로 대조할 기준**이 있어야 한다.

⭐ 무엇을 만드나
   각 STL을 **top-down(카메라와 같은 시선)** 으로 렌더링해 부품별 카드를 만든다.
   depth처럼 보이게 높이를 색으로 칠하므로, 촬영 이미지와 같은 방식으로 보인다.
   실측 라벨에서 뽑은 화면상 크기(px)를 같이 적어 크기 대조도 가능하게 한다.

   ⚠️ 렌더는 "위에서 본 실루엣"이므로 실제 촬영에서 부품이 뒤집혀 있거나
      기울어져 있으면 다르게 보인다. 절대 기준이 아니라 **후보를 좁히는 도구**다.

사용법:
    python make_part_atlas.py --out-dir /data/jtm/blaze_crosssession_0731/atlas
"""

import argparse
import glob
import os
import struct

import cv2
import numpy as np


def load_stl(path: str) -> np.ndarray:
    """STL(바이너리/ASCII 자동판별) → (N,3,3) 삼각형 배열. trimesh 없이 직접 파싱."""
    with open(path, "rb") as f:
        head = f.read(84)
        f.seek(0)
        raw = f.read()

    # ASCII 판별: 헤더가 'solid'로 시작하고 'facet'이 텍스트로 들어있는지
    is_ascii = head[:5].lower() == b"solid" and b"facet" in raw[:2048].lower()

    if is_ascii:
        verts = []
        for line in raw.decode("utf-8", "ignore").splitlines():
            parts = line.split()
            if len(parts) == 4 and parts[0] == "vertex":
                verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
        tris = np.array(verts, dtype=np.float32)
        n = len(tris) // 3
        return tris[: n * 3].reshape(n, 3, 3)

    # 바이너리: 80B 헤더 + uint32 개수 + (12 float + uint16) * n
    n = struct.unpack("<I", raw[80:84])[0]
    out = np.zeros((n, 3, 3), dtype=np.float32)
    off = 84
    for i in range(n):
        vals = struct.unpack("<12f", raw[off:off + 48])
        out[i, 0] = vals[3:6]
        out[i, 1] = vals[6:9]
        out[i, 2] = vals[9:12]
        off += 50
    return out


def lay_flat(tris: np.ndarray) -> np.ndarray:
    """가장 넓은 면이 위를 향하도록 세운 부품을 눕힌다.

    🚨 왜 필요한가: STL 원점 자세는 CAD 설계 기준이라 부품이 **세워져 있는** 경우가
       많다(`bracket_sen_1`은 15x56x53mm로 얇은 면이 정면). 그 상태로 top-down
       렌더를 하면 **막대기처럼 보여** 실제 촬영 모습과 전혀 다르다.

    ⭐ 실제 촬영에서 부품은 빈 바닥에 **가장 안정적인 자세 = 가장 넓은 면을 아래로**
       놓인다. 그러면 카메라(위)가 보는 것도 그 넓은 면이다.
       → bbox에서 **가장 짧은 축을 z(높이)로** 돌려놓으면 그 상태가 된다.
    """
    ext = tris.reshape(-1, 3)
    dims = ext.max(axis=0) - ext.min(axis=0)
    shortest = int(np.argmin(dims))
    if shortest == 2:
        return tris                       # 이미 눕혀져 있음
    order = [0, 1, 2]
    order[2], order[shortest] = order[shortest], order[2]
    return tris[:, :, order]


def render_topdown(tris: np.ndarray, size: int = 300, margin: int = 18) -> np.ndarray:
    """위에서 내려다본 높이맵을 렌더 → depth처럼 컬러맵.

    z-buffer 방식: 각 삼각형을 xy 평면에 투영해 채우고, **가장 높은 z**를 남긴다.
    (top-down 카메라가 보는 면이 곧 가장 높은 면이다)
    """
    xy = tris[:, :, :2].reshape(-1, 2)
    lo, hi = xy.min(axis=0), xy.max(axis=0)
    span = max((hi - lo).max(), 1e-6)
    scale = (size - 2 * margin) / span

    zbuf = np.full((size, size), -np.inf, dtype=np.float32)
    for tri in tris:
        pts = ((tri[:, :2] - lo) * scale + margin).astype(np.int32)
        # ⭐ y를 뒤집어 이미지 좌표계(위→아래)로 맞춘다
        pts[:, 1] = size - 1 - pts[:, 1]
        zc = float(tri[:, 2].mean())
        mask = np.zeros((size, size), np.uint8)
        cv2.fillConvexPoly(mask, pts, 1)
        sel = mask.astype(bool)
        np.maximum(zbuf, np.where(sel, zc, -np.inf), out=zbuf)

    filled = np.isfinite(zbuf)
    if not filled.any():
        return np.zeros((size, size, 3), np.uint8)

    zv = zbuf[filled]
    z0, z1 = zv.min(), zv.max()
    norm = np.zeros((size, size), np.float32)
    norm[filled] = (zbuf[filled] - z0) / max(z1 - z0, 1e-6)
    vis = (255 * (1 - norm)).astype(np.uint8)
    color = cv2.applyColorMap(vis, cv2.COLORMAP_TURBO)
    color[~filled] = (0, 0, 0)
    return color


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    cad_default = os.path.abspath(os.path.join(here, "..", "..", "models", "cad"))

    ap = argparse.ArgumentParser()
    ap.add_argument("--cad-dir", default=cad_default)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--labels", default=None,
                    help="labels.txt (여기 있는 27종만 그린다). 없으면 STL 전부")
    ap.add_argument("--cell", type=int, default=300)
    ap.add_argument("--cols", type=int, default=5)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    wanted = None
    if args.labels and os.path.exists(args.labels):
        with open(args.labels) as f:
            wanted = {ln.strip() for ln in f
                      if ln.strip() and not ln.startswith(("__", "_b"))}

    # 실측 라벨에서 뽑은 화면상 크기(px) — 크기 대조용. 없는 것은 표시 생략.
    measured = {
        "08_r_guide_a": (276, 126), "r_guide_a_l": (233, 89),
        "07_guide_paper_l": (182, 128), "17_mks_holder": (180, 134),
        "09_guide_paper_r": (178, 92), "r_guide_a_r": (170, 92),
        "18_button_function_niro": (163, 78),
        "guide_paper_roll_cover_left": (108, 72),
        "guide_paper_roll_cover_right": (106, 58),
        "bracket_sen_1": (97, 76), "01_sol_block_a": (90, 76),
        "plate_e": (90, 82), "02_sol_block_b": (90, 74),
        "03_sol_block_front": (88, 86), "06_sol_block_back": (86, 80),
        "13_variant": (70, 60), "13_x2_bcf8ccb4": (68, 54),
        "16_cam_f_bracket": (64, 46), "14_13": (62, 58),
        "bracket_sensor1": (62, 42), "main_body": (50, 44),
        "15_roller_bracket": (46, 34), "bracket_sensor2": (40, 22),
        "brkt_switch": (40, 36), "top_inner_sheet": (32, 30),
        "11_sw_block": (27, 20), "bracket_case": (14, 12),
    }

    paths = sorted(glob.glob(os.path.join(args.cad_dir, "*.stl")))
    cards = []
    for p in paths:
        name = os.path.splitext(os.path.basename(p))[0]
        if wanted is not None and name not in wanted:
            continue
        try:
            tris = load_stl(p)
        except Exception as e:  # 깨진 STL은 건너뛰되 조용히 넘기지 않는다
            print(f"  ⚠️ 읽기 실패 {name}: {e}")
            continue
        if len(tris) == 0:
            print(f"  ⚠️ 삼각형 0개 {name}")
            continue

        tris = lay_flat(tris)             # ⭐ 촬영과 같은 자세로 눕힌 뒤 렌더
        img = render_topdown(tris, size=args.cell)
        ext = tris.reshape(-1, 3)
        dims = ext.max(axis=0) - ext.min(axis=0)
        cards.append((name, img, dims))
        cv2.imwrite(os.path.join(args.out_dir, f"{name}.png"), img)

    if not cards:
        raise SystemExit("🔴 렌더한 부품이 없음. --cad-dir 확인")

    # 큰 것부터 = 화면에서 눈에 띄는 순서
    cards.sort(key=lambda c: -max(c[2][0], c[2][1]))

    cell, cols = args.cell, args.cols
    label_h = 62
    rows = (len(cards) + cols - 1) // cols
    sheet = np.full((rows * (cell + label_h), cols * cell, 3), 24, np.uint8)

    for i, (name, img, dims) in enumerate(cards):
        r, c = divmod(i, cols)
        y, x = r * (cell + label_h), c * cell
        sheet[y:y + cell, x:x + cell] = img
        px = measured.get(name)
        # ⚠️ cv2.putText는 한글을 못 그린다(`??????`로 나옴) → 영문·숫자만 쓴다
        fs = 0.52 if len(name) <= 24 else 0.40   # 긴 이름은 글자를 줄여 통째로 보여준다
        l2 = f"{dims[0]:.0f}x{dims[1]:.0f}x{dims[2]:.0f}mm"
        if px:
            l2 += f"   screen {px[0]}x{px[1]}px"
        cv2.putText(sheet, name, (x + 6, y + cell + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(sheet, l2, (x + 6, y + cell + 44),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (150, 220, 150), 1, cv2.LINE_AA)

    out = os.path.join(args.out_dir, "_ATLAS.png")
    cv2.imwrite(out, sheet)
    print(f"\n✅ 부품 {len(cards)}종 → {out}")
    print("   (개별 PNG도 같은 폴더에 있음)")
    print("\n⚠️ 렌더는 '위에서 본 모습'이다. 촬영에서 뒤집히거나 기울면 다르게 보인다")
    print("   → 절대 기준이 아니라 **후보를 좁히는 도구**로 쓸 것")


if __name__ == "__main__":
    main()
