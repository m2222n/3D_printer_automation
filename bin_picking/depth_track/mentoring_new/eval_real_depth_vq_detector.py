from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch

from depth_vq_detector.depth_preprocess import (
    load_depth,
    load_json,
    make_depth_input,
    input_channels_for_mode,
    resize_depth_nan_safe,
    parse_center_keep,
    parse_float_range,
    preprocess_metric_depth,
    apply_center_crop,
    adjust_camera_for_crop,
    adjust_camera_for_resize,
)
from depth_vq_detector.model import DepthVQDetector
from depth_vq_detector.postprocess import postprocess_outputs, prediction_masks_np
from depth_vq_detector.real_labelme import (
    canonical_cad_name,
    find_label_json_for_depth,
    load_labelme_objects,
    gt_objects_to_jsonable,
    mask_iou,
)


def parse_image_size(value: str | None):
    if value is None or str(value).lower() in {"none", ""}:
        return None
    parts = str(value).lower().replace("x", ",").split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("image_size must be like 512,512 or 512x512")
    return int(parts[0]), int(parts[1])


def safe_div(num: float, den: float) -> float:
    return float(num) / float(den) if den else 0.0


def f1_from_pr(precision: float, recall: float) -> float:
    return 2.0 * precision * recall / (precision + recall) if (precision + recall) else 0.0


def box_iou_xyxy(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = [float(x) for x in a]
    bx1, by1, bx2, by2 = [float(x) for x in b]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def load_model_from_checkpoint(checkpoint: str | Path, device: str, input_mode_arg: str | None = None):
    ckpt = torch.load(checkpoint, map_location="cpu")
    ckpt_args = ckpt.get("args", {})
    input_mode = input_mode_arg or ckpt_args.get("input_mode", "zv")
    label_offset = int(ckpt_args.get("label_offset", 1))

    cad_codebook = ckpt.get("cad_codebook")
    cad_ids = [str(x) for x in ckpt.get("cad_ids", [])]
    if cad_codebook is None:
        cad_codebook = ckpt.get("model", {}).get("cad_codebook", None)

    model = DepthVQDetector(
        in_channels=input_channels_for_mode(input_mode),
        num_classes=int(ckpt_args.get("num_classes", 27)),
        cad_codebook=cad_codebook,
        num_queries=int(ckpt_args.get("num_queries", 100)),
        hidden_dim=int(ckpt_args.get("hidden_dim", 256)),
        backbone_dim=int(ckpt_args.get("backbone_dim", 64)),
        decoder_layers=int(ckpt_args.get("decoder_layers", 6)),
        nheads=int(ckpt_args.get("nheads", 8)),
    )
    model.load_state_dict(ckpt["model"], strict=True)
    dev = torch.device(device)
    model.to(dev).eval()
    image_size = ckpt_args.get("image_size", None)
    if isinstance(image_size, list):
        image_size = tuple(image_size)
    return model, dev, ckpt_args, input_mode, image_size, label_offset, cad_ids


def _resolve_label_ref(depth_path: Path, label_dir: str | None, label_zip: str | None, label_json: str | None = None) -> tuple[str | None, str | None, str | None]:
    ref = find_label_json_for_depth(depth_path, label_json=label_json, label_dir=label_dir, label_zip=label_zip)
    if not ref:
        return None, None, None
    if ref.startswith("zip://"):
        rest = ref[len("zip://"):]
        zpath, _ = rest.split("::", 1)
        return ref, None, zpath
    return ref, ref, None


@torch.no_grad()
def infer_one(
    *,
    model: DepthVQDetector,
    device: torch.device,
    depth_path: Path,
    input_mode: str,
    image_size: tuple[int, int] | None,
    label_offset: int,
    cad_ids: list[str],
    camera_path: str | None,
    real_uint16_max_depth_m: float | None,
    depth_scale: float | None,
    zero_to_nan: bool,
    center_keep: str | None,
    center_crop: str | None,
    depth_keep_range: str | None,
    infer_avg_pool_kernel: int,
    score_thresh: float,
    mask_thresh: float,
    topk: int,
    score_mode: str,
    nms_iou_thresh: float,
    nms_iou_type: str,
    bbox_source: str,
) -> dict[str, Any]:
    camera = load_json(camera_path)
    if real_uint16_max_depth_m is not None and depth_scale is None:
        scale = float(real_uint16_max_depth_m) / 65535.0
    else:
        scale = depth_scale
    depth = load_depth(
        depth_path,
        depth_scale=scale,
        zero_to_nan=bool(zero_to_nan or real_uint16_max_depth_m is not None),
    )
    source_depth_hw = tuple(depth.shape)
    if center_crop is not None and center_keep is not None:
        raise ValueError("Use either --center_crop or --center_keep, not both.")

    crop_box_yxyx = None
    if center_crop is not None:
        depth, crop_box_yxyx = apply_center_crop(depth, parse_center_keep(center_crop))
        camera = adjust_camera_for_crop(camera, crop_box_yxyx)

    depth = preprocess_metric_depth(
        depth,
        center_keep=parse_center_keep(center_keep),
        center_fill_value=0.0,
        keep_depth_range=parse_float_range(depth_keep_range),
        range_fill_value=0.0,
        avg_pool_kernel=infer_avg_pool_kernel,
    )
    pre_resize_hw = tuple(depth.shape)
    depth = resize_depth_nan_safe(depth, image_size)
    camera = adjust_camera_for_resize(camera, pre_resize_hw, tuple(depth.shape) if image_size is not None else None)
    x = make_depth_input(depth, camera=camera, mode=input_mode)
    inp = torch.from_numpy(x)[None].float().to(device)
    outputs = model(inp)
    h, w = depth.shape
    preds = postprocess_outputs(
        outputs,
        image_size=(h, w),
        cad_ids=cad_ids,
        score_thresh=score_thresh,
        topk=topk,
        mask_thresh=mask_thresh,
        class_id_offset=label_offset,
        score_mode=score_mode,
        nms_iou_thresh=nms_iou_thresh,
        nms_iou_type=nms_iou_type,
        bbox_source=bbox_source,
    )
    query_indices = [p["query_index"] for p in preds]
    masks = prediction_masks_np(outputs, (h, w), query_indices, mask_thresh=mask_thresh)
    return {
        "scene_id": depth_path.stem,
        "file": str(depth_path),
        "source_depth_hw": source_depth_hw,
        "input_shape_hw": (h, w),
        "crop_bbox_yxyx": crop_box_yxyx,
        "predictions": preds,
        "masks": masks,
    }


def pred_match_label(pred: dict[str, Any], match_key: str) -> str | None:
    if match_key == "cad_id":
        cad = pred.get("cad_id")
        return canonical_cad_name(cad) if cad is not None else None
    if match_key == "class_id":
        return str(int(pred["class_id"])) if "class_id" in pred else None
    raise ValueError(match_key)


def gt_match_label(gt: dict[str, Any], match_key: str) -> str | None:
    if match_key == "cad_id":
        return canonical_cad_name(gt.get("cad_name", gt.get("raw_label", "")))
    if match_key == "class_id":
        cid = int(gt.get("class_id", -1))
        return str(cid) if cid > 0 else None
    raise ValueError(match_key)


def evaluate_label_count(preds: list[dict[str, Any]], gts: list[dict[str, Any]], match_key: str) -> dict[str, Any]:
    from collections import Counter
    pc = Counter([x for x in (pred_match_label(p, match_key) for p in preds) if x is not None])
    gc = Counter([x for x in (gt_match_label(g, match_key) for g in gts) if x is not None])
    tp = sum(min(pc[k], gc[k]) for k in set(pc) | set(gc))
    fp = sum(pc.values()) - tp
    fn = sum(gc.values()) - tp
    p = safe_div(tp, tp + fp)
    r = safe_div(tp, tp + fn)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1_from_pr(p, r), "n_pred": sum(pc.values()), "n_gt": sum(gc.values())}


def evaluate_box_or_mask(
    preds: list[dict[str, Any]],
    pred_masks: np.ndarray,
    gts: list[dict[str, Any]],
    *,
    match_key: str,
    iou_thresh: float,
    mode: str,
) -> dict[str, Any]:
    pred_items = []
    for idx, pred in enumerate(preds):
        label = pred_match_label(pred, match_key)
        if label is None:
            continue
        item = {"idx": idx, "label": label, "score": float(pred.get("score", 0.0)), "box": [float(x) for x in pred.get("bbox_xyxy", [])]}
        if mode == "mask" and idx < len(pred_masks):
            item["mask"] = pred_masks[idx].astype(bool)
        pred_items.append(item)
    gt_items = []
    for idx, gt in enumerate(gts):
        label = gt_match_label(gt, match_key)
        if label is None:
            continue
        item = {"idx": idx, "label": label, "box": [float(x) for x in gt.get("bbox_xyxy", [])]}
        if mode == "mask":
            item["mask"] = np.asarray(gt.get("mask"), dtype=bool)
        gt_items.append(item)

    matched_gt: set[int] = set()
    tp = 0
    ious: list[float] = []
    for p in sorted(pred_items, key=lambda x: x["score"], reverse=True):
        best_iou, best_gt = 0.0, None
        for g in gt_items:
            if g["idx"] in matched_gt or g["label"] != p["label"]:
                continue
            if mode == "mask":
                cur_iou = mask_iou(p["mask"], g["mask"])
            else:
                cur_iou = box_iou_xyxy(p["box"], g["box"])
            if cur_iou > best_iou:
                best_iou, best_gt = cur_iou, g["idx"]
        if best_gt is not None and best_iou >= iou_thresh:
            matched_gt.add(best_gt)
            tp += 1
            ious.append(best_iou)
    fp = len(pred_items) - tp
    fn = len(gt_items) - tp
    prec = safe_div(tp, tp + fp)
    rec = safe_div(tp, tp + fn)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": prec, "recall": rec, "f1": f1_from_pr(prec, rec), "n_pred": len(pred_items), "n_gt": len(gt_items), "mean_matched_iou": float(np.mean(ious)) if ious else 0.0}


def evaluate_spatial_label_diagnostic(
    preds: list[dict[str, Any]],
    pred_masks: np.ndarray,
    gts: list[dict[str, Any]],
    *,
    match_key: str,
    iou_thresh: float,
    mode: str,
) -> dict[str, Any]:
    """Match predictions to GT by IoU only, then measure whether labels agree."""
    pred_items = []
    for idx, pred in enumerate(preds):
        label = pred_match_label(pred, match_key)
        item = {"idx": idx, "label": label, "score": float(pred.get("score", 0.0)), "box": [float(x) for x in pred.get("bbox_xyxy", [])]}
        if mode == "mask" and idx < len(pred_masks):
            item["mask"] = pred_masks[idx].astype(bool)
        pred_items.append(item)
    gt_items = []
    for idx, gt in enumerate(gts):
        label = gt_match_label(gt, match_key)
        item = {"idx": idx, "label": label, "box": [float(x) for x in gt.get("bbox_xyxy", [])]}
        if mode == "mask":
            item["mask"] = np.asarray(gt.get("mask"), dtype=bool)
        gt_items.append(item)

    matched_gt: set[int] = set()
    spatial_tp = 0
    label_correct = 0
    matched_ious: list[float] = []
    pairs: list[str] = []
    for p in sorted(pred_items, key=lambda x: x["score"], reverse=True):
        best_iou, best_gt = 0.0, None
        for g in gt_items:
            if g["idx"] in matched_gt:
                continue
            if mode == "mask":
                cur_iou = mask_iou(p["mask"], g["mask"])
            else:
                cur_iou = box_iou_xyxy(p["box"], g["box"])
            if cur_iou > best_iou:
                best_iou, best_gt = cur_iou, g
        if best_gt is not None and best_iou >= iou_thresh:
            matched_gt.add(best_gt["idx"])
            spatial_tp += 1
            matched_ious.append(best_iou)
            ok = (p.get("label") == best_gt.get("label"))
            if ok:
                label_correct += 1
            pairs.append(f"pred={p.get('label')}|gt={best_gt.get('label')}|iou={best_iou:.3f}|ok={int(ok)}")
    spatial_fp = len(pred_items) - spatial_tp
    spatial_fn = len(gt_items) - spatial_tp
    sp = safe_div(spatial_tp, spatial_tp + spatial_fp)
    sr = safe_div(spatial_tp, spatial_tp + spatial_fn)
    return {
        "spatial_tp_ignore_label": spatial_tp,
        "spatial_fp_ignore_label": spatial_fp,
        "spatial_fn_ignore_label": spatial_fn,
        "spatial_precision_ignore_label": sp,
        "spatial_recall_ignore_label": sr,
        "spatial_f1_ignore_label": f1_from_pr(sp, sr),
        "spatial_label_correct": label_correct,
        "spatial_label_acc": safe_div(label_correct, spatial_tp),
        "spatial_mean_iou": float(np.mean(matched_ious)) if matched_ious else 0.0,
        "spatial_pairs": "; ".join(pairs[:20]),
    }

def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tp = int(sum(r["tp"] for r in rows))
    fp = int(sum(r["fp"] for r in rows))
    fn = int(sum(r["fn"] for r in rows))
    p = safe_div(tp, tp + fp)
    r = safe_div(tp, tp + fn)
    return {
        "num_files": len(rows),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision_micro": p,
        "recall_micro": r,
        "f1_micro": f1_from_pr(p, r),
        "precision_macro_scene": float(np.mean([x["precision"] for x in rows])) if rows else 0.0,
        "recall_macro_scene": float(np.mean([x["recall"] for x in rows])) if rows else 0.0,
        "f1_macro_scene": float(np.mean([x["f1"] for x in rows])) if rows else 0.0,
        "mean_matched_iou_macro": float(np.mean([x.get("mean_matched_iou", 0.0) for x in rows])) if rows else 0.0,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    keys: list[str] = []
    for r in rows:
        for k in r.keys():
            if k not in keys:
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate real depth shots using LabelMe JSON labels")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--depth_dir", required=True, help="Directory containing real .npy depth shots, e.g. ./data/real_depth_0626/npy")
    parser.add_argument("--glob", default="shot_*_g1.npy")
    parser.add_argument("--label_dir", default=None, help="Directory containing LabelMe JSON files, one per shot")
    parser.add_argument("--label_zip", default=None, help="Zip archive containing LabelMe JSON files")
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--match_key", choices=["cad_id", "class_id"], default="cad_id", help="LabelMe labels are CAD names, so cad_id is recommended")
    parser.add_argument("--eval_mode", choices=["label_count", "box", "mask"], default="mask")
    parser.add_argument("--iou_thresh", type=float, default=0.50)
    parser.add_argument("--missing_label", choices=["error", "skip"], default="error")

    parser.add_argument("--camera", default=None)
    parser.add_argument("--input_mode", default=None, choices=["z", "zv", "xyzv", "xyznv"])
    parser.add_argument("--image_size", type=parse_image_size, default=None)
    parser.add_argument("--depth_scale", type=float, default=None)
    parser.add_argument("--real_uint16_max_depth_m", type=float, default=10.0)
    parser.add_argument("--zero_to_nan", action="store_true")
    parser.add_argument("--center_keep", default=None, help="Zero outside center ROI. Prefer --center_crop for real shots.")
    parser.add_argument("--center_crop", default="1/6,5/6", help="Crop center ROI before inference. Default: 1/6,5/6")
    parser.add_argument("--depth_keep_range", default="0.40,0.60")
    parser.add_argument("--infer_avg_pool_kernel", type=int, default=1)

    parser.add_argument("--score_thresh", type=float, default=0.25)
    parser.add_argument("--mask_thresh", type=float, default=0.5)
    parser.add_argument("--topk", type=int, default=100)
    parser.add_argument("--score_mode", choices=["det", "product", "cad"], default="det")
    parser.add_argument("--nms_iou_thresh", type=float, default=0.10)
    parser.add_argument("--nms_iou_type", choices=["mask", "box"], default="mask")
    parser.add_argument("--bbox_source", choices=["mask", "model"], default="mask", help="Which bbox to evaluate/save. mask aligns boxes with predicted masks; model uses detector box head.")
    parser.add_argument("--no_angle", action="store_true", help="마스크에서 회전각(angle) 산출을 끈다. 기본은 켬 — 로봇 파지에 angle이 필수(2026-07-30).")
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--max_files", type=int, default=None)
    parser.add_argument("--save_predictions", action="store_true")
    parser.add_argument("--diagnose_label_mismatch", action="store_true", help="Also compute IoU-only spatial matching and label accuracy on those matches.")
    args = parser.parse_args()

    if not args.label_dir and not args.label_zip:
        raise ValueError("Provide --label_dir or --label_zip for LabelMe real-shot evaluation.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model, device, ckpt_args, input_mode, ckpt_image_size, label_offset, cad_ids = load_model_from_checkpoint(args.checkpoint, args.device, args.input_mode)
    image_size = args.image_size or ckpt_image_size

    depth_files = sorted(Path(args.depth_dir).glob(args.glob))
    if args.max_files is not None:
        depth_files = depth_files[: args.max_files]
    if not depth_files:
        raise FileNotFoundError(f"No files matched {Path(args.depth_dir) / args.glob}")

    rows: list[dict[str, Any]] = []
    all_predictions: dict[str, Any] = {}
    missing: list[str] = []
    for i, depth_path in enumerate(depth_files, 1):
        label_ref, label_json_path, label_zip_path = _resolve_label_ref(depth_path, args.label_dir, args.label_zip)
        if label_ref is None:
            if args.missing_label == "error":
                missing.append(depth_path.name)
                continue
            print(f"[{i:04d}/{len(depth_files):04d}] skip missing label: {depth_path.name}")
            continue

        inf = infer_one(
            model=model,
            device=device,
            depth_path=depth_path,
            input_mode=input_mode,
            image_size=image_size,
            label_offset=label_offset,
            cad_ids=cad_ids,
            camera_path=args.camera,
            real_uint16_max_depth_m=args.real_uint16_max_depth_m,
            depth_scale=args.depth_scale,
            zero_to_nan=args.zero_to_nan,
            center_keep=args.center_keep,
            center_crop=args.center_crop,
            depth_keep_range=args.depth_keep_range,
            infer_avg_pool_kernel=args.infer_avg_pool_kernel,
            score_thresh=args.score_thresh,
            mask_thresh=args.mask_thresh,
            topk=args.topk,
            score_mode=args.score_mode,
            nms_iou_thresh=args.nms_iou_thresh,
            nms_iou_type=args.nms_iou_type,
            bbox_source=args.bbox_source,
        )
        gt_objects = load_labelme_objects(
            label_json=label_json_path,
            label_zip=label_zip_path,
            stem=depth_path.stem,
            source_depth_hw=inf["source_depth_hw"],
            target_hw=inf["input_shape_hw"],
            crop_box_yxyx=inf["crop_bbox_yxyx"],
            cad_ids=cad_ids,
            label_offset=label_offset,
        )
        preds = inf["predictions"]
        masks = inf["masks"]
        if args.eval_mode == "label_count":
            metrics = evaluate_label_count(preds, gt_objects, args.match_key)
        else:
            metrics = evaluate_box_or_mask(
                preds,
                masks,
                gt_objects,
                match_key=args.match_key,
                iou_thresh=args.iou_thresh,
                mode=args.eval_mode,
            )
            if args.diagnose_label_mismatch:
                metrics.update(evaluate_spatial_label_diagnostic(
                    preds,
                    masks,
                    gt_objects,
                    match_key=args.match_key,
                    iou_thresh=args.iou_thresh,
                    mode=args.eval_mode,
                ))
        row = {"file": depth_path.name, "label_json": str(label_ref), "num_predictions": len(preds), **metrics}
        rows.append(row)
        # ⭐ 마스크를 버리기 전에 회전각을 뽑아 예측에 심는다 (2026-07-30 추가).
        #    로봇 파지에는 angle이 필수인데(27종 중 22종·검출 82%가 종횡비 1.5 초과,
        #    tests/survey_rotation_asymmetry.py) 아래 clean_inf가 masks를 버려서
        #    6요소 단계에서 angle=0으로 고정돼 있었다.
        #    ⚠️ 마스크 전체는 저장하지 않는다(100장×수십개면 무거움) — 각도·OBB만 남긴다.
        if not args.no_angle:
            try:
                from bin_picking.src.pipeline.mask_to_angle import angles_from_masks
                # 마스크는 모델 입력(crop·resize) 좌표계 → 원본 depth 좌표계로 되돌린다.
                # ⚠️ 이 역변환을 빼먹으면 좌표가 밀린다(7/29에 141px 밀림 경험).
                y0, x0, y1, x1 = inf["crop_bbox_yxyx"]
                in_h, in_w = inf["input_shape_hw"]
                sx = (x1 - x0) / max(in_w, 1)
                sy = (y1 - y0) / max(in_h, 1)
                ang = angles_from_masks(masks, offset_xy=(x0, y0), scale_xy=(sx, sy))
                for p, a in zip(preds, ang):
                    if a is None:
                        p["angle_deg"] = None
                        p["angle_note"] = "mask_angle_failed"
                    else:
                        p["angle_deg"] = a["angle"]
                        p["angle_reliable"] = a["angle_reliable"]
                        p["obb_edge"] = a["edge"]
                        p["obb_aspect"] = a["aspect"]
                        p["obb_fill"] = a["fill"]
                        p["angle_note"] = a["angle_note"]
            except Exception as e:
                # 각도 산출 실패가 평가 자체를 죽이면 안 된다(F1 재현이 주 목적).
                print(f"  ⚠️ angle 산출 건너뜀 ({type(e).__name__}: {e})")
        clean_inf = {k: v for k, v in inf.items() if k != "masks"}
        clean_inf["label_json"] = str(label_ref)
        clean_inf["ground_truth"] = gt_objects_to_jsonable(gt_objects)
        all_predictions[depth_path.stem] = clean_inf
        if args.save_predictions:
            pred_dir = out_dir / "predictions"
            pred_dir.mkdir(parents=True, exist_ok=True)
            with (pred_dir / f"{depth_path.stem}.json").open("w", encoding="utf-8") as f:
                json.dump(clean_inf, f, indent=2)
        print(f"[{i:04d}/{len(depth_files):04d}] {depth_path.name}: TP={metrics['tp']} FP={metrics['fp']} FN={metrics['fn']} F1={metrics['f1']:.4f}")

    if missing:
        sample = ", ".join(missing[:10])
        raise FileNotFoundError(f"Missing LabelMe JSON for {len(missing)} depth files. First missing: {sample}. Use --missing_label skip only if intentional.")

    summary = aggregate(rows)
    summary.update({
        "checkpoint": str(args.checkpoint),
        "depth_dir": str(args.depth_dir),
        "glob": args.glob,
        "label_dir": str(args.label_dir) if args.label_dir else None,
        "label_zip": str(args.label_zip) if args.label_zip else None,
        "match_key": args.match_key,
        "eval_mode": args.eval_mode,
        "iou_thresh": args.iou_thresh,
        "score_thresh": args.score_thresh,
        "mask_thresh": args.mask_thresh,
        "score_mode": args.score_mode,
        "nms_iou_thresh": args.nms_iou_thresh,
        "nms_iou_type": args.nms_iou_type,
        "bbox_source": args.bbox_source,
        "center_crop": args.center_crop,
        "depth_keep_range": args.depth_keep_range,
    })
    with (out_dir / "eval_real_metrics.json").open("w", encoding="utf-8") as f:
        json.dump({"summary": summary, "per_scene": rows}, f, indent=2)
    write_csv(out_dir / "eval_real_per_scene.csv", rows)
    if args.save_predictions:
        with (out_dir / "all_predictions.json").open("w", encoding="utf-8") as f:
            json.dump(all_predictions, f, indent=2)

    print("\n=== Real-depth LabelMe evaluation summary ===")
    print(json.dumps(summary, indent=2))
    print(f"Saved metrics to {out_dir / 'eval_real_metrics.json'}")
    print(f"Saved per-scene CSV to {out_dir / 'eval_real_per_scene.csv'}")


if __name__ == "__main__":
    main()
