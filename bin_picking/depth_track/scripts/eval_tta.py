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
# 🔴🔴 2026-08-21 판정 = **우리 데이터에서 TTA는 해롭다. 채택하지 않는다.**
#
#   측정 (T100 · thr 0.20 · 8/18 90장 · 변수는 --scales 하나):
#     scales=1.0(TTA 없음)      F1 0.5838  TP 371 FP 270   0.08s/장   ← 기준
#     scales=1.0,0.85,1.15      F1 0.5134  TP 345 FP 369   0.63s/장   🔴 −0.0704 · 8배
#     scales=1.0,0.9,1.1,0.8,1.2 F1 0.4734 TP 338 FP 460   1.19s/장   🔴 −0.1104 · 15배
#
#   ⭐⭐ **같은 TTA가 KAIST 데이터에선 도움이 됐다** (7/13 기록, test102):
#     scales=1.0        F1 0.6836  TP 577 FP 203
#     scales=3-scale    F1 0.6907  TP 632 FP 290   🟢 +0.0071
#
#   🚨 **FP 거동이 정반대다** — KAIST는 FP가 늘어도 TP가 함께 늘어(577→632) F1이 올랐는데,
#      우리는 FP만 늘고(270→369) **TP는 오히려 줄었다**(371→345). recall도 0.589→0.548로 떨어져
#      *"커버리지를 넓힌다"* 는 TTA의 전제가 우리 데이터에서 성립하지 않는다.
#   💡 해석 = KAIST는 **같은 세션**(학습 분포 안)이라 다중 스케일이 진짜 부품을 더 찾았고,
#      우리는 **cross-session**이라 스케일을 흔들면 학습 분포에서 더 멀어져 헛검출만 는다.
#      ⇒ 7/13에 적어둔 *"TTA는 검출 커버리지를 넓히고 종류식별 병목은 못 품"* 보다 나쁘다
#        (커버리지조차 안 넓어진다).
#   📌 **KTR 3초 제약과 무관하게 이미 탈락**이다 — F1이 떨어지므로 시간을 볼 필요가 없다.
#      (다만 시간도 쟀다: A100에서 8~15배. 배포 HW에서는 더 나쁠 것)
#
#   ⭐ 이 파일은 **폐기하지 않고 남긴다** — 판정 근거이고, 재현 가능해야 한다.
#      🚨 단 **"TTA로 성능을 올릴 수 있다"는 근거로 인용하지 말 것.**
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


def _canon(name):
    """이름 정규화 + 동치 처리. ⭐ 본 평가기(`eval_real_depth_vq_detector`)와 **같은 규칙**이어야 한다.

    🚨 2026-08-21 정정 = 여기가 `canonical_cad_name`만 쓰고 **`apply_cad_equivalence`를
       안 쓰고 있었다**. 8/19에 신설한 동치 처리(`14_13`→`13_variant`)가 빠져 있어
       **TTA와 baseline이 다른 채점 규칙**으로 비교되던 상태다
       (같은 날 A100 본 평가기가 7/6자로 낡았던 것과 **같은 계열의 누락**).
    ⇒ ⭐ TTA 이득을 재려면 **분모가 같아야** 한다. E의 함수를 그대로 재사용해
       규칙이 갈릴 수 없게 한다.
    """
    return E.apply_cad_equivalence(canonical_cad_name(name)) if name else None


def match_count(preds, gts, iou_thr):
    used = [False] * len(gts)
    tp = 0
    for p in sorted(preds, key=lambda x: x["score"], reverse=True):
        pc = _canon(p["cad_id"]) if p.get("cad_id") else None
        best_j, best_iou = -1, iou_thr
        for j, g in enumerate(gts):
            if used[j] or _canon(g["cad_name"]) != pc:
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
    # ⭐⭐ 추론 시간 측정 (2026-08-21 신설) — KTR 정량목표 ②가 "응답 3초 이내"이고
    #    8/5 실측 최악이 2.67초다. TTA는 스케일 수만큼 추론을 반복하므로
    #    **F1이 올라도 3초를 넘기면 채택할 수 없다** ⇒ 이득과 비용을 함께 재야 판정이 된다.
    #    🚨 A100 시간이지 배포 하드웨어(Thor/IPC) 시간이 아니다 — 비율(배수)로 해석할 것.
    import time
    scene_secs = []
    for i, dp in enumerate(depth_files, 1):
        pooled = []
        crop_box = None
        source_hw = None
        _t0 = time.perf_counter()
        for hw in sizes:
            r = E.infer_one(depth_path=dp, image_size=hw, **kw)
            crop_box = r.get("crop_bbox_yxyx")
            source_hw = r.get("source_depth_hw")
            for p, m in zip(r["predictions"], r["masks"]):
                pooled.append({"score": p["score"], "cad_id": p.get("cad_id"),
                               "mask": resize_mask(m, base_hw)})
        merged = nms_masks(pooled, args.nms_iou_thresh)
        if torch.cuda.is_available():
            torch.cuda.synchronize()   # GPU는 비동기라 동기화 없이 재면 실제보다 짧게 나온다
        scene_secs.append(time.perf_counter() - _t0)

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
    import statistics as _st
    _srt = sorted(scene_secs)
    timing = {
        "n_scales": len(scales),
        "sec_mean": round(_st.mean(scene_secs), 3) if scene_secs else None,
        "sec_median": round(_st.median(scene_secs), 3) if scene_secs else None,
        "sec_p95": round(_srt[int(len(_srt) * 0.95)], 3) if scene_secs else None,
        "sec_max": round(max(scene_secs), 3) if scene_secs else None,
        "device": str(dev),
        "note": "추론+NMS만. 카메라 grab·6요소 변환은 제외. A100 기준이므로 배포 HW와 절대값이 다르다.",
    }
    print(f"[timing] scales={len(scales)}  mean {timing['sec_mean']}s  "
          f"median {timing['sec_median']}s  p95 {timing['sec_p95']}s  max {timing['sec_max']}s")
    json.dump({"summary": {"f1_micro": f1, "precision_micro": prec, "recall_micro": rec,
                           "tp": tp, "fp": fp, "fn": fn, "scales": scales,
                           "num_files": len(depth_files), "timing": timing,
                           "evaluator_equivalence": dict(E.EQUIVALENT_CAD_NAMES)},
               "per_scene": per_scene},
              open(Path(args.out_dir) / "eval_tta_metrics.json", "w"), indent=2)
    print(f"\n=== TTA 결과 ===")
    print(f"  F1={f1:.4f}  P={prec:.3f}  R={rec:.3f}  (TP{tp}/FP{fp}/FN{fn})")
    print(f"  baseline(발표) = 0.6836")
    print("  ✅ 향상" if f1 > 0.6836 + 1e-4 else "  ⚠️ baseline 이하 = TTA 무효")


if __name__ == "__main__":
    main()
