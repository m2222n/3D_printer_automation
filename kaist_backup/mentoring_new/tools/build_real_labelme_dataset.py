#!/usr/bin/env python3
"""Build a real LabelMe depth dataset in the same scene_*.npz format as pseudo data.

Input:
  real depth npy files, e.g. data/real_depth/npy/shot_001_g1.npy
  LabelMe json files, e.g. data/real_labels/shot_001_g1.json

Output:
  data/real_labelme_dataset/
    npz/scene_00000.npz
    crops/scene00000_inst01_catXX.npz
    vis/scene_00000.png
    splits/train.json, val.json, test.json, all.json

This keeps the detector training path unchanged: train_depth_vq_detector.py can train on
the resulting scene manifests.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

_HASH_SUFFIX_RE = re.compile(r"__[0-9a-fA-F]{4,}(?:__[0-9a-fA-F]{4,})*$")
_PREFIX_RE = re.compile(r"^(\d+)[_\-].*")


def canonical_cad_name(value: Any) -> str:
    if value is None:
        return ""
    name = Path(str(value)).stem
    name = _HASH_SUFFIX_RE.sub("", name)
    if "__" in name:
        name = name.split("__", 1)[0]
    return name


def parse_fraction(x: str | float | int) -> float:
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if "/" in s:
        a, b = s.split("/", 1)
        return float(a) / float(b)
    return float(s)


def parse_range(value: str | None):
    if value is None or str(value).strip().lower() in {"", "none", "off"}:
        return None
    parts = [p.strip() for p in str(value).split(",") if p.strip()]
    if len(parts) != 2:
        raise ValueError(f"range must be min,max; got {value}")
    lo, hi = parse_fraction(parts[0]), parse_fraction(parts[1])
    if hi < lo:
        lo, hi = hi, lo
    return float(lo), float(hi)


def crop_box(hw: tuple[int, int], center_crop: str | None):
    H, W = hw
    r = parse_range(center_crop)
    if r is None:
        return (0, 0, H, W)
    a, b = r
    return int(round(H*a)), int(round(W*a)), int(round(H*b)), int(round(W*b))


def load_depth_npy(path: Path, max_depth_m: float) -> np.ndarray:
    arr = np.load(path)
    depth = arr.astype(np.float32)
    if np.issubdtype(arr.dtype, np.integer):
        invalid = depth <= 0
        depth = depth * (float(max_depth_m) / 65535.0)
        depth[invalid] = np.nan
    else:
        depth[depth <= 0] = np.nan
    return depth.astype(np.float32)


def read_label_json(depth_path: Path, label_dir: Path | None, label_zip: Path | None) -> dict[str, Any] | None:
    stem = depth_path.stem
    if label_dir is not None:
        p = label_dir / f"{stem}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8-sig"))
    if label_zip is not None and label_zip.exists():
        with zipfile.ZipFile(label_zip) as zf:
            names = [n for n in zf.namelist() if Path(n).name == f"{stem}.json"]
            if not names:
                return None
            return json.loads(zf.read(names[0]).decode("utf-8-sig"))
    return None


def shape_points(shape: dict[str, Any]):
    pts = shape.get("points", [])
    if not pts:
        return []
    shape_type = str(shape.get("shape_type", "polygon")).lower()
    if shape_type == "rectangle" and len(pts) >= 2:
        (x1, y1), (x2, y2) = pts[0], pts[1]
        return [(float(x1), float(y1)), (float(x2), float(y1)), (float(x2), float(y2)), (float(x1), float(y2))]
    return [(float(x), float(y)) for x, y in pts]


def rasterize(points_xy, hw):
    H, W = int(hw[0]), int(hw[1])
    if len(points_xy) < 3 or H <= 0 or W <= 0:
        return np.zeros((max(0, H), max(0, W)), dtype=bool)
    img = Image.new("L", (W, H), 0)
    ImageDraw.Draw(img).polygon(points_xy, outline=1, fill=1)
    return np.asarray(img, dtype=np.uint8) > 0




def dilate_binary_mask(mask: np.ndarray, radius: int) -> np.ndarray:
    """Binary dilation using PIL MaxFilter; radius is in pixels."""
    r = int(radius or 0)
    if r <= 0 or mask.size == 0:
        return mask.astype(bool)
    k = 2 * r + 1
    img = Image.fromarray(mask.astype(np.uint8) * 255, mode="L")
    img = img.filter(ImageFilter.MaxFilter(k))
    return np.asarray(img, dtype=np.uint8) > 0


def label_to_mask(shape: dict[str, Any], label_obj: dict[str, Any], src_hw, crop_yxyx, target_hw):
    pts = shape_points(shape)
    if len(pts) < 3:
        return np.zeros(target_hw, dtype=bool)
    label_h = float(label_obj.get("imageHeight", src_hw[0]))
    label_w = float(label_obj.get("imageWidth", src_hw[1]))
    src_h, src_w = float(src_hw[0]), float(src_hw[1])
    y0, x0, y1, x1 = [float(v) for v in crop_yxyx]
    crop_h, crop_w = max(1.0, y1-y0), max(1.0, x1-x0)
    tgt_h, tgt_w = float(target_hw[0]), float(target_hw[1])

    sx_json_to_src = src_w / max(label_w, 1.0)
    sy_json_to_src = src_h / max(label_h, 1.0)
    sx_crop_to_target = tgt_w / crop_w
    sy_crop_to_target = tgt_h / crop_h

    out_pts = []
    for xj, yj in pts:
        xs = float(xj) * sx_json_to_src
        ys = float(yj) * sy_json_to_src
        xc = xs - x0
        yc = ys - y0
        out_pts.append((xc * sx_crop_to_target, yc * sy_crop_to_target))
    return rasterize(out_pts, target_hw)


def build_ref_cad_category_map(ref_dataset: Path | None) -> dict[str, int]:
    mapping: dict[str, int] = {}
    if ref_dataset is None:
        return mapping
    npz_dir = ref_dataset / "npz" if (ref_dataset / "npz").exists() else ref_dataset
    if not npz_dir.exists():
        return mapping
    for f in sorted(npz_dir.glob("scene_*.npz"))[:500]:
        try:
            z = np.load(f, allow_pickle=True)
            meta = json.loads(str(z["meta"].item()))
            for inst in meta.get("instances", {}).values():
                stl = str(inst.get("stl", ""))
                cid = int(inst.get("category_id", 0))
                if stl and cid > 0:
                    mapping.setdefault(canonical_cad_name(stl), cid)
        except Exception:
            continue
    return mapping


def fallback_category_id(label: str) -> int | None:
    m = _PREFIX_RE.match(label)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def save_vis(depth, inst_id, category_id, path: Path):
    H, W = depth.shape
    valid = np.isfinite(depth)
    img = np.zeros((H, W, 3), dtype=np.uint8)
    if valid.any():
        vals = depth[valid]
        p1, p99 = np.percentile(vals, [1, 99])
        norm = np.zeros((H, W), dtype=np.float32)
        norm[valid] = 1.0 - np.clip((depth[valid] - p1) / (p99 - p1 + 1e-8), 0, 1)
        img[:] = (norm * 255).astype(np.uint8)[..., None]
        rng = np.random.default_rng(12345)
        colors = rng.integers(50, 255, size=(max(int(category_id.max()) + 1, 2), 3), dtype=np.uint8)
        colors[0] = 0
        m = category_id > 0
        overlay = colors[np.clip(category_id, 0, len(colors)-1)]
        img[m] = (0.45 * img[m] + 0.55 * overlay[m]).astype(np.uint8)
    Image.fromarray(img).save(path)


def write_crop(scene_i, inst_idx, cid, raw_label, cad_name, depth, mask, crop_dir: Path):
    ys, xs = np.where(mask)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    d = depth[y0:y1, x0:x1].copy()
    m = mask[y0:y1, x0:x1].astype(bool)
    d[~m] = np.nan
    np.savez_compressed(
        crop_dir / f"scene{scene_i:05d}_inst{inst_idx:02d}_cat{cid:02d}.npz",
        depth=d.astype(np.float32),
        mask=m,
        label=np.array(cid, np.int32),
        quat_wxyz=np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float64),
        euler_zyx_deg=np.asarray([0.0, 0.0, 0.0], dtype=np.float64),
        bbox_yxyx=np.asarray([y0, x0, y1, x1], dtype=np.int32),
        stl=np.asarray(f"{cad_name}.stl"),
        raw_label=np.asarray(raw_label),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--depth_dir", required=True)
    ap.add_argument("--glob", default="shot_*_g1.npy")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--label_dir", default=None)
    group.add_argument("--label_zip", default=None)
    ap.add_argument("--out_root", required=True)
    ap.add_argument("--ref_dataset", default="./data/2d_dataset")
    ap.add_argument("--real_uint16_max_depth_m", type=float, default=10.0)
    ap.add_argument("--center_crop", default="1/6,5/6")
    ap.add_argument("--depth_keep_range", default="0.40,0.60")
    ap.add_argument("--foreground_depth_mode", choices=["all", "label", "dilated_label"], default="dilated_label", help="For real C fine-tuning, optionally remove non-label depth before saving/training. This prevents side walls from dominating depth normalization.")
    ap.add_argument("--foreground_dilate_px", type=int, default=8, help="Dilation radius for --foreground_depth_mode dilated_label.")
    ap.add_argument("--min_object_depth_valid_ratio", type=float, default=0.02, help="Warn when an object polygon has too little valid depth after range filtering.")
    ap.add_argument("--min_mask_area", type=int, default=20)
    ap.add_argument("--train_count", type=int, default=24)
    ap.add_argument("--val_count", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    depth_dir = Path(args.depth_dir)
    label_dir = Path(args.label_dir) if args.label_dir else None
    label_zip = Path(args.label_zip) if args.label_zip else None
    out = Path(args.out_root)
    if out.exists() and args.overwrite:
        import shutil
        shutil.rmtree(out)
    npz_dir = out / "npz"
    crop_dir = out / "crops"
    vis_dir = out / "vis"
    split_dir = out / "splits"
    for d in [npz_dir, crop_dir, vis_dir, split_dir]:
        d.mkdir(parents=True, exist_ok=True)

    ref_map = build_ref_cad_category_map(Path(args.ref_dataset) if args.ref_dataset else None)
    depth_files = sorted(depth_dir.glob(args.glob))
    if not depth_files:
        raise FileNotFoundError(f"No depth files found in {depth_dir} matching {args.glob}")

    keep_range = parse_range(args.depth_keep_range)
    scene_items = []
    stats = []
    for scene_i, depth_path in enumerate(depth_files):
        depth_full = load_depth_npy(depth_path, args.real_uint16_max_depth_m)
        H0, W0 = depth_full.shape
        y0, x0, y1, x1 = crop_box((H0, W0), args.center_crop)
        depth = depth_full[y0:y1, x0:x1].copy()
        if keep_range is not None:
            lo, hi = keep_range
            invalid = ~np.isfinite(depth) | (depth < lo) | (depth > hi)
            depth[invalid] = np.nan

        label_obj = read_label_json(depth_path, label_dir, label_zip)
        if label_obj is None:
            print(f"[warn] missing label for {depth_path.name}; writing empty scene")
            label_obj = {"shapes": [], "imageHeight": H0, "imageWidth": W0}

        H, W = depth.shape
        inst_id = np.zeros((H, W), dtype=np.int32)
        category_id = np.zeros((H, W), dtype=np.int32)
        meta_instances = {}
        visible_ids = []
        inst_idx = 0

        # First rasterize all LabelMe polygons. Then optionally remove non-label
        # depth from the input map. This is important for C real fine-tuning: nearby
        # side walls / container surfaces can otherwise dominate robust depth
        # normalization and compress actual object depth toward zero.
        shape_records = []
        union_mask = np.zeros((H, W), dtype=bool)
        for shape in label_obj.get("shapes", []):
            raw_label = str(shape.get("label", "")).strip()
            if not raw_label:
                continue
            cad_name = canonical_cad_name(raw_label)
            cid = ref_map.get(cad_name)
            if cid is None:
                cid = fallback_category_id(raw_label)
            if cid is None or cid <= 0:
                print(f"[warn] cannot map label '{raw_label}' in {depth_path.name}; skipping")
                continue
            mask = label_to_mask(shape, label_obj, (H0, W0), (y0, x0, y1, x1), (H, W))
            if int(mask.sum()) < args.min_mask_area:
                continue
            union_mask |= mask
            shape_records.append((shape, raw_label, cad_name, int(cid), mask))

        depth_input_mask = None
        if args.foreground_depth_mode == "label":
            depth_input_mask = union_mask
        elif args.foreground_depth_mode == "dilated_label":
            depth_input_mask = dilate_binary_mask(union_mask, args.foreground_dilate_px)

        depth_before_fg = depth.copy()
        if depth_input_mask is not None:
            depth[~depth_input_mask] = np.nan

        for shape, raw_label, cad_name, cid, mask in shape_records:
            inst_idx += 1
            inst_id[mask] = inst_idx
            category_id[mask] = int(cid)
            visible_ids.append(inst_idx)
            mask_area = int(mask.sum())
            finite_in_mask = int((mask & np.isfinite(depth)).sum())
            finite_in_mask_before_fg = int((mask & np.isfinite(depth_before_fg)).sum())
            valid_ratio = float(finite_in_mask / max(1, mask_area))
            if valid_ratio < float(args.min_object_depth_valid_ratio):
                print(f"[warn] low valid depth in object {raw_label} of {depth_path.name}: {valid_ratio:.3f}")
            meta_instances[str(inst_idx)] = {
                "category_id": int(cid),
                "stl": f"{cad_name}.stl",
                "quat_wxyz": [1.0, 0.0, 0.0, 0.0],
                "euler_zyx_deg": [0.0, 0.0, 0.0],
                "raw_label": raw_label,
                "cad_name": cad_name,
                "source_depth": str(depth_path.resolve()),
                "source_label": str((label_dir / f"{depth_path.stem}.json").resolve()) if label_dir else f"zip://{label_zip}::{depth_path.stem}.json",
                "mask_area": mask_area,
                "finite_depth_pixels_in_mask": finite_in_mask,
                "finite_depth_pixels_in_mask_before_foreground_filter": finite_in_mask_before_fg,
                "finite_depth_ratio_in_mask": valid_ratio,
            }
            write_crop(scene_i, inst_idx, int(cid), raw_label, cad_name, depth, mask, crop_dir)

        meta = {
            "scene_idx": scene_i,
            "scene_id": depth_path.stem,
            "bg_kind": "real_labelme",
            "resolution": [H, W],
            "source_depth_shape": [H0, W0],
            "crop_bbox_yxyx": [y0, x0, y1, x1],
            "depth_keep_range": args.depth_keep_range,
            "foreground_depth_mode": args.foreground_depth_mode,
            "foreground_dilate_px": args.foreground_dilate_px,
            "n_parts_dropped": len(visible_ids),
            "visible_inst_ids": visible_ids,
            "instances": meta_instances,
            "conventions": {
                "depth_unit": "meter",
                "renderer": "real_depth_labelme",
                "target_mask": "LabelMe polygon in cropped depth coordinates",
            },
        }
        np.savez_compressed(
            npz_dir / f"scene_{scene_i:05d}.npz",
            depth=depth.astype(np.float32),
            inst_id=inst_id.astype(np.int32),
            category_id=category_id.astype(np.int32),
            meta=np.asarray(json.dumps(meta, ensure_ascii=False)),
        )
        save_vis(depth, inst_id, category_id, vis_dir / f"scene_{scene_i:05d}.png")
        scene_item = {
            "scene_id": f"scene_{scene_i:05d}",
            "source_id": depth_path.stem,
            "scene_npz": str((npz_dir / f"scene_{scene_i:05d}.npz").resolve()),
            "source_depth_path": str(depth_path.resolve()),
        }
        scene_items.append(scene_item)
        stats.append({
            "scene": depth_path.name,
            "objects": len(visible_ids),
            "finite_depth": int(np.isfinite(depth).sum()),
            "finite_depth_before_foreground_filter": int(np.isfinite(depth_before_fg).sum()),
            "mask_pixels": int((inst_id > 0).sum()),
            "foreground_depth_mode": args.foreground_depth_mode,
        })
        print(f"[{scene_i+1:04d}/{len(depth_files):04d}] {depth_path.name}: objects={len(visible_ids)} finite_depth={stats[-1]['finite_depth']} mask_pixels={stats[-1]['mask_pixels']}")

    rng = random.Random(args.seed)
    idxs = list(range(len(scene_items)))
    rng.shuffle(idxs)
    train_count = min(args.train_count, len(idxs))
    val_count = min(args.val_count, max(0, len(idxs) - train_count))
    splits = {
        "train": idxs[:train_count],
        "val": idxs[train_count:train_count+val_count],
        "test": idxs[train_count+val_count:],
        "all": idxs,
    }
    for name, ids in splits.items():
        (split_dir / f"{name}.json").write_text(json.dumps({
            "split": name,
            "data_root": str(out.resolve()),
            "scenes": [scene_items[i] for i in ids],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "build_summary.json").write_text(json.dumps({
        "num_depth_files": len(depth_files),
        "num_scenes": len(scene_items),
        "ref_category_map_size": len(ref_map),
        "center_crop": args.center_crop,
        "depth_keep_range": args.depth_keep_range,
        "foreground_depth_mode": args.foreground_depth_mode,
        "foreground_dilate_px": args.foreground_dilate_px,
        "splits": {k: len(v) for k, v in splits.items()},
        "stats": stats,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2x2 preview
    imgs = [Image.open(vis_dir / f"scene_{i:05d}.png").convert("RGB") for i in range(min(4, len(scene_items)))]
    if imgs:
        Wp, Hp = imgs[0].size
        canvas = Image.new("RGB", (Wp*2, Hp*2), (0,0,0))
        for i, im in enumerate(imgs):
            canvas.paste(im, ((i % 2) * Wp, (i // 2) * Hp))
        canvas.save(out / "real_labelme_preview_2x2.png")
    print("DONE")
    print(json.dumps({k: len(v) for k, v in splits.items()}, indent=2))


if __name__ == "__main__":
    main()
