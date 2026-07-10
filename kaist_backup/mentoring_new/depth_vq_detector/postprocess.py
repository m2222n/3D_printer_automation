from __future__ import annotations

from typing import Any

import torch
import torch.nn.functional as F

from .geometry import box_cxcywh_to_xyxy


def _box_iou_one_to_many(boxes_xyxy: torch.Tensor, cur_pos: int, rest_pos: torch.Tensor) -> torch.Tensor:
    """IoU between boxes[cur_pos] and boxes[rest_pos]. boxes are [N,4] xyxy."""
    if rest_pos.numel() == 0:
        return torch.empty((0,), device=boxes_xyxy.device, dtype=boxes_xyxy.dtype)
    cur = boxes_xyxy[cur_pos]
    rest = boxes_xyxy[rest_pos]

    x1 = torch.maximum(cur[0], rest[:, 0])
    y1 = torch.maximum(cur[1], rest[:, 1])
    x2 = torch.minimum(cur[2], rest[:, 2])
    y2 = torch.minimum(cur[3], rest[:, 3])
    inter = (x2 - x1).clamp(min=0) * (y2 - y1).clamp(min=0)

    area_cur = (cur[2] - cur[0]).clamp(min=0) * (cur[3] - cur[1]).clamp(min=0)
    area_rest = (rest[:, 2] - rest[:, 0]).clamp(min=0) * (rest[:, 3] - rest[:, 1]).clamp(min=0)
    union = area_cur + area_rest - inter
    return inter / union.clamp(min=1e-6)


def _mask_iou_one_to_many(masks_bool: torch.Tensor, cur_pos: int, rest_pos: torch.Tensor) -> torch.Tensor:
    """IoU between masks[cur_pos] and masks[rest_pos]. masks are bool [N,H,W]."""
    if rest_pos.numel() == 0:
        return torch.empty((0,), device=masks_bool.device, dtype=torch.float32)
    cur = masks_bool[cur_pos]
    rest = masks_bool[rest_pos]
    inter = torch.logical_and(rest, cur).flatten(1).sum(dim=1).float()
    union = torch.logical_or(rest, cur).flatten(1).sum(dim=1).float()
    return inter / union.clamp(min=1.0)


def _mask_boxes_xyxy(masks_bool: torch.Tensor, fallback_boxes_abs: torch.Tensor) -> torch.Tensor:
    """Compute tight xyxy boxes from predicted masks.

    The model has separate box and mask heads. On real depth shots the box head
    can drift from the mask head even when the mask itself is reasonable. For
    visualization and real-shot evaluation, the mask-derived box is often the
    correct region-of-interest box. Empty masks fall back to the model box.
    """
    if masks_bool.numel() == 0:
        return fallback_boxes_abs.clone()
    n, _, _ = masks_bool.shape
    boxes = fallback_boxes_abs.clone()
    for i in range(n):
        ys, xs = torch.where(masks_bool[i])
        if xs.numel() == 0:
            continue
        boxes[i, 0] = xs.min().float()
        boxes[i, 1] = ys.min().float()
        boxes[i, 2] = xs.max().float() + 1.0
        boxes[i, 3] = ys.max().float() + 1.0
    return boxes


def _representative_iou_nms(
    *,
    sorted_positions: torch.Tensor,
    boxes_xyxy_sorted_space: torch.Tensor,
    masks_bool_sorted_space: torch.Tensor,
    iou_thresh: float,
    iou_type: str,
) -> torch.Tensor:
    """
    Class-agnostic representative NMS over score-sorted candidates.

    This intentionally ignores predicted class/CAD labels. If two candidates occupy
    nearly the same region, keep the higher-score candidate only; its class/CAD
    becomes the representative label for that region.

    `sorted_positions` contains positions in score-sorted candidate space, e.g.
    [0, 1, 2, ...]. Returned values are also positions in that sorted space.
    """
    if iou_thresh is None or iou_thresh <= 0 or iou_thresh >= 1:
        return sorted_positions
    if sorted_positions.numel() <= 1:
        return sorted_positions

    remaining = sorted_positions.clone()
    kept: list[int] = []
    while remaining.numel() > 0:
        cur = int(remaining[0].item())
        kept.append(cur)
        rest = remaining[1:]
        if rest.numel() == 0:
            break

        if iou_type == "mask":
            ious = _mask_iou_one_to_many(masks_bool_sorted_space, cur, rest)
        elif iou_type == "box":
            ious = _box_iou_one_to_many(boxes_xyxy_sorted_space, cur, rest)
        else:
            raise ValueError(f"Unknown nms_iou_type={iou_type!r}; expected mask or box")

        # Class-agnostic suppression: any candidate with high overlap is removed,
        # even if its predicted class/CAD label differs.
        remaining = rest[ious <= float(iou_thresh)]

    return torch.tensor(kept, device=sorted_positions.device, dtype=torch.long)


@torch.no_grad()
def postprocess_outputs(
    outputs: dict[str, torch.Tensor],
    image_size: tuple[int, int],
    cad_ids: list[str] | None = None,
    score_thresh: float = 0.25,
    topk: int = 100,
    mask_thresh: float = 0.5,
    class_id_offset: int = 0,
    score_mode: str = "det",
    nms_iou_thresh: float = 0.70,
    nms_iou_type: str = "mask",
    bbox_source: str = "mask",
) -> list[dict[str, Any]]:
    """
    Post-process a single image output into Python dict predictions.

    bbox_source:
      - "mask": report bbox_xyxy as the tight box of the predicted mask.
        This keeps the drawn box aligned with the displayed mask and is the
        recommended default for real-shot visualization/evaluation.
      - "model": report bbox_xyxy from the detector box head.
        Both sources are always stored as bbox_xyxy_mask and bbox_xyxy_model.

    NMS behavior:
      - Class-agnostic representative NMS is used by default.
      - If two predictions have IoU > nms_iou_thresh, keep only the higher-score
        prediction, regardless of class/CAD label.
      - The remaining prediction's class/CAD is treated as the representative label
        for that overlapping region.
      - Set nms_iou_thresh <= 0 or >= 1 to disable this step.
    """
    h, w = image_size
    pred_logits = outputs["pred_logits"][0]
    pred_boxes = outputs["pred_boxes"][0]
    pred_masks = outputs["pred_masks"][0]
    probs = pred_logits.softmax(-1)
    class_probs, labels = probs[:, :-1].max(-1)  # exclude no-object

    cad_labels = None
    cad_scores = None
    if "pred_cad_logits" in outputs:
        cad_prob = outputs["pred_cad_logits"][0].softmax(-1)
        cad_scores, cad_labels = cad_prob.max(-1)
        if score_mode == "product":
            scores = class_probs * cad_scores
        elif score_mode == "cad":
            scores = cad_scores
        elif score_mode == "det":
            scores = class_probs
        else:
            raise ValueError(f"Unknown score_mode={score_mode!r}; expected det, product, or cad")
    else:
        scores = class_probs

    keep = scores >= score_thresh
    if keep.sum() == 0:
        return []
    keep_idx = torch.where(keep)[0]
    keep_scores = scores[keep_idx]
    order = torch.argsort(keep_scores, descending=True)
    keep_idx = keep_idx[order]

    # Build masks and boxes for score-thresholded, score-sorted candidates.
    masks = F.interpolate(pred_masks[keep_idx, None], size=(h, w), mode="bilinear", align_corners=False)[:, 0]
    masks_prob = masks.sigmoid()
    masks_bool = masks_prob > mask_thresh

    boxes_xyxy = box_cxcywh_to_xyxy(pred_boxes[keep_idx]).clamp(0, 1)
    model_boxes_abs = boxes_xyxy.clone()
    model_boxes_abs[:, [0, 2]] *= w
    model_boxes_abs[:, [1, 3]] *= h

    mask_boxes_abs = _mask_boxes_xyxy(masks_bool, model_boxes_abs)
    if bbox_source == "mask":
        boxes_abs = mask_boxes_abs
    elif bbox_source == "model":
        boxes_abs = model_boxes_abs
    else:
        raise ValueError(f"Unknown bbox_source={bbox_source!r}; expected 'mask' or 'model'")

    sorted_positions = torch.arange(keep_idx.numel(), device=keep_idx.device, dtype=torch.long)
    kept_positions = _representative_iou_nms(
        sorted_positions=sorted_positions,
        boxes_xyxy_sorted_space=boxes_abs,
        masks_bool_sorted_space=masks_bool,
        iou_thresh=float(nms_iou_thresh),
        iou_type=nms_iou_type,
    )
    if topk is not None and topk > 0:
        kept_positions = kept_positions[:topk]

    keep_idx = keep_idx[kept_positions]
    masks_prob = masks_prob[kept_positions]
    boxes_abs = boxes_abs[kept_positions]
    model_boxes_abs = model_boxes_abs[kept_positions]
    mask_boxes_abs = mask_boxes_abs[kept_positions]

    results = []
    for n, q_idx in enumerate(keep_idx.tolist()):
        cad_index = int(cad_labels[q_idx].item()) if cad_labels is not None else -1
        result = {
            "query_index": int(q_idx),
            "score": float(scores[q_idx].item()),
            "class_id": int(labels[q_idx].item()) + int(class_id_offset),
            "class_score": float(class_probs[q_idx].item()),
            "bbox_xyxy": [float(v) for v in boxes_abs[n].tolist()],
            "bbox_source": bbox_source,
            "bbox_xyxy_model": [float(v) for v in model_boxes_abs[n].tolist()],
            "bbox_xyxy_mask": [float(v) for v in mask_boxes_abs[n].tolist()],
            "mask_area": int((masks_prob[n] > mask_thresh).sum().item()),
        }
        if cad_labels is not None:
            result["cad_index"] = cad_index
            result["cad_score"] = float(cad_scores[q_idx].item())
            result["cad_id"] = cad_ids[cad_index] if cad_ids is not None and 0 <= cad_index < len(cad_ids) else str(cad_index)
        results.append(result)
    return results


@torch.no_grad()
def prediction_masks_np(
    outputs: dict[str, torch.Tensor],
    image_size: tuple[int, int],
    query_indices: list[int],
    mask_thresh: float = 0.5,
):
    """Return boolean masks [N,H,W] for selected query indices."""
    if not query_indices:
        import numpy as np
        h, w = image_size
        return np.zeros((0, h, w), dtype=bool)
    pred_masks = outputs["pred_masks"][0, query_indices]
    masks = F.interpolate(pred_masks[:, None], size=image_size, mode="bilinear", align_corners=False)[:, 0]
    return (masks.sigmoid() > mask_thresh).cpu().numpy()
