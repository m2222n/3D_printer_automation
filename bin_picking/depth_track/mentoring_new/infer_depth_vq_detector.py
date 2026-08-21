from __future__ import annotations

import argparse
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
from depth_vq_detector.visualization import save_prediction_visualization
from depth_vq_detector.real_labelme import (
    find_label_json_for_depth,
    load_labelme_objects,
    gt_objects_to_jsonable,
)


def parse_image_size(value: str | None):
    if value is None or str(value).lower() in {"none", ""}:
        return None
    parts = str(value).lower().replace("x", ",").split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("image_size must be like 512,512 or 512x512")
    return int(parts[0]), int(parts[1])


def _load_scene_npz(path: str | Path) -> tuple[np.ndarray, dict[str, Any], str]:
    data = np.load(path, allow_pickle=True)
    if "depth" not in data.files:
        raise KeyError(f"{path} has no key 'depth'. Available: {data.files}")
    depth = data["depth"].astype(np.float32)
    meta = {}
    if "meta" in data.files:
        raw = data["meta"].item() if getattr(data["meta"], "shape", None) == () else str(data["meta"])
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if isinstance(raw, str):
            try:
                meta = json.loads(raw)
            except json.JSONDecodeError:
                meta = {}
    scene_id = f"scene_{int(meta['scene_idx']):05d}" if "scene_idx" in meta else Path(path).stem
    camera = meta.get("camera", {}) if isinstance(meta.get("camera", {}), dict) else {}
    return depth, camera, scene_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Infer depth-only VQ query detector")
    parser.add_argument("--checkpoint", required=True)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--scene_npz", default=None, help="Provided scene npz with key depth")
    src.add_argument("--depth", default=None, help="Standalone depth .npy/.npz/.png")
    parser.add_argument("--camera", default=None, help="Optional camera.json for standalone depth")
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--input_mode", default=None, choices=["z", "zv", "xyzv", "xyznv"])
    parser.add_argument("--image_size", type=parse_image_size, default=None)
    parser.add_argument("--depth_scale", type=float, default=None)
    parser.add_argument(
        "--real_uint16_max_depth_m",
        type=float,
        default=None,
        help="For real uint16 .npy shots encoded as raw/65535*max_depth_m. Example: 10.0 makes raw=3000 -> 0.458m.",
    )
    parser.add_argument(
        "--zero_to_nan",
        action="store_true",
        help="Treat raw zero depth as invalid NaN before preprocessing. Automatically enabled with --real_uint16_max_depth_m.",
    )
    parser.add_argument(
        "--center_keep",
        "--center_keep_frac",
        dest="center_keep",
        default=None,
        help="Keep center ROI and zero outside. Example: '1/6,5/6' keeps x/y from 1/6 to 5/6. For real test/inference, prefer --center_crop.",
    )
    parser.add_argument(
        "--center_crop",
        default=None,
        help="Crop to the center ROI instead of zeroing outside. Example: '1/6,5/6'. Recommended for real test/inference visualization.",
    )
    parser.add_argument(
        "--depth_keep_range",
        default=None,
        help="Optional metric depth range filter after center crop, e.g. '0.45,0.55'. Outside is zeroed.",
    )
    parser.add_argument(
        "--infer_avg_pool_kernel",
        type=int,
        default=1,
        help="Optional odd average-pooling kernel for inference depth input. Usually keep 1 for real shots.",
    )
    # ⭐⭐ 기본값 0.25 → 0.20 (2026-08-21)
    #
    # 🚨 왜 여기를 고치는가 = 8/20에 스윕으로 0.20을 최적점으로 정하고
    #    `eval_crosssession*.sh`에만 반영했는데, **운영 추론이 읽는 기본값은 여기**다.
    #    ⇒ "측정한 값"과 "실제로 도는 값"이 달랐다(0.20 vs 0.25).
    #    ⭐ 8/20 교훈의 재발 = *"주석·스크립트만 고치면 코드는 계속 옛 값을 쓴다"*.
    #
    # 근거 = 8/18 실측 90장 스윕(0.10/0.15/0.20/0.30/0.45), 0.20이 봉우리(양쪽으로 하락):
    #    0.45(옛) F1 0.5445 · R 0.500  |  ⭐0.20 F1 0.5838 · R 0.589  (+0.0393, 학습 불필요)
    # 🚨 판정 근거는 F1이 아니라 **집을 수 있는 부품 수** 491→577(+86) = GT 대비 77.9%→91.6%
    #    (추가 치명은 +9뿐 = 9.6:1). 파지 *비율*은 95.5→94.7로 내려가나 **분모가 커진 탓**이다.
    # 📌 recall은 0.10에서 포화(TP 373 vs 0.20의 371) ⇒ 더 낮추면 FP만 는다.
    parser.add_argument("--score_thresh", type=float, default=0.20)
    parser.add_argument("--mask_thresh", type=float, default=0.5)
    parser.add_argument("--topk", type=int, default=100)
    parser.add_argument("--score_mode", choices=["det", "product", "cad"], default="det", help="Score used for filtering/ranking. det=class/object score; product=class*CAD; cad=CAD only.")
    parser.add_argument(
        "--nms_iou_thresh",
        type=float,
        default=0.70,
        help="Class-agnostic representative NMS threshold. If two predictions overlap above this IoU, keep only the higher-score prediction. Set <=0 or >=1 to disable.",
    )
    parser.add_argument(
        "--nms_iou_type",
        choices=["mask", "box"],
        default="mask",
        help="IoU source for representative duplicate suppression. mask is recommended for instance segmentation outputs.",
    )
    parser.add_argument(
        "--bbox_source",
        choices=["mask", "model"],
        default="mask",
        help="Which bbox to report/draw. mask=tight bbox from predicted mask; model=detector box head. Use model only for debugging bbox-head behavior.",
    )
    # Representative IoU NMS is class-agnostic by design: if two predictions overlap
    # strongly, only the higher-score prediction remains and provides the representative label.
    parser.add_argument("--debug_scores", action="store_true", help="Print top query class/CAD scores before thresholding")
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--visualize", action="store_true", help="Save overlay PNG with predicted masks, boxes, class ids, and CAD ids")
    parser.add_argument("--include_gt_visualization", action="store_true", help="Add a GT overlay panel. Works with --scene_npz or LabelMe real-shot labels.")
    parser.add_argument("--label_json", default=None, help="Optional LabelMe JSON for a real depth shot, e.g. labels/shot_001_g1.json")
    parser.add_argument("--label_dir", default=None, help="Optional directory containing LabelMe JSONs with the same stem as depth files")
    parser.add_argument("--label_zip", default=None, help="Optional zip archive containing LabelMe JSONs, e.g. 실증 데이터셋_라벨링_0629.zip")
    parser.add_argument("--include_label_visualization", action="store_true", help="Alias for including LabelMe GT overlay when --label_json/--label_dir/--label_zip is used")
    args = parser.parse_args()

    ckpt = torch.load(args.checkpoint, map_location="cpu")
    ckpt_args = ckpt.get("args", {})
    input_mode = args.input_mode or ckpt_args.get("input_mode", "zv")
    image_size = args.image_size or ckpt_args.get("image_size", None)
    if isinstance(image_size, list):
        image_size = tuple(image_size)
    label_offset = int(ckpt_args.get("label_offset", 1))

    cad_codebook = ckpt.get("cad_codebook")
    cad_ids = [str(x) for x in ckpt.get("cad_ids", [])]
    if cad_codebook is None:
        state = ckpt["model"]
        cad_codebook = state.get("cad_codebook", None)
    # Detector-only checkpoints may have no codebook.

    num_classes = int(ckpt_args.get("num_classes", 27))
    model = DepthVQDetector(
        in_channels=input_channels_for_mode(input_mode),
        num_classes=num_classes,
        cad_codebook=cad_codebook,
        num_queries=int(ckpt_args.get("num_queries", 100)),
        hidden_dim=int(ckpt_args.get("hidden_dim", 256)),
        backbone_dim=int(ckpt_args.get("backbone_dim", 64)),
        decoder_layers=int(ckpt_args.get("decoder_layers", 6)),
        nheads=int(ckpt_args.get("nheads", 8)),
    )
    model.load_state_dict(ckpt["model"], strict=True)
    device = torch.device(args.device)
    model.to(device).eval()

    depth_path_for_label = None
    if args.scene_npz:
        depth, camera, scene_id = _load_scene_npz(args.scene_npz)
        if args.depth_scale is not None:
            depth = depth * float(args.depth_scale)
    else:
        depth_path_for_label = args.depth
        camera = load_json(args.camera)
        if args.real_uint16_max_depth_m is not None and args.depth_scale is None:
            depth_scale = float(args.real_uint16_max_depth_m) / 65535.0
        else:
            depth_scale = args.depth_scale if args.depth_scale is not None else ckpt_args.get("depth_scale", None)
        depth = load_depth(
            args.depth,
            depth_scale=depth_scale,
            zero_to_nan=bool(args.zero_to_nan or args.real_uint16_max_depth_m is not None),
        )
        scene_id = Path(args.depth).stem
    source_depth_hw = tuple(depth.shape)

    if args.center_crop is not None and args.center_keep is not None:
        raise ValueError("Use either --center_crop or --center_keep, not both. --center_crop changes image size; --center_keep zeros outside.")

    # Deployment-time preprocessing for real demonstration shots.
    # --center_crop removes the border region entirely, so the central object
    # cluster becomes the model/visualization canvas instead of remaining tiny
    # inside the original full frame.
    crop_box_yxyx = None
    crop_hw = None
    if args.center_crop is not None:
        depth, crop_box_yxyx = apply_center_crop(depth, parse_center_keep(args.center_crop))
        camera = adjust_camera_for_crop(camera, crop_box_yxyx)
        crop_hw = tuple(depth.shape)

    # For pseudo scene_npz inference, leave these options unset unless
    # intentionally testing robustness.
    depth = preprocess_metric_depth(
        depth,
        center_keep=parse_center_keep(args.center_keep),
        center_fill_value=0.0,
        keep_depth_range=parse_float_range(args.depth_keep_range),
        range_fill_value=0.0,
        avg_pool_kernel=args.infer_avg_pool_kernel,
    )
    viz_depth = depth.copy()

    # Optional real-shot LabelMe labels.  The real annotations are drawn on
    # PNG images whose resolution can differ from the depth npy resolution
    # (observed: labels 1696x960, depth 848x480).  We scale polygons to the
    # original depth size, then apply the same center crop, and finally create
    # GT masks in the visualization coordinate system.
    label_json_ref = find_label_json_for_depth(
        depth_path_for_label,
        label_json=args.label_json,
        label_dir=args.label_dir,
        label_zip=args.label_zip,
    )
    label_json_path = None
    label_zip_path = None
    if label_json_ref:
        if str(label_json_ref).startswith("zip://"):
            # Virtual reference: zip://path::stem.json
            rest = str(label_json_ref)[len("zip://"):]
            label_zip_path = rest.split("::", 1)[0]
        else:
            label_json_path = label_json_ref
    gt_label_objects = []
    if label_json_ref:
        gt_label_objects = load_labelme_objects(
            label_json=label_json_path,
            label_zip=label_zip_path,
            stem=scene_id,
            source_depth_hw=source_depth_hw,
            target_hw=tuple(viz_depth.shape),
            crop_box_yxyx=crop_box_yxyx,
            cad_ids=cad_ids,
            label_offset=label_offset,
        )
        if args.debug_scores:
            print(f"loaded LabelMe GT objects: {len(gt_label_objects)} from {label_json_ref}")

    pre_resize_hw = tuple(depth.shape)
    depth = resize_depth_nan_safe(depth, image_size)
    camera = adjust_camera_for_resize(camera, pre_resize_hw, tuple(depth.shape) if image_size is not None else None)
    x = make_depth_input(depth, camera=camera, mode=input_mode)
    inp = torch.from_numpy(x)[None].float().to(device)

    with torch.no_grad():
        outputs = model(inp)
    if args.debug_scores:
        probs = outputs["pred_logits"][0].softmax(-1)
        class_probs, labels = probs[:, :-1].max(-1)
        print(f"max class_score={float(class_probs.max()):.6f}, mean class_score={float(class_probs.mean()):.6f}")
        if "pred_cad_logits" in outputs:
            cad_prob = outputs["pred_cad_logits"][0].softmax(-1)
            cad_scores, cad_labels = cad_prob.max(-1)
            combined = class_probs * cad_scores
            print(f"max cad_score={float(cad_scores.max()):.6f}, mean cad_score={float(cad_scores.mean()):.6f}")
            print(f"max class*cad={float(combined.max()):.6f}")
        vals, idxs = torch.topk(class_probs, k=min(10, class_probs.numel()))
        for rank, (v, q) in enumerate(zip(vals.tolist(), idxs.tolist()), 1):
            msg = f"top{rank}: q={q} class_id={int(labels[q]) + label_offset} class_score={v:.6f}"
            if "pred_cad_logits" in outputs:
                msg += f" cad_score={float(cad_scores[q]):.6f} cad_index={int(cad_labels[q])}"
            print(msg)
    h, w = depth.shape
    preds = postprocess_outputs(
        outputs,
        image_size=(h, w),
        cad_ids=cad_ids,
        score_thresh=args.score_thresh,
        topk=args.topk,
        mask_thresh=args.mask_thresh,
        class_id_offset=label_offset,
        score_mode=args.score_mode,
        nms_iou_thresh=args.nms_iou_thresh,
        nms_iou_type=args.nms_iou_type,
        bbox_source=args.bbox_source,
    )
    # Predictions are in the model-input coordinate system.  If the input was
    # produced by --center_crop, keep bbox_xyxy as crop-local coordinates for
    # visualization, and additionally report bbox_xyxy_original in the original
    # full-frame coordinates.  This is useful when deployment needs original
    # pixel coordinates even though visualization is crop-local.
    if crop_box_yxyx is not None and crop_hw is not None:
        y0, x0, y1, x1 = crop_box_yxyx
        crop_h, crop_w = int(crop_hw[0]), int(crop_hw[1])
        sy = float(crop_h) / float(max(h, 1))
        sx = float(crop_w) / float(max(w, 1))
        def _to_original_xyxy(box_xyxy):
            bx1, by1, bx2, by2 = [float(v) for v in box_xyxy]
            return [
                bx1 * sx + float(x0),
                by1 * sy + float(y0),
                bx2 * sx + float(x0),
                by2 * sy + float(y0),
            ]

        for p in preds:
            bx1, by1, bx2, by2 = [float(v) for v in p["bbox_xyxy"]]
            p["bbox_xyxy_crop"] = [bx1, by1, bx2, by2]
            p["bbox_xyxy_original"] = _to_original_xyxy(p["bbox_xyxy"])
            if "bbox_xyxy_model" in p:
                p["bbox_xyxy_model_original"] = _to_original_xyxy(p["bbox_xyxy_model"])
            if "bbox_xyxy_mask" in p:
                p["bbox_xyxy_mask_original"] = _to_original_xyxy(p["bbox_xyxy_mask"])
            p["crop_bbox_yxyx"] = [int(y0), int(x0), int(y1), int(x1)]

    query_indices = [p["query_index"] for p in preds]
    masks = prediction_masks_np(outputs, (h, w), query_indices, mask_thresh=args.mask_thresh)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "predictions.json").open("w", encoding="utf-8") as f:
        json.dump({
            "scene_id": scene_id,
            "input_shape_hw": [int(h), int(w)],
            "visualization_shape_hw": [int(viz_depth.shape[0]), int(viz_depth.shape[1])],
            "source_depth_shape_hw": [int(source_depth_hw[0]), int(source_depth_hw[1])],
            "crop_bbox_yxyx": list(map(int, crop_box_yxyx)) if crop_box_yxyx is not None else None,
            "label_json": str(label_json_ref) if label_json_ref else None,
            "ground_truth": gt_objects_to_jsonable(gt_label_objects) if gt_label_objects else [],
            "bbox_source": args.bbox_source,
            "predictions": preds,
        }, f, indent=2)
    np.savez_compressed(out_dir / "predicted_masks.npz", masks=masks.astype(np.uint8), query_indices=np.array(query_indices, dtype=np.int64))
    if args.visualize:
        include_label_gt = bool((args.include_label_visualization or args.include_gt_visualization) and gt_label_objects)
        include_scene_gt = bool(args.include_gt_visualization and args.scene_npz and not gt_label_objects)
        if crop_box_yxyx is not None and include_scene_gt:
            print("warning: scene_npz GT overlay is disabled with --center_crop because scene GT masks are full-frame; use LabelMe --label_json/--label_dir for real cropped GT visualization.")
            include_scene_gt = False
        save_prediction_visualization(
            depth=viz_depth,
            predictions=preds,
            masks=masks,
            out_path=out_dir / "visualization.png",
            scene_npz=args.scene_npz if include_scene_gt else None,
            include_gt=bool(include_label_gt or include_scene_gt),
            gt_objects=gt_label_objects if include_label_gt else None,
            gt_title="LabelMe GT overlay" if include_label_gt else "Ground truth overlay",
        )
    print(f"Saved {len(preds)} predictions to {out_dir}")


if __name__ == "__main__":
    main()
