#!/usr/bin/env python3
"""depth npy → 라벨링용 PNG 생성 (labelme로 라벨 그릴 화면).

⭐ 왜 필요한가
   촬영 스크립트가 저장하는 PNG는 **HUD 오버레이가 박힌 화면**이다
   (`saved=0/30`·`BAND`·`DIST` 텍스트 + crop 흰 박스 + 화면 밖 잡영).
   그걸 그대로 라벨링하면 ①텍스트·박스가 부품을 가리고 ②학습셋 라벨을
   그린 화면과 컬러맵이 달라 경계 판단 기준이 어긋난다.

   이 스크립트는 학습셋 `label_png/`를 만든 것과 **동일한 방식**으로
   npy에서 순수 depth 컬러맵만 다시 그린다
   (`blaze_capture_100.py:colorize` + `--scale 2.0` 동일).

🔑 스케일 2배가 규약이다
   npy 848x480 → PNG 1696x960. 평가기(`real_labelme.py:162-165`)가 라벨 JSON의
   `imageWidth/imageHeight`를 읽어 자동으로 되돌리므로 2배가 유지되어야 한다.

사용법:
    python make_label_png.py --npy-dir /data/jtm/blaze_crosssession_0731 \
                             --out-dir /data/jtm/blaze_crosssession_0731/label_png
"""

import argparse
import glob
import os
import sys

import cv2
import numpy as np

# 🚨 depth 단위는 반드시 단일 출처를 경유한다 — 자체 변환 금지.
#    이 버그를 닷새에 다섯 번 밟았고, 전부 "조용히 그럴싸한 값"이었다.
#    ⚠️ to_mm은 **(배열, 설명문자열) 튜플**을 돌려준다.
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from bin_picking.src.acquisition.depth_units import to_mm  # noqa: E402


# 학습셋 label_png와 동일 (blaze_capture_100.py:100-109)
def colorize(depth: np.ndarray) -> np.ndarray:
    """유효 depth의 2~98 퍼센타일로 정규화 후 TURBO 컬러맵. 무효(0)는 검정."""
    valid = depth[depth > 0]
    if valid.size == 0:
        return np.zeros((*depth.shape, 3), np.uint8)
    lo, hi = np.percentile(valid, [2, 98])
    norm = np.clip((depth.astype(np.float32) - lo) / max(hi - lo, 1), 0, 1)
    vis = (255 * (1 - norm)).astype(np.uint8)
    color = cv2.applyColorMap(vis, cv2.COLORMAP_TURBO)
    color[depth == 0] = (0, 0, 0)
    return color


def colorize_band(depth_mm: np.ndarray, near: float, far: float) -> np.ndarray:
    """부품 대역(near~far mm)만으로 정규화한다 — 라벨링 가시성 전용.

    🚨 왜 별도 함수인가: `colorize()`는 화면 전체의 2~98 퍼센타일을 쓴다.
       cross-session 촬영분은 **빈 밖 원거리 물체(벽·바닥)가 프레임에 들어와**
       그 값들이 퍼센타일을 끌어당겨 **부품 대비가 눌린다**(부품이 전부 파랗게
       나와 경계가 안 보임). 학습셋은 원거리 잡영이 거의 없어 문제가 없었다.

    → 부품이 있는 400~600mm만 색 범위로 쓰고 대역 밖은 검정으로 눌러서
      학습셋과 같은 "노랑·주황 부품 / 검은 배경" 화면을 만든다.
      ⭐ 라벨 좌표에는 영향 없다(색만 바뀜).
    """
    band = (depth_mm >= near) & (depth_mm <= far)
    if not band.any():
        return colorize(depth_mm)
    norm = np.clip((depth_mm.astype(np.float32) - near) / max(far - near, 1), 0, 1)
    vis = (255 * (1 - norm)).astype(np.uint8)
    color = cv2.applyColorMap(vis, cv2.COLORMAP_TURBO)
    color[~band] = (0, 0, 0)          # 대역 밖(원거리 잡영·무효) 전부 검정
    return color


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--npy-dir", required=True, help="shot_*.npy 가 있는 디렉토리")
    ap.add_argument("--out-dir", required=True, help="PNG 저장 위치")
    ap.add_argument("--scale", type=float, default=2.0,
                    help="npy 대비 PNG 배율. ⚠️ 학습셋 규약 2.0 유지")
    ap.add_argument("--glob", default="shot*.npy")
    ap.add_argument("--band", default="400,600",
                    help="부품 대역 near,far [mm]. 이 범위만 색을 쓴다(대비 확보). "
                         "'off' 로 주면 학습셋과 완전 동일한 전체 퍼센타일 방식")
    args = ap.parse_args()

    use_band = args.band.lower() != "off"
    if use_band:
        near, far = (float(v) for v in args.band.split(","))

    os.makedirs(args.out_dir, exist_ok=True)

    # npy가 디렉토리에 바로 있는 경우와 npy/ 하위 모두 대응
    files = sorted(glob.glob(os.path.join(args.npy_dir, args.glob)))
    if not files:
        files = sorted(glob.glob(os.path.join(args.npy_dir, "npy", args.glob)))
    if not files:
        raise SystemExit(f"🔴 {args.glob} 를 못 찾음: {args.npy_dir}")

    print(f"입력 {len(files)}장 → {args.out_dir}  (배율 {args.scale}x)")

    for i, path in enumerate(files, 1):
        depth = np.load(path)
        # 🚨 단위: 단일 출처 경유. to_mm은 (배열, 설명) 튜플을 돌려준다.
        depth_mm, note = to_mm(depth, verbose=False)
        color = colorize_band(depth_mm, near, far) if use_band else colorize(depth_mm)
        if args.scale != 1.0:
            h, w = color.shape[:2]
            color = cv2.resize(
                color,
                (int(round(w * args.scale)), int(round(h * args.scale))),
                interpolation=cv2.INTER_NEAREST,  # 경계 번짐 방지 = 라벨 정확도
            )
        stem = os.path.splitext(os.path.basename(path))[0]
        out = os.path.join(args.out_dir, f"{stem}.png")
        cv2.imwrite(out, color)
        if i == 1:
            print(f"  단위 변환: {note}")
        if i == 1 or i % 10 == 0 or i == len(files):
            band_px = int(((depth_mm >= near) & (depth_mm <= far)).sum()) if use_band else -1
            print(f"  [{i:3d}/{len(files)}] {stem}  npy{depth.shape} → png{color.shape[:2]}"
                  + (f"  부품대역 {band_px}px" if use_band else ""))

    print(f"\n✅ 완료: {len(files)}장")
    print("⏭️ 맥으로 받아 labelme 실행:")
    print(f"   labelme . --labels labels.txt --output ./labelme_json --nodata")


if __name__ == "__main__":
    main()
