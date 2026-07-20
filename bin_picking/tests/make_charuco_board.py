"""
ChArUco 보드 인쇄물 생성 (OpenCV 4.13 CharucoBoard API)
========================================================

ACE2 intrinsic 캘리브 / Blaze↔ACE2 extrinsic 정렬에 쓸 ChArUco 보드를
PNG(+선택적으로 벡터 없는 고해상 PNG)로 생성. A4/A3에 인쇄해서
**평평한 판(폼보드·아크릴)에 기포 없이 붙여** 사용 (휘면 캘리브 망침).

⚠️ 여기서 정한 (squares_x, squares_y, square_length_mm, marker_ratio, dict)를
   calibrate_ace2_intrinsics.py 에 **똑같이** 넘겨야 함. 값이 다르면 검출 0.

사용:
    # 기본: A4 가로, 7x5 칸, 한 칸 30mm (인쇄 후 자로 실측하여 --measured 로 정정)
    python bin_picking/tests/make_charuco_board.py --out viz_output/charuco_A4.png

    # A3 크게
    python bin_picking/tests/make_charuco_board.py \
        --squares-x 9 --squares-y 6 --square-mm 35 --out viz_output/charuco_A3.png

인쇄 팁:
- 프린터 "실제 크기 / 배율 100% / 여백맞춤 끄기"로 인쇄 (자동 축소 금지!)
- 인쇄 후 자로 한 칸 실제 길이 측정 → 캘리브 시 그 실측값을 square-mm 로 넘김
  (인쇄 배율이 1~2% 틀어져도 실측값 쓰면 캘리브 정확)

⭐ USB로 프린터에 가져가 인쇄할 때 = --pdf 옵션 권장:
    python bin_picking/tests/make_charuco_board.py --pdf --out viz_output/charuco_A4.pdf
  A4(210x297mm) 페이지 정중앙에 보드를 정확한 mm 크기로 앉힌 PDF 생성.
  PNG는 프린터가 못 읽거나 변환 시 확대되지만, 이 PDF는 A4에 딱 맞게 나옴.
  (프린터에서 "실제 크기/배율 100%"로 인쇄. 그래도 인쇄 후 자로 실측은 필수.)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

# 딕셔너리: 5x5 마커 250종 — A4 규모에 충분, 검출 안정적
_DICT = cv2.aruco.DICT_5X5_250


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--squares-x", type=int, default=7, help="가로 칸 수")
    ap.add_argument("--squares-y", type=int, default=5, help="세로 칸 수")
    ap.add_argument("--square-mm", type=float, default=30.0,
                    help="한 칸(검은/흰 사각형) 목표 길이 mm")
    ap.add_argument("--marker-ratio", type=float, default=0.75,
                    help="마커/사각형 길이 비 (0.7~0.8 권장)")
    ap.add_argument("--dpi", type=int, default=300, help="인쇄 해상도")
    ap.add_argument("--margin-mm", type=float, default=10.0, help="바깥 여백 mm")
    ap.add_argument("--out", type=Path, default=Path("viz_output/charuco_board.png"))
    ap.add_argument("--pdf", action="store_true",
                    help="A4 페이지에 실제 mm 크기로 앉힌 PDF 생성 (USB 인쇄용 권장)")
    args = ap.parse_args()

    square_m = args.square_mm / 1000.0
    marker_m = square_m * args.marker_ratio

    dictionary = cv2.aruco.getPredefinedDictionary(_DICT)
    board = cv2.aruco.CharucoBoard(
        (args.squares_x, args.squares_y), square_m, marker_m, dictionary
    )

    # mm → px (인쇄 실제 크기 보장)
    px_per_mm = args.dpi / 25.4
    board_w_mm = args.squares_x * args.square_mm
    board_h_mm = args.squares_y * args.square_mm
    margin_px = int(round(args.margin_mm * px_per_mm))
    img_w = int(round(board_w_mm * px_per_mm))
    img_h = int(round(board_h_mm * px_per_mm))

    board_img = board.generateImage((img_w, img_h), marginSize=0, borderBits=1)

    # 여백 추가 (흰색)
    canvas = np.full((img_h + 2 * margin_px, img_w + 2 * margin_px), 255, np.uint8)
    canvas[margin_px:margin_px + img_h, margin_px:margin_px + img_w] = board_img

    args.out.parent.mkdir(parents=True, exist_ok=True)

    if args.pdf:
        # A4(210x297mm) 페이지 정중앙에 보드를 실제 mm 크기로 앉힌 PDF.
        # board_img(=canvas)는 이미 args.dpi 기준 실제 mm 크기의 px 배열.
        from PIL import Image
        A4_W_MM, A4_H_MM = 210.0, 297.0
        page_w_px = int(round(A4_W_MM * px_per_mm))
        page_h_px = int(round(A4_H_MM * px_per_mm))
        if canvas.shape[1] > page_w_px or canvas.shape[0] > page_h_px:
            print(f"⚠️ 보드({board_w_mm:.0f}x{board_h_mm:.0f}mm)+여백이 A4보다 큼 → "
                  f"--square-mm 를 줄이거나 --margin-mm 낮추세요. (그래도 저장은 진행)")
        page = Image.new("L", (page_w_px, page_h_px), 255)
        board_pil = Image.fromarray(canvas)
        ox = max(0, (page_w_px - canvas.shape[1]) // 2)
        oy = max(0, (page_h_px - canvas.shape[0]) // 2)
        page.paste(board_pil, (ox, oy))
        # DPI 메타를 박아 저장 → 뷰어/프린터가 실제 크기(210x297mm)로 인식
        page.save(str(args.out), "PDF", resolution=float(args.dpi))
    else:
        cv2.imwrite(str(args.out), canvas)

    print(f"✅ 저장: {args.out}")
    print(f"   보드: {args.squares_x}x{args.squares_y} 칸, 한 칸 {args.square_mm}mm, "
          f"마커비 {args.marker_ratio}")
    print(f"   전체 인쇄 크기: {board_w_mm:.0f} x {board_h_mm:.0f} mm (+여백 {args.margin_mm}mm)")
    print(f"   딕셔너리: DICT_5X5_250" + ("  | 형식: A4 PDF (실제 크기)" if args.pdf else ""))
    print()
    print("⚠️ 인쇄: '실제 크기/배율 100%'로. 인쇄 후 자로 한 칸 실측 → 캘리브 시 그 값 사용.")
    print(f"   캘리브 명령 예시:")
    print(f"     python bin_picking/tests/calibrate_ace2_intrinsics.py \\")
    print(f"       --squares-x {args.squares_x} --squares-y {args.squares_y} \\")
    print(f"       --square-mm <실측값> --marker-ratio {args.marker_ratio}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
