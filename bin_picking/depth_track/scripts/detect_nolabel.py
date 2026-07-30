#!/usr/bin/env python3
"""라벨 없이 검출만 — 새 세션 촬영 직후 "찾긴 찾나" 확인용.

⭐ 왜 필요한가
--------------
`eval_real_depth_vq_detector.py`는 **라벨을 강제한다**(`:418` — label_dir 없으면
ValueError). 그런데 금요일 촬영분은 **라벨이 없다**(labelme 작업은 나중).

라벨 없이도 답할 수 있는 질문이 있다:
  - 새 환경에서 **검출이 되기는 하나?** (0건이면 그 자리에서 알아야 한다)
  - 검출 수·신뢰도·z 분포가 **학습 세션과 비슷한가?**

🚨 라벨 없이 알 수 없는 것 = **F1**(맞게 찾았는지). 그건 labelme 라벨링 후에만.
   그래서 이 스크립트는 **"완전히 무너졌는지"를 조기에 걸러내는 용도**다.
   여기서 검출 0건이면 F1을 볼 필요도 없다.

비교 기준 (7/29 학습 세션 100장, 같은 파라미터):
  검출 801건 / 장당 평균 8.0건 / z 99%가 400~600mm / 평균 신뢰도 ~0.9

사용:
  PYTHONPATH=/home/jtm/3D_printer_automation /data/jtm/depth_venv/bin/python \
    bin_picking/depth_track/scripts/detect_nolabel.py \
    --depth_dir /data/jtm/blaze_crosssession_0731 \
    --out_dir   /data/jtm/blaze_crosssession_0731_detect
"""
from __future__ import annotations
import argparse
import json
import statistics as st
import sys
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve()
MENTORING = HERE.parents[1] / "mentoring_new"
sys.path.insert(0, str(MENTORING))

CKPT_DEFAULT = ("/data/jtm/a100_backup_0710/checkpoints/extracted/runs/"
                "T100_csblur_lr1e4_ep80/best.pt")

# 7/29 학습 세션 기준값 (같은 파라미터로 낸 것)
BASE_PER_SCENE = 8.01      # 801건 / 100장
BASE_Z_IN_BAND = 99.0      # %


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--depth_dir", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--checkpoint", default=CKPT_DEFAULT)
    ap.add_argument("--glob", default="shot*.npy")
    ap.add_argument("--score_thresh", type=float, default=0.45)
    ap.add_argument("--mask_thresh", type=float, default=0.5)
    ap.add_argument("--nms_iou_thresh", type=float, default=0.5)
    args = ap.parse_args()

    # eval 모듈을 그대로 재사용한다 — 추론 경로가 달라지면 비교가 무의미해진다.
    import eval_real_depth_vq_detector as E

    depth_dir = Path(args.depth_dir)
    files = sorted(depth_dir.glob(args.glob))
    if not files:
        # npy/ 하위도 시도
        files = sorted((depth_dir / "npy").glob(args.glob))
        if files:
            depth_dir = depth_dir / "npy"
    if not files:
        print(f"🔴 {args.glob} 없음: {args.depth_dir}")
        return 1

    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    print(f"검출 대상 {len(files)}장 / 체크포인트 {Path(args.checkpoint).name}")
    print("(라벨 없이 검출만 — F1은 labelme 라벨링 후)\n")

    # ⚠️ 실제 API에 맞춤(추측 금지 — 처음에 `load_model`로 잘못 짰다가 시그니처를
    #    확인해 고쳤다). 반환 7개: model, device, ckpt_args, input_mode,
    #    image_size, label_offset, cad_ids
    model, device, ckpt_args, input_mode, image_size, label_offset, cad_ids = (
        E.load_model_from_checkpoint(args.checkpoint, "cpu")
    )

    rows, all_scores, all_z, per_scene = [], [], [], []
    for i, f in enumerate(files, 1):
        # ⭐ 7/29 평가와 **완전히 동일한 인자**로 호출한다. 하나라도 다르면 결과
        #    차이가 "조건 차이"인지 "세션 차이"인지 구분할 수 없다.
        inf = E.infer_one(
            model=model, device=device, depth_path=f,
            input_mode=input_mode, image_size=image_size,
            label_offset=label_offset, cad_ids=cad_ids,
            camera_path=None,
            # 🔴 **10.0이 기본값이다**(eval `:396`). None을 넘기면 uint16→m 변환이
            #    안 돼 검출이 무너진다 — 실제로 처음에 None으로 짜서 장당 9건이
            #    2건으로 떨어졌다(같은 데이터인데!). 이것이 `raw × 10/65535`의 10.
            #    ⭐ 이걸 못 잡았으면 금요일에 "폭락했다"고 오진했을 것.
            real_uint16_max_depth_m=10.0, depth_scale=None, zero_to_nan=False,
            center_keep=None, center_crop="1/6,5/6",
            depth_keep_range="0.40,0.60", infer_avg_pool_kernel=1,
            score_thresh=args.score_thresh, mask_thresh=args.mask_thresh,
            topk=100, score_mode="det",
            nms_iou_thresh=args.nms_iou_thresh, nms_iou_type="mask",
            bbox_source="mask",
        )

        preds = inf["predictions"]
        n = len(preds)
        scores = [float(p.get("score", 0)) for p in preds]
        all_scores += scores
        per_scene.append(n)

        # z는 6요소 파이프라인과 같은 방식으로 뽑는다(bbox 중심 median)
        depth = np.load(f)
        zs = []
        for p in preds:
            b = p.get("bbox") or p.get("bbox_xyxy")
            if not b:
                continue
            try:
                x1, y1, x2, y2 = [int(v) for v in b[:4]]
                patch = depth[max(y1, 0):y2, max(x1, 0):x2]
                v = patch[patch > 0]
                if v.size:
                    zs.append(float(np.median(v)) * 10.0 / 65535.0 * 1000.0)
            except Exception:
                pass
        all_z += zs
        rows.append({"file": f.name, "n_pred": n,
                     "mean_score": round(st.mean(scores), 4) if scores else 0.0,
                     "z_median_mm": round(st.median(zs), 1) if zs else None})
        print(f"[{i:03d}/{len(files):03d}] {f.name}: 검출 {n}건"
              f"{'  ⚠️ 0건' if n == 0 else ''}")

        clean = {k: v for k, v in inf.items() if k != "masks"}
        (out_dir / f"{f.stem}.json").write_text(
            json.dumps(clean, indent=2, default=str), encoding="utf-8")

    total = sum(per_scene)
    avg = total / len(files)
    zero = sum(1 for n in per_scene if n == 0)
    in_band = 100.0 * sum(1 for z in all_z if 400 <= z <= 600) / max(len(all_z), 1)

    summary = {
        "n_scenes": len(files), "n_detections": total,
        "per_scene_avg": round(avg, 2), "scenes_with_zero": zero,
        "mean_score": round(st.mean(all_scores), 4) if all_scores else 0.0,
        "z_in_band_pct": round(in_band, 1),
        "baseline_per_scene": BASE_PER_SCENE, "baseline_z_in_band": BASE_Z_IN_BAND,
    }
    (out_dir / "detect_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 58)
    print(f"  장면 {len(files)} / 검출 {total}건 / 장당 평균 {avg:.2f}건")
    print(f"  학습 세션 기준 장당 {BASE_PER_SCENE}건 → 비율 {100*avg/BASE_PER_SCENE:.0f}%")
    print(f"  검출 0건 장면: {zero}장")
    print(f"  평균 신뢰도: {summary['mean_score']:.3f}")
    print(f"  z 400~600mm: {in_band:.1f}%  (학습 세션 {BASE_Z_IN_BAND}%)")
    print("=" * 58)

    # 🚨 판정 — 라벨 없이 말할 수 있는 범위에서만
    print("\n[판정 — 라벨 없이 알 수 있는 것만]")
    if total == 0:
        print("  🔴 검출 0건 = 완전 실패. F1 볼 필요 없음.")
        print("     확인: 거리(400~600mm)·ShortRange·부품이 화면 중앙에 있었나")
    elif zero > len(files) * 0.3:
        print(f"  🔴 {zero}/{len(files)} 장면이 0건 = 심각. 촬영 조건 점검 필요")
    elif avg < BASE_PER_SCENE * 0.5:
        print("  🟡 검출 수가 학습 세션의 절반 미만 = 하락 의심")
        print("     ⚠️ 단 부품을 적게 놓았으면 정상. capture_meta 조건과 함께 볼 것")
    else:
        print("  🟢 검출 수는 학습 세션과 비슷한 수준")
        print("     ⚠️ **이것은 '찾았다'가 아니라 '뭔가 찾았다'다.**")
        print("        맞게 찾았는지(F1)는 labelme 라벨링 후에만 알 수 있다.")
    if in_band < 80:
        print(f"  ⚠️ z가 부품 대역을 벗어남({in_band:.0f}%) = 촬영 거리 문제 가능")

    print(f"\n산출물: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
