from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

_HASH_SUFFIX_RE = re.compile(r"__[0-9a-fA-F]{4,}(?:__[0-9a-fA-F]{4,})*$")
_PREFIX_INT_RE = re.compile(r"^(\d+)[_\-].*$")


def canonical_cad_name(value: Any) -> str:
    """Normalize CAD/STL/LabelMe label names for display and matching.

    Examples:
      03_sol_block_front.stl      -> 03_sol_block_front
      03_sol_block_front__e79f118d -> 03_sol_block_front
    """
    if value is None:
        return ""
    name = Path(str(value)).stem
    name = _HASH_SUFFIX_RE.sub("", name)
    if "__" in name:
        name = name.split("__", 1)[0]
    return name


def label_to_class_id(label: Any) -> int | None:
    """Fallback parser for labels like '01_sol_block_a'.

    NOTE: this is only a fallback.  In this project the training category_id is
    the dense CAD-memory index (1..27), not always the numeric prefix in the
    STL filename.  Prefer build_cad_name_to_class_id(cad_ids) whenever a
    checkpoint/CAD memory is available.
    """
    s = str(label)
    m = _PREFIX_INT_RE.match(s)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def build_cad_name_to_class_id(cad_ids: list[str] | tuple[str, ...] | None, label_offset: int = 1) -> dict[str, int]:
    """Build canonical CAD-name -> dense training class_id mapping.

    Model class_id follows the CAD codebook order saved in the checkpoint:
      class_id = cad_index + label_offset

    This is different from numeric filename prefixes for many parts, e.g.
      08_r_guide_a.stl can be class_id 6, while 11_sw_block.stl can be class_id 8.
    """
    mapping: dict[str, int] = {}
    if not cad_ids:
        return mapping
    for i, cad in enumerate(cad_ids):
        name = canonical_cad_name(cad)
        if name:
            mapping[name] = int(i + label_offset)
    return mapping


def _read_labelme_json(label_json: str | Path | None = None, *, label_zip: str | Path | None = None, stem: str | None = None) -> dict[str, Any] | None:
    if label_json:
        p = Path(label_json)
        if not p.exists():
            raise FileNotFoundError(p)
        with p.open("r", encoding="utf-8-sig") as f:
            return json.load(f)
    if label_zip and stem:
        zpath = Path(label_zip)
        if not zpath.exists():
            raise FileNotFoundError(zpath)
        target_names = {f"{stem}.json", f"./{stem}.json"}
        with zipfile.ZipFile(zpath) as zf:
            # Exact basename match first, then suffix match for nested zips.
            by_base = {Path(n).name: n for n in zf.namelist() if n.lower().endswith(".json")}
            name = by_base.get(f"{stem}.json")
            if name is None:
                for n in zf.namelist():
                    if n in target_names or Path(n).stem == stem:
                        name = n
                        break
            if name is None:
                return None
            return json.loads(zf.read(name).decode("utf-8-sig"))
    return None


def find_label_json_for_depth(
    depth_path: str | Path | None,
    *,
    label_json: str | Path | None = None,
    label_dir: str | Path | None = None,
    label_zip: str | Path | None = None,
) -> str | None:
    """Find a LabelMe JSON path for a depth file.

    For a depth file named shot_001_g1.npy, this looks for shot_001_g1.json.
    If label_zip is used, the returned value is a virtual string
    'zip://<zip_path>::<stem>.json'. Use load_labelme_objects directly with
    label_zip for actual reading.
    """
    if label_json:
        return str(label_json)
    if depth_path is None:
        return None
    stem = Path(depth_path).stem
    if label_dir:
        p = Path(label_dir) / f"{stem}.json"
        if p.exists():
            return str(p)
    if label_zip:
        zpath = Path(label_zip)
        if zpath.exists():
            with zipfile.ZipFile(zpath) as zf:
                basenames = {Path(n).name for n in zf.namelist()}
            if f"{stem}.json" in basenames:
                return f"zip://{zpath}::{stem}.json"
    return None


def _shape_points(shape: dict[str, Any]) -> list[tuple[float, float]]:
    pts = shape.get("points", [])
    if not pts:
        return []
    shape_type = str(shape.get("shape_type", "polygon")).lower()
    if shape_type == "rectangle" and len(pts) >= 2:
        (x1, y1), (x2, y2) = pts[0], pts[1]
        return [(float(x1), float(y1)), (float(x2), float(y1)), (float(x2), float(y2)), (float(x1), float(y2))]
    return [(float(x), float(y)) for x, y in pts]


def _rasterize_polygon(points_xy: list[tuple[float, float]], hw: tuple[int, int]) -> np.ndarray:
    h, w = int(hw[0]), int(hw[1])
    if h <= 0 or w <= 0 or len(points_xy) < 3:
        return np.zeros((max(h, 0), max(w, 0)), dtype=bool)
    img = Image.new("L", (w, h), 0)
    ImageDraw.Draw(img).polygon(points_xy, outline=1, fill=1)
    return np.asarray(img, dtype=np.uint8) > 0


def load_labelme_objects(
    *,
    label_json: str | Path | None = None,
    label_zip: str | Path | None = None,
    stem: str | None = None,
    source_depth_hw: tuple[int, int],
    target_hw: tuple[int, int],
    crop_box_yxyx: tuple[int, int, int, int] | None = None,
    cad_ids: list[str] | tuple[str, ...] | None = None,
    label_offset: int = 1,
) -> list[dict[str, Any]]:
    """Load LabelMe polygon labels as masks in the target image coordinates.

    The provided real labels were drawn on RGB PNGs with image size 1696x960,
    while the depth npy files are 848x480.  This function automatically scales
    LabelMe points from JSON imageWidth/imageHeight to the original depth size,
    then applies the same center crop and final resize used by inference.

    Args:
      source_depth_hw: original depth .npy shape before crop, e.g. (480, 848).
      target_hw: final coordinate canvas for GT masks. For visualization this is
        usually the cropped pre-resize depth shape; for metric evaluation this
        can be the model input shape.
      crop_box_yxyx: optional crop box in original depth coordinates.
    """
    obj = _read_labelme_json(label_json, label_zip=label_zip, stem=stem)
    if obj is None:
        return []

    label_h = float(obj.get("imageHeight", source_depth_hw[0]))
    label_w = float(obj.get("imageWidth", source_depth_hw[1]))
    src_h, src_w = float(source_depth_hw[0]), float(source_depth_hw[1])
    tgt_h, tgt_w = float(target_hw[0]), float(target_hw[1])
    if crop_box_yxyx is None:
        y0 = x0 = 0.0
        canvas_h, canvas_w = src_h, src_w
    else:
        y0, x0, y1, x1 = [float(v) for v in crop_box_yxyx]
        canvas_h, canvas_w = max(1.0, y1 - y0), max(1.0, x1 - x0)

    sx_json_to_src = src_w / max(label_w, 1.0)
    sy_json_to_src = src_h / max(label_h, 1.0)
    sx_canvas_to_target = tgt_w / max(canvas_w, 1.0)
    sy_canvas_to_target = tgt_h / max(canvas_h, 1.0)

    cad_name_to_class_id = build_cad_name_to_class_id(cad_ids, label_offset=label_offset)

    objects: list[dict[str, Any]] = []
    for shape in obj.get("shapes", []):
        label = str(shape.get("label", "")).strip()
        if not label:
            continue
        pts = _shape_points(shape)
        if len(pts) < 3:
            continue
        target_pts: list[tuple[float, float]] = []
        for x_json, y_json in pts:
            x_src = x_json * sx_json_to_src
            y_src = y_json * sy_json_to_src
            x_can = x_src - x0
            y_can = y_src - y0
            x_t = x_can * sx_canvas_to_target
            y_t = y_can * sy_canvas_to_target
            target_pts.append((x_t, y_t))
        mask = _rasterize_polygon(target_pts, (int(target_hw[0]), int(target_hw[1])))
        if not mask.any():
            # Outside crop, or too tiny after resize.
            continue
        ys, xs = np.where(mask)
        cad_name = canonical_cad_name(label)
        cid = cad_name_to_class_id.get(cad_name)
        if cid is None:
            cid = label_to_class_id(label)
        idx = len(objects) + 1
        objects.append({
            "idx": idx,
            "raw_label": label,
            "class_id": int(cid) if cid is not None else -1,
            "cad_name": cad_name,
            "mask": mask,
            "bbox_xyxy": [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)],
        })
    return objects


def gt_objects_to_jsonable(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for o in objects:
        out.append({
            "idx": int(o.get("idx", -1)),
            "raw_label": str(o.get("raw_label", "")),
            "class_id": int(o.get("class_id", -1)) if o.get("class_id", -1) is not None else -1,
            "cad_name": str(o.get("cad_name", "")),
            "bbox_xyxy": [int(v) for v in o.get("bbox_xyxy", [])],
            "mask_area": int(np.asarray(o.get("mask", np.zeros((0, 0), dtype=bool))).sum()),
        })
    return out


def mask_iou(a: np.ndarray, b: np.ndarray) -> float:
    aa = np.asarray(a).astype(bool)
    bb = np.asarray(b).astype(bool)
    if aa.shape != bb.shape:
        raise ValueError(f"mask shape mismatch: {aa.shape} vs {bb.shape}")
    inter = np.logical_and(aa, bb).sum()
    union = np.logical_or(aa, bb).sum()
    return float(inter) / float(max(union, 1))
