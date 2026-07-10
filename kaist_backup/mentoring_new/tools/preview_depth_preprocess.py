from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

from depth_vq_detector.depth_preprocess import (
    apply_center_keep,
    apply_center_crop,
    apply_depth_keep_range,
    avg_pool_depth_edges,
    load_depth,
    parse_center_keep,
    parse_float_range,
    preprocess_metric_depth,
    shift_depth_median_to_range,
)


def _display_near_bright(depth: np.ndarray) -> np.ndarray:
    valid = np.isfinite(depth) & (depth > 0)
    out = np.zeros(depth.shape, dtype=np.float32)
    if int(valid.sum()) < 10:
        return out
    vals = depth[valid]
    p1, p99 = np.percentile(vals, [1, 99])
    z = (depth - p1) / max(float(p99 - p1), 1e-8)
    z = np.clip(z, 0.0, 1.0)
    out[valid] = 1.0 - z[valid]
    return out


def _stats_text(depth: np.ndarray) -> str:
    valid = np.isfinite(depth) & (depth > 0)
    if int(valid.sum()) == 0:
        return "no valid pixels"
    vals = depth[valid]
    return (
        f"valid={valid.mean()*100:.2f}%\n"
        f"mean={float(vals.mean()):.4f}m\n"
        f"p5/p95={float(np.percentile(vals,5)):.4f}/{float(np.percentile(vals,95)):.4f}m"
    )


def _center_keep_from_args(args: argparse.Namespace) -> tuple[float, float, float, float] | None:
    if args.center_keep is not None:
        return parse_center_keep(args.center_keep)
    if args.center_keep_frac is None:
        return None
    frac = float(args.center_keep_frac)
    if frac <= 0 or frac >= 1.0:
        return None
    return (
        0.5 * (1.0 - frac),
        0.5 * (1.0 + frac),
        0.5 * (1.0 - frac),
        0.5 * (1.0 + frac),
    )


def _roi_rectangle(shape: tuple[int, int], keep: tuple[float, float, float, float] | None):
    if keep is None:
        return None
    y0f, y1f, x0f, x1f = keep
    h, w = shape
    y0, y1 = int(round(h * y0f)), int(round(h * y1f))
    x0, x1 = int(round(w * x0f)), int(round(w * x1f))
    return x0, y0, x1 - x0, y1 - y0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Preview depth preprocessing. For pseudo scene_*.npz, depth is already float32 meters; "
            "for real shot_*.npy uint16, use --real_uint16_max_depth_m 10.0."
        )
    )
    parser.add_argument("--depth", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--depth_scale", type=float, default=None, help="Multiplier applied only to integer depth arrays by default.")
    parser.add_argument(
        "--real_uint16_max_depth_m",
        type=float,
        default=None,
        help="For real uint16 shots: depth_m = raw * max_depth_m / 65535. Ignored for float32 scene npz unless --force_depth_scale is set.",
    )
    parser.add_argument("--force_depth_scale", action="store_true", help="Also apply depth_scale to float depth arrays. Normally do not use for scene npz.")
    parser.add_argument(
        "--center_keep",
        default=None,
        help="ROI as '1/6,5/6' or 'y0,y1,x0,x1'. This zeros outside the ROI. For real test/inference preview, prefer --center_crop.",
    )
    parser.add_argument(
        "--center_crop",
        default=None,
        help="Crop to the center ROI instead of zeroing outside. Example: '1/6,5/6'.",
    )
    parser.add_argument(
        "--center_keep_frac",
        type=float,
        default=None,
        help="Backward-compatible shortcut. 0.8 keeps central 80%% on x/y. Omit to disable.",
    )
    parser.add_argument(
        "--target_median_range",
        default=None,
        help="Training-domain shift target, e.g. '0.45,0.55'. Applied before depth gate and avg pooling.",
    )
    parser.add_argument("--randomize_target_median", action="store_true", help="Sample inside --target_median_range. Default uses midpoint for reproducible preview.")
    parser.add_argument("--depth_min_m", type=float, default=None)
    parser.add_argument("--depth_max_m", type=float, default=None)
    parser.add_argument("--avg_pool_kernel", "--edge_blur_kernel", dest="avg_pool_kernel", type=int, default=3, help="Odd kernel for height-preserving valid-aware edge blur. Legacy alias: --avg_pool_kernel.")
    parser.add_argument("--avg_pool_valid_threshold", "--edge_blur_valid_threshold", dest="avg_pool_valid_threshold", type=float, default=0.05, help="Valid support threshold for the boundary halo. 0.03~0.10 gives soft edges; 0.5 keeps a tighter silhouette.")
    args = parser.parse_args()

    depth_scale = args.depth_scale
    if depth_scale is None and args.real_uint16_max_depth_m is not None:
        depth_scale = float(args.real_uint16_max_depth_m) / 65535.0

    depth_path = Path(args.depth)
    depth = load_depth(
        depth_path,
        depth_scale=depth_scale,
        zero_to_nan=bool(args.real_uint16_max_depth_m is not None and depth_path.suffix.lower() == ".npy"),
        scale_float_depth=bool(args.force_depth_scale),
    )
    raw_metric = depth.astype(np.float32).copy()

    if args.center_crop is not None and (args.center_keep is not None or args.center_keep_frac is not None):
        raise ValueError("Use either --center_crop or --center_keep/--center_keep_frac, not both.")

    crop_keep = parse_center_keep(args.center_crop) if args.center_crop is not None else None
    keep = _center_keep_from_args(args)
    if crop_keep is not None:
        centered, crop_box_yxyx = apply_center_crop(raw_metric, crop_keep)
    else:
        centered = apply_center_keep(raw_metric, keep=keep, fill_value=0.0)
        crop_box_yxyx = None

    target_range = parse_float_range(args.target_median_range)
    shifted = shift_depth_median_to_range(
        centered,
        target_range,
        rng=np.random.default_rng(0),
        randomize=bool(args.randomize_target_median),
    )

    depth_range = None if args.depth_min_m is None and args.depth_max_m is None else (
        args.depth_min_m if args.depth_min_m is not None else 0.0,
        args.depth_max_m if args.depth_max_m is not None else float("inf"),
    )
    gated = apply_depth_keep_range(shifted, depth_range, fill_value=0.0)
    blurred = avg_pool_depth_edges(
        gated,
        kernel_size=int(args.avg_pool_kernel),
        valid_threshold=float(args.avg_pool_valid_threshold),
        fill_value=0.0,
    )

    panel3_title = "median shift"
    if target_range is None:
        panel3_title = "center keep"
        panel3_arr = centered
    else:
        panel3_arr = shifted
    if depth_range is not None:
        panel3_title = panel3_title + " + depth gate"
        panel3_arr = gated

    panels = [
        ("raw metric depth", raw_metric),
        ("center crop" if crop_keep is not None else ("center keep" if keep is not None else "no center crop"), centered),
        (panel3_title, panel3_arr),
        (f"+ {args.avg_pool_kernel}x{args.avg_pool_kernel} valid-aware edge blur", blurred),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(14, 8))
    rect = _roi_rectangle(raw_metric.shape, crop_keep if crop_keep is not None else keep)
    for ax, (title, d) in zip(axes.ravel(), panels):
        ax.imshow(_display_near_bright(d), cmap="gray", vmin=0, vmax=1)
        if title == "raw metric depth" and rect is not None:
            ax.add_patch(Rectangle((rect[0], rect[1]), rect[2], rect[3], fill=False, edgecolor="yellow", linewidth=2))
        ax.set_title(title)
        ax.axis("off")
        ax.text(
            0.01,
            0.99,
            _stats_text(d),
            transform=ax.transAxes,
            va="top",
            ha="left",
            color="white",
            fontsize=10,
            bbox={"facecolor": "black", "alpha": 0.55, "pad": 4},
        )
    fig.tight_layout()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160, bbox_inches="tight")
    print(f"saved {out}")

    if depth_path.suffix.lower() == ".npz" and args.real_uint16_max_depth_m is not None and not args.force_depth_scale:
        print("note: --real_uint16_max_depth_m was ignored because input is float scene npz. This is expected for pseudo training data.")


if __name__ == "__main__":
    main()
