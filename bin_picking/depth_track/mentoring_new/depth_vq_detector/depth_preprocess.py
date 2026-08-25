from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image


# ⭐ 2026-08-25 추가 = RGB 융합 모드 (`zvrgb`, `zrgb`)
#   태민님 8/21 궁극 목표 = *"Depth랑 RGB 무조건 연동"*.
#   8/24에 체크포인트를 열어 첫 conv 가 (32,2,3,3) 2채널로 **물리적으로 박혀** 있음을
#   확인했다 ⇒ 후처리로 얻는 이득이 아니라 **재학습이 필수**다.
#
# 🚨 기존 모드는 한 글자도 바꾸지 않았다 — depth-only 재현성이 걸려 있다
#    (T100 배포 모델이 `zv` 로 학습됐고 그 값이 모든 기준선의 근거다).
VALID_INPUT_MODES = {"z", "zv", "xyzv", "xyznv", "zrgb", "zvrgb"}

# RGB 를 요구하는 모드 — 호출자가 rgb 를 안 주면 **조용히 0으로 채우지 않고 예외**를 던진다.
RGB_INPUT_MODES = {"zrgb", "zvrgb"}


def input_channels_for_mode(mode: str) -> int:
    if mode == "z":
        return 1
    if mode == "zv":
        return 2
    if mode == "xyzv":
        return 4
    if mode == "xyznv":
        return 7
    if mode == "zrgb":      # z + R,G,B
        return 4
    if mode == "zvrgb":     # z + valid + R,G,B  ⭐ 기본 권장(zv 의 자연 확장)
        return 5
    raise ValueError(f"Unknown input mode: {mode}. Choose one of {sorted(VALID_INPUT_MODES)}")


def load_json(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_depth(
    path: str | Path,
    depth_scale: float | None = None,
    zero_to_nan: bool = False,
    scale_float_depth: bool = False,
) -> np.ndarray:
    """Load a depth map as float32.

    Supported formats:
      - .npy: array depth. Real demonstration shots are often uint16.
      - .npz: key "depth" is used when available.
      - PNG/TIFF-like image files.

    For real uint16 shots captured with a global 0..max-depth encoding, pass
    depth_scale=max_depth_m/65535 and zero_to_nan=True. Example for 10 m scale:

        depth_m = raw_uint16 * (10.0 / 65535.0)
        raw == 0 -> NaN invalid/background

    Provided pseudo scene npz files already store metric depth in meters and use
    NaN as background, so normally no depth_scale is needed for them.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".npy":
        arr = np.load(path)
        raw_dtype = arr.dtype
        depth = arr.astype(np.float32)
    elif path.suffix.lower() == ".npz":
        data = np.load(path, allow_pickle=True)
        key = "depth" if "depth" in data.files else data.files[0]
        arr = data[key]
        raw_dtype = arr.dtype
        depth = arr.astype(np.float32)
    else:
        img = Image.open(path)
        arr = np.array(img)
        if arr.ndim == 3:
            # Debug only: never train from 8-bit visualization PNGs.
            arr = arr[..., 0]
        raw_dtype = arr.dtype
        depth = arr.astype(np.float32)

    invalid_zero = depth <= 0
    if depth_scale is not None:
        # Pseudo scene npz files already store float32 metric depth in meters.
        # Real demonstration .npy files are uint16 encoded and need scaling.
        # Therefore, by default, apply depth_scale only to integer arrays.
        if np.issubdtype(raw_dtype, np.integer) or bool(scale_float_depth):
            depth = depth * float(depth_scale)
    if zero_to_nan:
        depth = depth.astype(np.float32)
        depth[invalid_zero] = np.nan
    return depth.astype(np.float32)


def parse_fraction(value: str | float | int) -> float:
    """Parse '0.1667' or '1/6' into a float."""
    if isinstance(value, (float, int)):
        return float(value)
    s = str(value).strip()
    if "/" in s:
        a, b = s.split("/", 1)
        return float(a) / float(b)
    return float(s)


def parse_float_range(value: str | None) -> tuple[float, float] | None:
    """Parse '0.45,0.55' into a pair. Supports fractions as well."""
    if value is None or str(value).strip().lower() in {"", "none", "off"}:
        return None
    parts = [p.strip() for p in str(value).split(",") if p.strip()]
    if len(parts) != 2:
        raise ValueError("range must be formatted as min,max; e.g. 0.45,0.55")
    lo, hi = parse_fraction(parts[0]), parse_fraction(parts[1])
    if hi < lo:
        lo, hi = hi, lo
    return float(lo), float(hi)


def parse_center_keep(value: str | None) -> tuple[float, float, float, float] | None:
    """Parse center keep fractions.

    Accepted forms:
      - '1/6,5/6' -> y0=1/6,y1=5/6,x0=1/6,x1=5/6
      - '1/6,5/6,1/6,5/6' -> y0,y1,x0,x1
      - 'none' / empty -> None
    """
    if value is None or str(value).strip().lower() in {"", "none", "off"}:
        return None
    parts = [p.strip() for p in str(value).split(",") if p.strip()]
    if len(parts) == 2:
        y0, y1 = parse_fraction(parts[0]), parse_fraction(parts[1])
        x0, x1 = y0, y1
    elif len(parts) == 4:
        y0, y1, x0, x1 = [parse_fraction(p) for p in parts]
    else:
        raise ValueError("center_keep must be 'y0,y1' or 'y0,y1,x0,x1', e.g. '1/6,5/6'")
    vals = [float(y0), float(y1), float(x0), float(x1)]
    if not (0.0 <= vals[0] < vals[1] <= 1.0 and 0.0 <= vals[2] < vals[3] <= 1.0):
        raise ValueError(f"invalid center_keep fractions: {vals}")
    return vals[0], vals[1], vals[2], vals[3]


def apply_center_keep(
    depth: np.ndarray,
    keep: tuple[float, float, float, float] | None,
    fill_value: float = 0.0,
) -> np.ndarray:
    """Keep only the center ROI and set the outside to fill_value.

    This is intended for real-shot inference where nearby container/wall pixels
    near the image boundary are detected as false objects. For a 1/6~5/6 keep
    window, call:

        apply_center_keep(depth, (1/6, 5/6, 1/6, 5/6), fill_value=0.0)

    The model later treats fill_value=0 as invalid because valid = depth > 0.
    """
    if keep is None:
        return depth.astype(np.float32)
    y0f, y1f, x0f, x1f = keep
    h, w = depth.shape
    y0 = int(round(h * y0f))
    y1 = int(round(h * y1f))
    x0 = int(round(w * x0f))
    x1 = int(round(w * x1f))
    out = np.full_like(depth.astype(np.float32), float(fill_value), dtype=np.float32)
    out[y0:y1, x0:x1] = depth[y0:y1, x0:x1]
    return out.astype(np.float32)



# -----------------------------------------------------------------------------
# Real-shot center-crop compatibility helpers
# -----------------------------------------------------------------------------

def fractional_box_to_pixels(
    shape: tuple[int, int],
    box_frac: tuple[float, float, float, float] | None,
) -> tuple[int, int, int, int] | None:
    """Convert fractional (y0,y1,x0,x1) ROI to integer (y0,x0,y1,x1).

    parse_center_keep("1/6,5/6") returns (y0f,y1f,x0f,x1f).
    This helper converts that fractional ROI to pixel coordinates in the
    original image.  The output order is y0,x0,y1,x1 because LabelMe and
    inference code use crop_bbox_yxyx.
    """
    if box_frac is None:
        return None
    y0f, y1f, x0f, x1f = box_frac
    h, w = int(shape[0]), int(shape[1])
    y0 = int(round(h * float(y0f)))
    y1 = int(round(h * float(y1f)))
    x0 = int(round(w * float(x0f)))
    x1 = int(round(w * float(x1f)))
    y0, y1 = max(0, min(h, y0)), max(0, min(h, y1))
    x0, x1 = max(0, min(w, x0)), max(0, min(w, x1))
    if not (y0 < y1 and x0 < x1):
        raise ValueError(f"empty crop from fractions={box_frac} for shape={shape}")
    return y0, x0, y1, x1


def apply_center_crop(
    depth: np.ndarray,
    crop: tuple[float, float, float, float] | None,
) -> tuple[np.ndarray, tuple[int, int, int, int] | None]:
    """Crop to the center ROI instead of zeroing the outside.

    This is used for real-shot inference/evaluation.  Unlike
    apply_center_keep(), it changes image shape so the central object cluster
    fills the input and visualization.  Returned crop box is (y0,x0,y1,x1) in
    the original full-frame depth image.
    """
    if crop is None:
        return depth.astype(np.float32), None
    box = fractional_box_to_pixels(depth.shape, crop)
    assert box is not None
    y0, x0, y1, x1 = box
    return depth.astype(np.float32)[y0:y1, x0:x1].copy(), box


def adjust_camera_for_crop(
    camera: dict[str, Any] | None,
    crop_box_yxyx: tuple[int, int, int, int] | None,
) -> dict[str, Any]:
    """Adjust intrinsics after cropping a depth image.

    For crop box (y0,x0,y1,x1), principal point shifts by (-x0,-y0).
    Width/height keys are also updated when present.
    """
    cam = dict(camera or {})
    if crop_box_yxyx is None:
        return cam
    y0, x0, y1, x1 = crop_box_yxyx
    if "cx" in cam and cam["cx"] is not None:
        cam["cx"] = float(cam["cx"]) - float(x0)
    if "cy" in cam and cam["cy"] is not None:
        cam["cy"] = float(cam["cy"]) - float(y0)
    for key in ("width", "w", "image_width"):
        if key in cam:
            cam[key] = int(x1 - x0)
    for key in ("height", "h", "image_height"):
        if key in cam:
            cam[key] = int(y1 - y0)
    return cam


def adjust_camera_for_resize(
    camera: dict[str, Any] | None,
    from_hw: tuple[int, int] | None,
    to_hw: tuple[int, int] | None,
) -> dict[str, Any]:
    """Adjust intrinsics after resizing from (H,W) to (H,W)."""
    cam = dict(camera or {})
    if from_hw is None or to_hw is None:
        return cam
    h0, w0 = int(from_hw[0]), int(from_hw[1])
    h1, w1 = int(to_hw[0]), int(to_hw[1])
    if h0 <= 0 or w0 <= 0:
        return cam
    sx = float(w1) / float(w0)
    sy = float(h1) / float(h0)
    if "fx" in cam and cam["fx"] is not None:
        cam["fx"] = float(cam["fx"]) * sx
    if "fy" in cam and cam["fy"] is not None:
        cam["fy"] = float(cam["fy"]) * sy
    if "cx" in cam and cam["cx"] is not None:
        cam["cx"] = float(cam["cx"]) * sx
    if "cy" in cam and cam["cy"] is not None:
        cam["cy"] = float(cam["cy"]) * sy
    for key in ("width", "w", "image_width"):
        if key in cam:
            cam[key] = w1
    for key in ("height", "h", "image_height"):
        if key in cam:
            cam[key] = h1
    return cam

def apply_depth_keep_range(
    depth: np.ndarray,
    keep_range: tuple[float, float] | None,
    fill_value: float = 0.0,
) -> np.ndarray:
    """Keep metric depth values inside [min,max]; set others to fill_value."""
    if keep_range is None:
        return depth.astype(np.float32)
    lo, hi = keep_range
    out = depth.astype(np.float32).copy()
    valid = np.isfinite(out) & (out > 0)
    keep = valid & (out >= float(lo)) & (out <= float(hi))
    out[~keep] = float(fill_value)
    return out.astype(np.float32)


def shift_depth_median_to_range(
    depth: np.ndarray,
    target_range: tuple[float, float] | None,
    rng: np.random.Generator | None = None,
    randomize: bool = True,
) -> np.ndarray:
    """Add a constant depth offset so the valid-depth median falls in target_range.

    This simulates rendering/capturing the same scene at a different camera-object
    distance without changing masks or 2D geometry. For real 45~50 cm data, a
    useful training range is 0.45~0.55 m, optionally widened to 0.35~0.55 m for
    robustness.
    """
    if target_range is None:
        return depth.astype(np.float32)
    valid = np.isfinite(depth) & (depth > 0)
    if int(valid.sum()) < 10:
        return depth.astype(np.float32)
    lo, hi = target_range
    if randomize:
        rng = rng or np.random.default_rng()
        target = float(rng.uniform(lo, hi))
    else:
        target = 0.5 * (float(lo) + float(hi))
    med = float(np.median(depth[valid]))
    out = depth.astype(np.float32).copy()
    out[valid] = out[valid] + (target - med)
    # Non-positive shifted values are invalid for our model input.
    out[np.isfinite(out) & (out <= 0)] = np.nan
    return out.astype(np.float32)


def _gaussian_kernel2d(kernel_size: int, sigma: float | None = None) -> torch.Tensor:
    """Create a normalized 2D Gaussian kernel as [1,1,k,k]."""
    k = int(kernel_size or 1)
    if k <= 1:
        return torch.ones((1, 1, 1, 1), dtype=torch.float32)
    if k % 2 == 0:
        raise ValueError("blur kernel_size must be odd, e.g. 3, 5, 7")
    if sigma is None or float(sigma) <= 0:
        # OpenCV-like automatic sigma. k=3 -> ~0.8, k=5 -> ~1.1.
        sigma = max(0.5, 0.3 * ((k - 1) * 0.5 - 1.0) + 0.8)
    ax = torch.arange(k, dtype=torch.float32) - (k - 1) / 2.0
    yy, xx = torch.meshgrid(ax, ax, indexing="ij")
    ker = torch.exp(-(xx * xx + yy * yy) / (2.0 * float(sigma) ** 2))
    ker = ker / ker.sum().clamp_min(1e-8)
    return ker[None, None].contiguous()


def valid_aware_depth_blur(
    depth: np.ndarray,
    kernel_size: int = 1,
    valid_threshold: float = 0.05,
    fill_value: float = 0.0,
    sigma: float | None = None,
    preserve_original_valid_values: bool = True,
) -> np.ndarray:
    """Edge blur without flattening metric depth/height.

    The old average pooling mixed valid depth with zero-filled background:

        avg(depth_with_background_zero)

    That pulls boundary values toward 0 and can make objects look flat. This
    function instead uses a valid-normalized Gaussian blur:

        blurred = conv(depth * valid, gaussian) / conv(valid, gaussian)

    Invalid/background pixels do not contribute fake zero depth. With
    preserve_original_valid_values=True, existing valid pixels keep their exact
    original metric depth and only a thin boundary halo receives blurred depth.
    That is the safest option when we want sensor-like edge softness without
    smearing height.
    """
    k = int(kernel_size or 1)
    if k <= 1:
        return depth.astype(np.float32)
    if k % 2 == 0:
        raise ValueError("blur kernel_size must be odd, e.g. 3, 5, 7")

    depth_f = depth.astype(np.float32)
    valid = (np.isfinite(depth_f) & (depth_f > 0)).astype(np.float32)
    if int(valid.sum()) < 1:
        return np.full_like(depth_f, float(fill_value), dtype=np.float32)

    ker = _gaussian_kernel2d(k, sigma=sigma)
    pad = k // 2
    d_t = torch.from_numpy((np.nan_to_num(depth_f, nan=0.0, posinf=0.0, neginf=0.0) * valid)[None, None]).float()
    v_t = torch.from_numpy(valid[None, None]).float()
    numerator = F.conv2d(d_t, ker, stride=1, padding=pad)[0, 0].numpy()
    support = F.conv2d(v_t, ker, stride=1, padding=pad)[0, 0].numpy()

    out = np.full_like(depth_f, float(fill_value), dtype=np.float32)
    good = support > float(valid_threshold)
    out[good] = numerator[good] / np.maximum(support[good], 1e-6)

    if preserve_original_valid_values:
        original_valid = valid.astype(bool)
        out[original_valid] = depth_f[original_valid]
    return out.astype(np.float32)


def avg_pool_depth_edges(
    depth: np.ndarray,
    kernel_size: int = 1,
    valid_threshold: float = 0.05,
    fill_value: float = 0.0,
) -> np.ndarray:
    """Backward-compatible wrapper for the old avg-pool option.

    Existing commands using --train_avg_pool_kernel still work, but the actual
    operation is now height-preserving, valid-aware edge blur.
    """
    return valid_aware_depth_blur(
        depth,
        kernel_size=kernel_size,
        valid_threshold=valid_threshold,
        fill_value=fill_value,
        sigma=None,
        preserve_original_valid_values=True,
    )



# -----------------------------------------------------------------------------
# Synthetic-to-real sensorization utilities for experiments.
# These augment the pseudo depth input only.  They intentionally do not modify
# instance/semantic target masks in the dataset.
# -----------------------------------------------------------------------------

def quantize_depth_uint16_like(
    depth: np.ndarray,
    max_depth_m: float | None = None,
) -> np.ndarray:
    """Simulate the real uint16 depth export then convert back to meters.

    Real shots observed in this project are uint16 arrays that are consistent
    with depth_m = raw * max_depth_m / 65535, with raw=0 as invalid.  Pseudo
    scene npz files are metric float32 + NaN background, so this transform adds
    the same quantization regime without changing the target labels.
    """
    if max_depth_m is None or float(max_depth_m) <= 0:
        return depth.astype(np.float32)
    out = depth.astype(np.float32).copy()
    valid = np.isfinite(out) & (out > 0)
    raw = np.zeros_like(out, dtype=np.uint16)
    scaled = np.clip(out[valid] / float(max_depth_m) * 65535.0, 1.0, 65535.0)
    raw[valid] = np.round(scaled).astype(np.uint16)
    out2 = raw.astype(np.float32) * (float(max_depth_m) / 65535.0)
    out2[raw == 0] = np.nan
    return out2.astype(np.float32)


def add_depth_sensor_noise(
    depth: np.ndarray,
    sigma_m: float = 0.0,
    rel_sigma: float = 0.0,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Add depth noise only on valid pixels.

    sigma_m is absolute Gaussian noise in meters. rel_sigma adds a multiplicative
    term proportional to depth.  Both are intentionally modest by default.
    """
    sigma_m = float(sigma_m or 0.0)
    rel_sigma = float(rel_sigma or 0.0)
    if sigma_m <= 0 and rel_sigma <= 0:
        return depth.astype(np.float32)
    rng = rng or np.random.default_rng()
    out = depth.astype(np.float32).copy()
    valid = np.isfinite(out) & (out > 0)
    if int(valid.sum()) < 1:
        return out
    sigma = sigma_m + rel_sigma * np.maximum(out[valid], 0.0)
    out[valid] = out[valid] + rng.normal(0.0, sigma).astype(np.float32)
    out[np.isfinite(out) & (out <= 0)] = np.nan
    return out.astype(np.float32)


def _binary_dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return mask.astype(bool)
    m = torch.from_numpy(mask.astype(np.float32)[None, None])
    k = 2 * int(radius) + 1
    y = F.max_pool2d(m, kernel_size=k, stride=1, padding=int(radius))[0, 0].numpy()
    return y > 0.5


def _binary_erode(mask: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return mask.astype(bool)
    return ~_binary_dilate(~mask.astype(bool), radius)


def _boundary_band(valid: np.ndarray, radius: int = 2) -> np.ndarray:
    valid_b = valid.astype(bool)
    dil = _binary_dilate(valid_b, int(radius))
    ero = _binary_erode(valid_b, int(radius))
    return dil & (~ero)


def corrupt_depth_validity(
    depth: np.ndarray,
    *,
    random_dropout_prob: float = 0.0,
    boundary_dropout_prob: float = 0.0,
    boundary_radius: int = 2,
    hole_prob: float = 0.0,
    hole_radius_range: tuple[int, int] = (1, 3),
    target_valid_ratio_range: tuple[float, float] | None = None,
    fill_value: float = np.nan,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Corrupt validity mask to resemble sparse/noisy real depth.

    This is different from blur: metric height values are not averaged.  We drop
    or punch out valid pixels, especially around boundaries where real depth
    sensors often lose thin edges and silhouettes.
    """
    rng = rng or np.random.default_rng()
    out = depth.astype(np.float32).copy()
    valid = np.isfinite(out) & (out > 0)
    if int(valid.sum()) < 1:
        return out

    drop = np.zeros_like(valid, dtype=bool)

    p = float(random_dropout_prob or 0.0)
    if p > 0:
        drop |= valid & (rng.random(valid.shape) < p)

    bp = float(boundary_dropout_prob or 0.0)
    if bp > 0:
        band = _boundary_band(valid, radius=max(1, int(boundary_radius)))
        drop |= band & valid & (rng.random(valid.shape) < bp)

    hp = float(hole_prob or 0.0)
    if hp > 0:
        h, w = valid.shape
        num_valid = int(valid.sum())
        # hole_prob is interpreted as approximate holes per 10k valid pixels.
        expected = hp * max(num_valid / 10000.0, 0.25)
        n_holes = int(rng.poisson(expected))
        ys, xs = np.where(valid)
        if n_holes > 0 and len(xs) > 0:
            r_lo, r_hi = int(hole_radius_range[0]), int(hole_radius_range[1])
            r_lo, r_hi = max(1, r_lo), max(r_lo, r_hi)
            yy, xx = np.ogrid[:h, :w]
            for _ in range(n_holes):
                j = int(rng.integers(0, len(xs)))
                cy, cx = int(ys[j]), int(xs[j])
                rad = int(rng.integers(r_lo, r_hi + 1))
                hole = (yy - cy) ** 2 + (xx - cx) ** 2 <= rad * rad
                drop |= hole & valid

    if target_valid_ratio_range is not None:
        lo, hi = target_valid_ratio_range
        lo, hi = float(lo), float(hi)
        if hi < lo:
            lo, hi = hi, lo
        target = float(rng.uniform(lo, hi))
        cur = float(valid.mean())
        # Only downsample validity.  We do not hallucinate extra depth pixels.
        if cur > target > 0:
            keep_prob = max(0.0, min(1.0, target / max(cur, 1e-8)))
            drop |= valid & (rng.random(valid.shape) > keep_prob)

    out[drop] = fill_value
    return out.astype(np.float32)

def preprocess_metric_depth(
    depth: np.ndarray,
    *,
    center_keep: tuple[float, float, float, float] | None = None,
    center_fill_value: float = 0.0,
    keep_depth_range: tuple[float, float] | None = None,
    range_fill_value: float = 0.0,
    target_median_range: tuple[float, float] | None = None,
    target_median_random: bool = True,
    avg_pool_kernel: int = 1,
    avg_pool_valid_threshold: float = 0.05,
    pseudo_uint16_max_depth_m: float | None = None,
    noise_sigma_m: float = 0.0,
    noise_rel_sigma: float = 0.0,
    random_dropout_prob: float = 0.0,
    boundary_dropout_prob: float = 0.0,
    boundary_radius: int = 2,
    hole_prob: float = 0.0,
    target_valid_ratio_range: tuple[float, float] | None = None,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Apply domain-gap preprocessing to metric depth before make_depth_input.

    Order matters for pseudo training:
      center/deployment ROI -> median shift -> metric depth gate -> edge blur.

    The edge blur is valid-aware and does not average depth with zero background.
    GT instance masks are intentionally left untouched in the dataset.
    """
    out = depth.astype(np.float32)
    out = apply_center_keep(out, center_keep, fill_value=center_fill_value)
    out = shift_depth_median_to_range(out, target_median_range, rng=rng, randomize=target_median_random)
    out = apply_depth_keep_range(out, keep_depth_range, fill_value=range_fill_value)
    # Simulate real export/sensor properties.  Keep this after median shift/depth gate
    # so the quantization/noise matches the final metric range.
    out = quantize_depth_uint16_like(out, max_depth_m=pseudo_uint16_max_depth_m)
    out = add_depth_sensor_noise(out, sigma_m=noise_sigma_m, rel_sigma=noise_rel_sigma, rng=rng)
    out = corrupt_depth_validity(
        out,
        random_dropout_prob=random_dropout_prob,
        boundary_dropout_prob=boundary_dropout_prob,
        boundary_radius=boundary_radius,
        hole_prob=hole_prob,
        target_valid_ratio_range=target_valid_ratio_range,
        fill_value=np.nan,
        rng=rng,
    )
    out = avg_pool_depth_edges(out, kernel_size=avg_pool_kernel, valid_threshold=avg_pool_valid_threshold)
    return out.astype(np.float32)


def load_id_map(path: str | Path) -> np.ndarray:
    """Load an integer ID mask from PNG-like files."""
    path = Path(path)
    img = Image.open(path)
    arr = np.array(img)
    if arr.ndim == 2:
        return arr.astype(np.int64)
    if arr.ndim == 3 and arr.shape[2] >= 3:
        rgb = arr[..., :3].reshape(-1, 3)
        unique, inverse = np.unique(rgb, axis=0, return_inverse=True)
        ids = inverse.reshape(arr.shape[:2]).astype(np.int64)
        black_rows = np.where(np.all(unique == 0, axis=1))[0]
        if len(black_rows) > 0 and black_rows[0] != 0:
            black_old = int(black_rows[0])
            remap = np.arange(len(unique), dtype=np.int64)
            remap[0], remap[black_old] = remap[black_old], remap[0]
            inv_remap = np.zeros_like(remap)
            inv_remap[remap] = np.arange(len(remap))
            ids = inv_remap[ids]
        return ids.astype(np.int64)
    raise ValueError(f"Unsupported mask shape {arr.shape} for {path}")


def resize_depth_nan_safe(depth: np.ndarray, size: tuple[int, int] | None) -> np.ndarray:
    """Resize a NaN-background depth image without spreading NaNs."""
    if size is None:
        return depth.astype(np.float32)
    h, w = size
    valid = (np.isfinite(depth) & (depth > 0)).astype(np.float32)
    depth_filled = np.nan_to_num(depth.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    d_t = torch.from_numpy((depth_filled * valid)[None, None])
    v_t = torch.from_numpy(valid[None, None])
    d_r = F.interpolate(d_t, size=(h, w), mode="bilinear", align_corners=False)[0, 0].numpy()
    v_r = F.interpolate(v_t, size=(h, w), mode="bilinear", align_corners=False)[0, 0].numpy()
    out = np.empty((h, w), dtype=np.float32)
    good = v_r > 0.25
    out[good] = d_r[good] / np.maximum(v_r[good], 1e-6)
    out[~good] = np.nan
    return out.astype(np.float32)


def resize_id_map(id_map: np.ndarray | None, size: tuple[int, int] | None) -> np.ndarray | None:
    if id_map is None or size is None:
        return None if id_map is None else id_map.astype(np.int64)
    h, w = size
    t = torch.from_numpy(id_map[None, None].astype(np.float32))
    return F.interpolate(t, size=(h, w), mode="nearest")[0, 0].numpy().astype(np.int64)


def resize_depth_and_masks(
    depth: np.ndarray,
    instance_map: np.ndarray | None,
    semantic_map: np.ndarray | None,
    size: tuple[int, int] | None,
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
    if size is None:
        return depth.astype(np.float32), instance_map, semantic_map
    return (
        resize_depth_nan_safe(depth, size),
        resize_id_map(instance_map, size),
        resize_id_map(semantic_map, size),
    )


def robust_normalize_depth(depth: np.ndarray, valid: np.ndarray) -> tuple[np.ndarray, float, float]:
    z = depth.astype(np.float32).copy()
    if valid.sum() < 10:
        z[:] = 0.0
        return z, 0.0, 1.0
    vals = z[valid]
    med = float(np.median(vals))
    p05, p95 = np.percentile(vals, [5, 95])
    scale = float(max(p95 - p05, 1e-3))
    z = (z - med) / scale
    z[~valid] = 0.0
    z = np.nan_to_num(z, nan=0.0, posinf=0.0, neginf=0.0)
    z = np.clip(z, -5.0, 5.0)
    return z.astype(np.float32), med, scale


def depth_to_xyz(depth: np.ndarray, camera: dict[str, Any] | None) -> np.ndarray:
    """Back-project depth into camera coordinates [H,W,3]."""
    h, w = depth.shape
    ys, xs = np.meshgrid(np.arange(h, dtype=np.float32), np.arange(w, dtype=np.float32), indexing="ij")
    z = depth.astype(np.float32)
    camera = camera or {}
    fx = camera.get("fx")
    fy = camera.get("fy")
    cx = camera.get("cx")
    cy = camera.get("cy")
    if fx is None or fy is None or cx is None or cy is None:
        x = ((xs / max(w - 1, 1)) - 0.5) * z
        y = ((ys / max(h - 1, 1)) - 0.5) * z
    else:
        x = (xs - float(cx)) * z / float(fx)
        y = (ys - float(cy)) * z / float(fy)
    xyz = np.stack([x, y, z], axis=-1).astype(np.float32)
    return xyz


def estimate_normals_from_xyz(xyz: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Estimate surface normals from camera-coordinate XYZ using finite differences."""
    xyz_clean = np.nan_to_num(xyz.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    xyz_pad = np.pad(xyz_clean, ((1, 1), (1, 1), (0, 0)), mode="edge")
    dx = xyz_pad[1:-1, 2:, :] - xyz_pad[1:-1, :-2, :]
    dy = xyz_pad[2:, 1:-1, :] - xyz_pad[:-2, 1:-1, :]
    n = np.cross(dx, dy)
    norm = np.linalg.norm(n, axis=-1, keepdims=True)
    n = n / np.maximum(norm, 1e-6)
    valid_pad = np.pad(valid.astype(bool), ((1, 1), (1, 1)), mode="constant", constant_values=False)
    neigh_valid = (
        valid_pad[1:-1, 1:-1]
        & valid_pad[1:-1, 2:]
        & valid_pad[1:-1, :-2]
        & valid_pad[2:, 1:-1]
        & valid_pad[:-2, 1:-1]
    )
    n[~neigh_valid] = 0.0
    return n.astype(np.float32)


def make_depth_input(
    depth: np.ndarray,
    camera: dict[str, Any] | None = None,
    mode: str = "zv",
) -> np.ndarray:
    """Create depth-only input channels of shape [C,H,W].

    Modes:
      z     : normalized depth
      zv    : normalized depth + valid-depth mask
      xyzv  : normalized camera XYZ + valid-depth mask
      xyznv : normalized camera XYZ + normal XYZ + valid-depth mask
    """
    if mode not in VALID_INPUT_MODES:
        raise ValueError(f"Unknown input mode {mode}. Choose one of {sorted(VALID_INPUT_MODES)}")
    valid = np.isfinite(depth) & (depth > 0)
    z_norm, med, scale = robust_normalize_depth(depth, valid)
    valid_f = valid.astype(np.float32)

    if mode == "z":
        chans = [z_norm]
    elif mode == "zv":
        chans = [z_norm, valid_f]
    else:
        xyz = depth_to_xyz(depth, camera)
        xyz_norm = np.nan_to_num(xyz.copy(), nan=0.0, posinf=0.0, neginf=0.0)
        xyz_norm[..., 2] = z_norm
        xyz_norm[..., 0] = xyz_norm[..., 0] / max(scale, 1e-3)
        xyz_norm[..., 1] = xyz_norm[..., 1] / max(scale, 1e-3)
        xyz_norm[~valid] = 0.0
        chans = [xyz_norm[..., 0], xyz_norm[..., 1], xyz_norm[..., 2]]
        if mode == "xyznv":
            normals = estimate_normals_from_xyz(xyz, valid)
            chans += [normals[..., 0], normals[..., 1], normals[..., 2]]
        chans.append(valid_f)
    return np.stack(chans, axis=0).astype(np.float32)
