#!/usr/bin/env python
# ============================================================================
# depth_track — Test-Time Augmentation (TTA) 평가
# ----------------------------------------------------------------------------
# 재학습 없이 추론 시점에만 성능을 짜내는 실험. 발표 baseline(F1 0.6836)을
# TTA로 넘길 수 있는지 데이터로 확인.
#
# 방법: 같은 scene을 여러 입력 스케일(image_size)로 독립 추론 → 각 예측 마스크를
#       baseline 해상도(320x576)로 통일 → 전체 예측을 score 내림차순 mask-NMS로 결합
#       → GT(동일 해상도)와 cad_id + mask-IoU 매칭으로 F1 산출.
#   ⚠️ 좌우 flip TTA는 이 모델 병목(좌우대칭 부품 l↔r 혼동)을 악화시킬 위험이 커 제외.
#
# 원본 eval(eval_real_depth_vq_detector)의 infer_one·GT 로더·mask_iou를 그대로 재사용.
# GT는 baseline 해상도 하나로만 로드 → 좌표계 통일(스케일별 좌표계 정합 버그 회피).
# ⚠️ GPU 필수. 학습 서버(A100)에서 실행.
# ============================================================================
import argparse, json, sys
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1] / "mentoring_new"
sys.path.insert(0, str(ROOT))

import eval_real_depth_vq_detector as E
from depth_vq_detector.real_labelme import (
    canonical_cad_name, load_labelme_objects, mask_iou, find_label_json_for_depth,
)


def resize_mask(m, hw):
    if m.shape == tuple(hw):
        return m
    t = torch.from_numpy(m.astype(np.float32))[None, None]
    return (F.interpolate(t, size=tuple(hw), mode="nearest")[0, 0].numpy() > 0.5)


def nms_masks(items, iou_thr):
    items = sorted(items, key=lambda x: x["score"], reverse=True)
    keep = []
    for it in items:
        if all(mask_iou(it["mask"], k["mask"]) <= iou_thr for k in keep):
            keep.append(it)
    return keep


def match_count(preds, gts, iou_thr):
    used = [False] * len(gts)
    tp = 0
    for p in sorted(preds, key=lambda x: x["score"], reverse=True):
        pc = canonical_cad_name(p["cad_id"]) if p.get("cad_id") else None
        best_j, best_iou = -1, iou_thr
        for j, g in enumerate(gts):
            if used[j] or canonical_cad_name(g["cad_name"]) != pc:
                continue
            iou = mask_iou(p["mask"], g["mask"])
            if iou >= best_iou:
                best_iou, best_j = iou, j
        if best_j >= 0:
            used[best_j] = True
            tp += 1
    return tp, len(preds) - tp, len(gts) - tp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--depth_dir", required=True)
    ap.add_argument("--label_dir", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--glob", default="shot*.npy")
    ap.add_argument("--base_h", type=int, default=320)
    ap.add_argument("--base_w", type=int, default=576)
    ap.add_argument("--scales", default="1.0,0.85,1.15")
    ap.add_argument("--score_thresh", type=float, default=0.45)
    ap.add_argument("--mask_thresh", type=float, default=0.5)
    ap.add_argument("--nms_iou_thresh", type=float, default=0.5)
    ap.add_argument("--iou_thresh", type=float, default=0.25)
    args = ap.parse_args()

    model, dev, ckpt_args, input_mode, ckpt_imgsz, label_offset, cad_ids = \
        E.load_model_from_checkpoint(args.checkpoint, "cuda" if torch.cuda.is_available() else "cpu")

    base_hw = (args.base_h, args.base_w)
    scales = [float(s) for s in args.scales.split(",")]
    sizes = [(int(round(args.base_h * s)), int(round(args.base_w * s))) for s in scales]
    depth_files = sorted(Path(args.depth_dir).glob(args.glob))
    print(f"scenes={len(depth_files)}  scales={scales}  sizes={sizes}  base={base_hw}")

    kw = dict(
        model=model, device=dev, input_mode=input_mode, label_offset=label_offset,
        cad_ids=cad_ids, camera_path=None, real_uint16_max_depth_m=10.0, depth_scale=None,
        zero_to_nan=False, center_keep=None, center_crop="1/6,5/6",
        depth_keep_range="0.40,0.60", infer_avg_pool_kernel=1,
        score_thresh=args.score_thresh, mask_thresh=args.mask_thresh, topk=100,
        score_mode="det", nms_iou_thresh=args.nms_iou_thresh, nms_iou_type="mask",
        bbox_source="mask",
    )

    tp = fp = fn = 0
    per_scene = []
    for i, dp in enumerate(depth_files, 1):
        pooled = []
        crop_box = None
        source_hw = None
        for hw in sizes:
            r = E.infer_one(depth_path=dp, image_size=hw, **kw)
            crop_box = r.get("crop_bbox_yxyx")
            source_hw = r.get("source_depth_hw")
            for p, m in zip(r["predictions"], r["masks"]):
                pooled.append({"score": p["score"], "cad_id": p.get("cad_id"),
                               "mask": resize_mask(m, base_hw)})
        merged = nms_masks(pooled, args.nms_iou_thresh)

        # GT를 baseline 해상도로 로드 (좌표계 통일)
        lj = find_label_json_for_depth(dp, label_dir=args.label_dir)
        gts = load_labelme_objects(
            label_json=lj, stem=dp.stem, source_depth_hw=source_hw,
            target_hw=base_hw, crop_box_yxyx=crop_box, cad_ids=cad_ids,
            label_offset=label_offset,
        )
        s_tp, s_fp, s_fn = match_count(merged, gts, args.iou_thresh)
        tp += s_tp; fp += s_fp; fn += s_fn
        per_scene.append({"file": dp.name, "tp": s_tp, "fp": s_fp, "fn": s_fn,
                          "n_pred": len(merged), "n_gt": len(gts)})
        if i % 25 == 0:
            print(f"  {i}/{len(depth_files)}")

    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    json.dump({"summary": {"f1_micro": f1, "precision_micro": prec, "recall_micro": rec,
                           "tp": tp, "fp": fp, "fn": fn, "scales": scales,
                           "num_files": len(depth_files)}, "per_scene": per_scene},
              open(Path(args.out_dir) / "eval_tta_metrics.json", "w"), indent=2)
    print(f"\n=== TTA 결과 ===")
    print(f"  F1={f1:.4f}  P={prec:.3f}  R={rec:.3f}  (TP{tp}/FP{fp}/FN{fn})")
    print(f"  baseline(발표) = 0.6836")
    print("  ✅ 향상" if f1 > 0.6836 + 1e-4 else "  ⚠️ baseline 이하 = TTA 무효")


if __name__ == "__main__":
    main()
