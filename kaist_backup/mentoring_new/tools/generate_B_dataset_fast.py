#!/usr/bin/env python3
"""Generate RESCENE-B pseudo dataset from STL using fast point-splat z-buffer rendering.

Updated partial-observation policy:
- soft pixel dropout is always applied to every visible object
- one additional regional corruption may be applied to move the visible ratio toward a
  target range [0.60, 0.80], centered around 0.70 by default
- no band / half-plane / full-instance dropout in the standard path
"""
from __future__ import annotations

import argparse, json, math, random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image
import trimesh

@dataclass
class Asset:
    stl: str
    path: Path
    category_id: int
    points_m: np.ndarray
    extent_m: np.ndarray


def parse_scalar(x: str) -> float:
    x = str(x).strip()
    if "/" in x:
        a,b = x.split("/")
        return float(a)/float(b)
    return float(x)


def parse_pair(s: str, default=(0.45,0.55)) -> Tuple[float,float]:
    if not s:
        return default
    a,b = s.split(",")
    return parse_scalar(a), parse_scalar(b)


def load_json(path: Optional[str]) -> dict:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def infer_stl_to_category(ref_root: Optional[Path]) -> Dict[str,int]:
    out = {}
    if ref_root is None:
        return out
    npz_dir = ref_root / "npz" if (ref_root / "npz").exists() else ref_root
    if not npz_dir.exists():
        return out
    for f in sorted(npz_dir.glob("scene_*.npz"))[:300]:
        try:
            z = np.load(f, allow_pickle=True)
            meta = json.loads(str(z["meta"].item()))
            for inst in meta.get("instances", {}).values():
                stl = Path(str(inst.get("stl", ""))).name
                cid = int(inst.get("category_id", 0))
                if stl and cid > 0:
                    out.setdefault(stl, cid)
        except Exception:
            pass
    return out


def fallback_category(stem: str, idx: int) -> int:
    first = stem.split("_")[0]
    return int(first) if first.isdigit() else idx


def load_assets(stl_dir: Path, ref_root: Optional[Path], unit_scale: float, points_per_asset: int, seed: int) -> List[Asset]:
    ref_map = infer_stl_to_category(ref_root)
    assets = []
    for idx, p in enumerate(sorted(stl_dir.glob("*.stl")), start=1):
        mesh = trimesh.load_mesh(str(p), process=True)
        if not hasattr(mesh, "vertices") or len(mesh.vertices) == 0:
            continue
        pts, _ = trimesh.sample.sample_surface_even(mesh, count=points_per_asset)
        if len(pts) < points_per_asset // 2:
            pts, _ = trimesh.sample.sample_surface(mesh, count=points_per_asset)
        pts = np.asarray(pts, dtype=np.float32) * float(unit_scale)
        mn, mx = pts.min(axis=0), pts.max(axis=0)
        center = (mn + mx) / 2.0
        pts = pts - center
        pts[:,2] -= pts[:,2].min()
        extent = pts.max(axis=0) - pts.min(axis=0)
        cid = ref_map.get(p.name, fallback_category(p.stem, idx))
        assets.append(Asset(p.name, p.resolve(), int(cid), pts.astype(np.float32), extent.astype(np.float32)))
    if not assets:
        raise RuntimeError(f"No STL assets loaded from {stl_dir}")
    return assets


def euler_zyx_to_matrix(z: float, y: float, x: float) -> np.ndarray:
    cz, sz = math.cos(z), math.sin(z); cy, sy = math.cos(y), math.sin(y); cx, sx = math.cos(x), math.sin(x)
    Rz = np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]], np.float32)
    Ry = np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]], np.float32)
    Rx = np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]], np.float32)
    return (Rz @ Ry @ Rx).astype(np.float32)


def quat_wxyz_from_matrix(R: np.ndarray) -> np.ndarray:
    m = R.astype(np.float64); tr = np.trace(m)
    if tr > 0:
        s = math.sqrt(tr+1.0)*2; q = [(0.25*s), (m[2,1]-m[1,2])/s, (m[0,2]-m[2,0])/s, (m[1,0]-m[0,1])/s]
    else:
        i = int(np.argmax(np.diag(m)))
        if i == 0:
            s = math.sqrt(1+m[0,0]-m[1,1]-m[2,2])*2; q=[(m[2,1]-m[1,2])/s,0.25*s,(m[0,1]+m[1,0])/s,(m[0,2]+m[2,0])/s]
        elif i == 1:
            s = math.sqrt(1+m[1,1]-m[0,0]-m[2,2])*2; q=[(m[0,2]-m[2,0])/s,(m[0,1]+m[1,0])/s,0.25*s,(m[1,2]+m[2,1])/s]
        else:
            s = math.sqrt(1+m[2,2]-m[0,0]-m[1,1])*2; q=[(m[1,0]-m[0,1])/s,(m[0,2]+m[2,0])/s,(m[1,2]+m[2,1])/s,0.25*s]
    q = np.asarray(q, np.float64); q /= np.linalg.norm(q)+1e-12
    return q


def crop_box(H:int,W:int, center_crop: str) -> Tuple[int,int,int,int]:
    a,b = parse_pair(center_crop)
    return int(round(H*a)), int(round(W*a)), int(round(H*b)), int(round(W*b))


def splat_points(depth: np.ndarray, inst: np.ndarray, cat: np.ndarray, u: np.ndarray, v: np.ndarray, z: np.ndarray,
                 inst_id: int, cat_id: int, radius: int):
    H,W = depth.shape
    ui0 = np.rint(u).astype(np.int32)
    vi0 = np.rint(v).astype(np.int32)
    offsets = [(0,0)]
    if radius >= 1:
        offsets += [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]
    if radius >= 2:
        offsets += [(-2,0),(2,0),(0,-2),(0,2),(-2,-1),(-2,1),(2,-1),(2,1),(-1,-2),(1,-2),(-1,2),(1,2)]
    flat_depth = depth.ravel(); flat_inst = inst.ravel(); flat_cat = cat.ravel()
    for dx,dy in offsets:
        ui = ui0 + dx; vi = vi0 + dy
        ok = (ui>=0)&(ui<W)&(vi>=0)&(vi<H)&np.isfinite(z)&(z>0.03)
        if not ok.any():
            continue
        flat = (vi[ok]*W + ui[ok]).astype(np.int64)
        zz = z[ok].astype(np.float32)
        order = np.lexsort((zz, flat))
        flat_s = flat[order]; zz_s = zz[order]
        uniq, first = np.unique(flat_s, return_index=True)
        zz_min = zz_s[first]
        current = flat_depth[uniq]
        upd = zz_min < current
        if upd.any():
            idx = uniq[upd]
            flat_depth[idx] = zz_min[upd]
            flat_inst[idx] = inst_id
            flat_cat[idx] = cat_id


def _remove_pixels(depth: np.ndarray, inst: np.ndarray, cat: np.ndarray, rem: np.ndarray):
    depth[rem] = np.nan
    inst[rem] = 0
    cat[rem] = 0


def _sample_target_visible_ratio(rng: np.random.Generator, low: float, high: float, mode: float) -> float:
    low = float(low); high = float(high); mode = float(np.clip(mode, low, high))
    return float(rng.triangular(low, mode, high))


def _soft_dropout(mask: np.ndarray, rng: np.random.Generator, rate: float) -> np.ndarray:
    rate = float(np.clip(rate, 0.0, 0.40))
    return mask & (rng.random(mask.shape) < rate)


def _make_side_removal(mask0: np.ndarray, yy: np.ndarray, xx: np.ndarray, y0: int, x0: int, y1: int, x1: int,
                       side: str, cut_frac: float) -> np.ndarray:
    rem = np.zeros_like(mask0, dtype=bool)
    if side == "left":
        thresh = x0 + int(round((x1 - x0) * cut_frac)); rem |= mask0 & (xx < thresh)
    elif side == "right":
        thresh = x1 - int(round((x1 - x0) * cut_frac)); rem |= mask0 & (xx >= thresh)
    elif side == "top":
        thresh = y0 + int(round((y1 - y0) * cut_frac)); rem |= mask0 & (yy < thresh)
    else:
        thresh = y1 - int(round((y1 - y0) * cut_frac)); rem |= mask0 & (yy >= thresh)
    return rem


def _make_rect_removal(mask0: np.ndarray, yy: np.ndarray, xx: np.ndarray, y0: int, x0: int, y1: int, x1: int,
                       target_area_frac: float, rng: np.random.Generator) -> np.ndarray:
    rem = np.zeros_like(mask0, dtype=bool)
    h = max(1, y1-y0); w = max(1, x1-x0)
    area_frac = float(np.clip(target_area_frac, 0.03, 0.35))
    side_frac = math.sqrt(area_frac)
    rh = int(max(1, round(h * side_frac)))
    rw = int(max(1, round(w * side_frac)))
    cy = int(rng.integers(y0 + rh//2, max(y0 + rh//2 + 1, y1 - rh//2))) if (y1-y0) > rh else (y0+y1)//2
    cx = int(rng.integers(x0 + rw//2, max(x0 + rw//2 + 1, x1 - rw//2))) if (x1-x0) > rw else (x0+x1)//2
    yy0 = max(y0, cy - rh//2); yy1 = min(y1, yy0 + rh)
    xx0 = max(x0, cx - rw//2); xx1 = min(x1, xx0 + rw)
    rem |= mask0 & (yy >= yy0) & (yy < yy1) & (xx >= xx0) & (xx < xx1)
    return rem


def apply_partial_observation(depth: np.ndarray, inst: np.ndarray, cat: np.ndarray, meta: dict, args, rng: np.random.Generator):
    """Always apply soft dropout, then optionally apply one regional corruption.

    Goal: for most partially corrupted instances, final visible ratio should lie around 0.70,
    within a configurable [min,max] range, default [0.60,0.80].
    """
    H, W = depth.shape
    yy, xx = np.mgrid[0:H, 0:W]
    partial_info = {}

    vmin = float(np.clip(args.partial_target_visible_min, 0.40, 0.95))
    vmax = float(np.clip(args.partial_target_visible_max, vmin, 0.98))
    vmode = float(np.clip(args.partial_target_visible_mean, vmin, vmax))
    p_partial = float(np.clip(args.partial_object_prob, 0.0, 1.0))
    p_trunc = float(np.clip(args.truncation_object_prob, 0.0, 1.0))
    soft_rate = float(np.clip(args.soft_pixel_dropout_rate, 0.0, 0.25))

    for iid in sorted([int(x) for x in np.unique(inst) if int(x) > 0]):
        mask0 = inst == iid
        orig_area = int(mask0.sum())
        if orig_area <= 0:
            continue
        ys, xs = np.where(mask0)
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        x0, x1 = int(xs.min()), int(xs.max()) + 1

        # always-on soft dropout for sensor-like depth holes
        rem = _soft_dropout(mask0, rng, soft_rate)
        modes = ["soft_pixel_dropout"] if rem.any() else []
        current_visible = int((mask0 & (~rem)).sum()) / max(1, orig_area)

        # Sample a target visible ratio. Regional corruption is only used to move the visible
        # ratio further down toward the target window.
        target_visible = _sample_target_visible_ratio(rng, vmin, vmax, vmode)

        # Decide whether to apply one regional corruption.
        regional_applied = False
        if float(rng.random()) < p_partial and current_visible > target_visible:
            desired_remove_frac = max(0.0, current_visible - target_visible)
            desired_remove_frac = min(desired_remove_frac, 0.35)
            # Try a few candidate regional corruptions and keep one whose final ratio is closest to target.
            candidates = []
            for _ in range(6):
                if float(rng.random()) < p_trunc:
                    side = str(rng.choice(["left", "right", "top", "bottom"]))
                    cut_frac = float(np.clip(desired_remove_frac * rng.uniform(0.9, 1.3), 0.03, 0.45))
                    reg = _make_side_removal(mask0, yy, xx, y0, x0, y1, x1, side, cut_frac)
                    mode = f"mild_side_trunc_{side}"
                else:
                    area_frac = float(np.clip(desired_remove_frac * rng.uniform(0.9, 1.4), 0.03, 0.30))
                    reg = _make_rect_removal(mask0, yy, xx, y0, x0, y1, x1, area_frac, rng)
                    mode = "mild_rect"
                combined = rem | reg
                remain_ratio = float((mask0 & (~combined)).sum() / max(1, orig_area))
                candidates.append((abs(remain_ratio - target_visible), remain_ratio, combined, mode))
            candidates.sort(key=lambda x: x[0])
            # prefer candidates inside [vmin, vmax], else use the closest one
            chosen = None
            for cand in candidates:
                if vmin <= cand[1] <= vmax:
                    chosen = cand
                    break
            if chosen is None:
                chosen = candidates[0]
            _, final_ratio_pred, combined_rem, mode = chosen
            rem = combined_rem
            modes.append(mode)
            regional_applied = True
            current_visible = final_ratio_pred

        # Safety clamp: if still below vmin, back off to soft-dropout only.
        final_area = int((mask0 & (~rem)).sum())
        final_ratio = float(final_area / max(1, orig_area))
        if final_ratio < vmin:
            rem = _soft_dropout(mask0, rng, soft_rate)
            modes = ["soft_pixel_dropout"] if rem.any() else []
            final_area = int((mask0 & (~rem)).sum())
            final_ratio = float(final_area / max(1, orig_area))
            regional_applied = False

        if rem.any():
            _remove_pixels(depth, inst, cat, rem)
        final_area = int((inst == iid).sum())
        final_ratio = float(final_area / max(1, orig_area))

        info = {
            "original_pixel_count": orig_area,
            "visible_pixel_count_after_partial": final_area,
            "visible_ratio_after_partial": final_ratio,
            "partial_modes": modes,
            "target_visible_ratio": float(target_visible),
            "regional_applied": bool(regional_applied),
        }
        partial_info[str(iid)] = info
        if str(iid) in meta.get("instances", {}):
            meta["instances"][str(iid)].update(info)

    meta["partial_observation"] = {
        "enabled": True,
        "policy": "soft_always_plus_targeted_partial_v3",
        "kept_modes": ["mild_side_trunc", "mild_rect", "soft_pixel_dropout_always"],
        "soft_pixel_dropout_always": True,
        "partial_object_prob": p_partial,
        "truncation_object_prob": p_trunc,
        "soft_pixel_dropout_rate": soft_rate,
        "target_visible_min": vmin,
        "target_visible_max": vmax,
        "target_visible_mean": vmode,
        "note": "Soft pixel dropout is always applied. One additional regional corruption may be applied to place most visible ratios around the target range.",
        "per_instance": partial_info,
    }
    return meta


def generate_scene(scene_i:int, assets:List[Asset], args, rng:np.random.Generator):
    H,W=args.height,args.width; fx=args.fx; fy=args.fy; cx=args.cx; cy=args.cy
    y0,x0,y1,x1 = crop_box(H,W,args.center_crop)
    depth = np.full((H,W), np.inf, dtype=np.float32)
    inst = np.zeros((H,W), dtype=np.int32); cat = np.zeros((H,W), dtype=np.int32)
    n = int(rng.integers(args.min_objects,args.max_objects+1))
    chosen = list(rng.choice(assets,size=n,replace=True))
    meta_instances = {}
    for iid, asset in enumerate(chosen, start=1):
        yaw = float(rng.uniform(-math.pi, math.pi))
        pitch = float(rng.normal(0, math.radians(args.tilt_sigma_deg)))
        roll = float(rng.normal(0, math.radians(args.tilt_sigma_deg)))
        R = euler_zyx_to_matrix(yaw,pitch,roll)
        pts = asset.points_m @ R.T
        pts[:,2] -= pts[:,2].max()
        D = float(rng.uniform(args.depth_min,args.depth_max))
        uu = float(rng.uniform(x0+args.margin_px, x1-args.margin_px))
        vv = float(rng.uniform(y0+args.margin_px, y1-args.margin_px))
        X = (uu-cx)*D/fx; Y = (vv-cy)*D/fy
        Xc = pts[:,0] + X; Yc = pts[:,1] + Y; Zc = D - pts[:,2]
        u = fx*(Xc/Zc)+cx; v = fy*(Yc/Zc)+cy
        splat_points(depth, inst, cat, u, v, Zc, iid, asset.category_id, args.splat_radius)
        meta_instances[iid] = {
            "category_id": int(asset.category_id), "stl": asset.stl,
            "quat_wxyz": quat_wxyz_from_matrix(R).tolist(),
            "euler_zyx_deg": [math.degrees(yaw), math.degrees(pitch), math.degrees(roll)],
        }
    depth[~np.isfinite(depth)] = np.nan
    yy0,xx0,yy1,xx1=crop_box(H,W,args.center_crop)
    vals=depth[yy0:yy1,xx0:xx1]; vals=vals[np.isfinite(vals)]
    if vals.size:
        target = float(rng.uniform(args.depth_min,args.depth_max)); shift=target-float(np.median(vals)); depth[np.isfinite(depth)] += shift
    meta = {
        "scene_idx": scene_i, "bg_kind":"rescene_B_fast_splat", "resolution":[H,W],
        "n_parts_dropped": n, "visible_inst_ids": [],
        "instances": {str(k):v for k,v in meta_instances.items()},
        "conventions":{"quat":"wxyz","euler":"ZYX intrinsic degrees","depth_unit":"meter","renderer":"fast_point_splat_zbuffer"},
        "camera":{"fx":fx,"fy":fy,"cx":cx,"cy":cy}, "center_crop":args.center_crop,
    }
    meta = apply_partial_observation(depth, inst, cat, meta, args, rng)
    return depth,inst,cat,meta


def write_crops(scene_i:int, depth, inst, cat, meta_instances, crop_dir:Path):
    visible=[]
    for iid in sorted(np.unique(inst)):
        iid=int(iid)
        if iid<=0: continue
        mask=inst==iid
        if mask.sum()<args_min_area_global: continue
        ys,xs=np.where(mask); y0,y1=int(ys.min()),int(ys.max())+1; x0,x1=int(xs.min()),int(xs.max())+1
        d=depth[y0:y1,x0:x1].copy(); m=mask[y0:y1,x0:x1].astype(bool); d[~m]=np.nan
        info=meta_instances[str(iid)] if str(iid) in meta_instances else meta_instances[iid]
        cid=int(info["category_id"])
        np.savez_compressed(crop_dir/f"scene{scene_i:05d}_inst{iid:02d}_cat{cid:02d}.npz",
            depth=d.astype(np.float32), mask=m, label=np.array(cid,np.int32),
            quat_wxyz=np.asarray(info["quat_wxyz"],np.float64), euler_zyx_deg=np.asarray(info["euler_zyx_deg"],np.float64),
            bbox_yxyx=np.asarray([y0,x0,y1,x1],np.int32), stl=np.array(info["stl"]))
        visible.append(iid)
    return visible


def save_vis(depth, inst, cat, path:Path):
    H,W=depth.shape; valid=np.isfinite(depth); img=np.zeros((H,W,3),np.uint8)
    if valid.any():
        vals=depth[valid]; p1,p99=np.percentile(vals,[1,99]); norm=np.zeros((H,W),np.float32); norm[valid]=1-np.clip((depth[valid]-p1)/(p99-p1+1e-8),0,1)
        gray=(norm*255).astype(np.uint8); img[:]=gray[...,None]
        rng=np.random.default_rng(12345); colors=rng.integers(50,255,size=(max(int(cat.max())+1,2),3),dtype=np.uint8); colors[0]=0
        m=cat>0; overlay=colors[np.clip(cat,0,len(colors)-1)]; img[m]=(0.45*img[m]+0.55*overlay[m]).astype(np.uint8)
    Image.fromarray(img).save(path)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--stl_dir",required=True); p.add_argument("--out_root",required=True); p.add_argument("--ref_dataset",default=None); p.add_argument("--request_json",default=None)
    p.add_argument("--num_scenes",type=int,default=20); p.add_argument("--seed",type=int,default=42)
    p.add_argument("--width",type=int,default=848); p.add_argument("--height",type=int,default=480); p.add_argument("--fx",type=float,default=600.0); p.add_argument("--fy",type=float,default=600.0); p.add_argument("--cx",type=float,default=None); p.add_argument("--cy",type=float,default=None)
    p.add_argument("--stl_unit_scale",type=float,default=0.001); p.add_argument("--points_per_asset",type=int,default=20000); p.add_argument("--splat_radius",type=int,default=1)
    p.add_argument("--center_crop",default="1/6,5/6"); p.add_argument("--depth_median_range",default="0.45,0.55"); p.add_argument("--valid_ratio_range",default="0.04,0.08")
    p.add_argument("--min_objects",type=int,default=8); p.add_argument("--max_objects",type=int,default=9); p.add_argument("--tilt_sigma_deg",type=float,default=7.0); p.add_argument("--margin_px",type=int,default=30); p.add_argument("--min_area",type=int,default=30)
    p.add_argument("--partial_object_prob", type=float, default=1.0, help="Probability of applying one additional regional corruption per object")
    p.add_argument("--truncation_object_prob", type=float, default=0.50, help="Among regional corruptions, probability of choosing a mild side truncation instead of a small rectangular missing region")
    p.add_argument("--soft_pixel_dropout_rate", type=float, default=0.04, help="Always-on sparse depth-hole rate for each visible object")
    p.add_argument("--partial_target_visible_min", type=float, default=0.85, help="Lower bound of desired visible ratio after partial corruption")
    p.add_argument("--partial_target_visible_max", type=float, default=0.95, help="Upper bound of desired visible ratio after partial corruption")
    p.add_argument("--partial_target_visible_mean", type=float, default=0.90, help="Center of the desired visible-ratio distribution")
    args=p.parse_args(); globals()['args_min_area_global']=args.min_area

    req=load_json(args.request_json); cam=req.get("camera",{}) if isinstance(req,dict) else {}; scene_cfg=req.get("scene",{}) if isinstance(req,dict) else {}
    if "render_resolution_hw" in cam: args.height,args.width=int(cam["render_resolution_hw"][0]),int(cam["render_resolution_hw"][1])
    if "train_center_crop" in cam: args.center_crop=cam["train_center_crop"]
    if "working_distance_m_main" in cam: args.depth_median_range=f"{cam['working_distance_m_main'][0]},{cam['working_distance_m_main'][1]}"
    if "visible_object_count_target" in scene_cfg: args.min_objects,args.max_objects=int(scene_cfg["visible_object_count_target"][0]),int(scene_cfg["visible_object_count_target"][1])
    if "target_valid_ratio_after_crop" in scene_cfg: args.valid_ratio_range=f"{scene_cfg['target_valid_ratio_after_crop'][0]},{scene_cfg['target_valid_ratio_after_crop'][1]}"

    if args.cx is None: args.cx=args.width/2
    if args.cy is None: args.cy=args.height/2
    args.depth_min,args.depth_max=parse_pair(args.depth_median_range); vr_min,vr_max=parse_pair(args.valid_ratio_range)
    out=Path(args.out_root); npz_dir=out/"npz"; crop_dir=out/"crops"; vis_dir=out/"vis"
    for d in [npz_dir,crop_dir,vis_dir]: d.mkdir(parents=True, exist_ok=True)
    assets=load_assets(Path(args.stl_dir), Path(args.ref_dataset) if args.ref_dataset else None, args.stl_unit_scale,args.points_per_asset,args.seed)
    print(f"Loaded {len(assets)} assets. HxW={args.height}x{args.width}, center_crop={args.center_crop}")
    print(f"Partial policy: soft_always, target_visible=[{args.partial_target_visible_min:.2f},{args.partial_target_visible_max:.2f}] mean={args.partial_target_visible_mean:.2f}")
    rng=np.random.default_rng(args.seed); rows=[]; all_visible_ratios=[]
    for si in range(args.num_scenes):
        depth,inst,cat,meta=generate_scene(si,assets,args,rng)
        visible=write_crops(si,depth,inst,cat,meta["instances"],crop_dir); meta["visible_inst_ids"]=visible
        if not visible: raise RuntimeError(f"empty generated scene {si}")
        np.savez_compressed(npz_dir/f"scene_{si:05d}.npz", depth=depth.astype(np.float32), inst_id=inst.astype(np.int32), category_id=cat.astype(np.int32), meta=np.array(json.dumps(meta)))
        save_vis(depth,inst,cat,vis_dir/f"scene_{si:05d}.png")
        y0,x0,y1,x1=crop_box(args.height,args.width,args.center_crop); c=depth[y0:y1,x0:x1]; valid=np.isfinite(c); med=float(np.median(c[valid])) if valid.any() else float('nan'); vr=float(valid.mean())
        rows.append((si,vr,med,len(visible)))
        for inst_info in meta.get("instances", {}).values():
            rr = inst_info.get("visible_ratio_after_partial")
            if rr is not None:
                all_visible_ratios.append(float(rr))
        if (si+1)%max(1,min(10,args.num_scenes))==0: print(f"[{si+1}/{args.num_scenes}] vr={vr:.4f} med={med:.4f} visible={len(visible)}")
    prof=out/"profile_check"; prof.mkdir(exist_ok=True)
    vis_stats = {
        "count": int(len(all_visible_ratios)),
        "min": float(np.min(all_visible_ratios)) if all_visible_ratios else None,
        "mean": float(np.mean(all_visible_ratios)) if all_visible_ratios else None,
        "p10": float(np.percentile(all_visible_ratios, 10)) if all_visible_ratios else None,
        "p50": float(np.percentile(all_visible_ratios, 50)) if all_visible_ratios else None,
        "p90": float(np.percentile(all_visible_ratios, 90)) if all_visible_ratios else None,
        "max": float(np.max(all_visible_ratios)) if all_visible_ratios else None,
    }
    summary={"num_scenes":args.num_scenes,"render_resolution_hw":[args.height,args.width],"center_crop":args.center_crop,"valid_ratio_crop_mean":float(np.mean([r[1] for r in rows])) if rows else None,"valid_ratio_crop_min":float(np.min([r[1] for r in rows])) if rows else None,"valid_ratio_crop_max":float(np.max([r[1] for r in rows])) if rows else None,"depth_median_crop_mean":float(np.mean([r[2] for r in rows])) if rows else None,"visible_count_mean":float(np.mean([r[3] for r in rows])) if rows else None,"renderer":"fast_point_splat_zbuffer","partial_observation":{"policy":"soft_always_plus_targeted_partial_v3","partial_object_prob":args.partial_object_prob,"truncation_object_prob":args.truncation_object_prob,"soft_pixel_dropout_always":True,"soft_pixel_dropout_rate":args.soft_pixel_dropout_rate,"partial_target_visible_min":args.partial_target_visible_min,"partial_target_visible_max":args.partial_target_visible_max,"partial_target_visible_mean":args.partial_target_visible_mean,"visible_ratio_stats":vis_stats}}
    (prof/"B_dataset_profile_summary.json").write_text(json.dumps(summary,indent=2))
    (prof/"B_dataset_visible_ratio_stats.json").write_text(json.dumps(vis_stats, indent=2))
    with (prof/"B_dataset_profile_per_scene.csv").open('w') as f:
        f.write('scene_idx,valid_ratio_crop,depth_median_crop,visible_count\n')
        for r in rows: f.write(f"{r[0]},{r[1]:.8f},{r[2]:.8f},{r[3]}\n")
    imgs=[Image.open(f).convert('RGB') for f in sorted(vis_dir.glob('scene_*.png'))[:4]]
    if imgs:
        cw,ch=imgs[0].size; canvas=Image.new('RGB',(cw*2,ch*2),(0,0,0))
        for i,im in enumerate(imgs): canvas.paste(im,((i%2)*cw,(i//2)*ch))
        canvas.save(prof/"B_dataset_preview_2x2.png")
    split=out/"splits"; split.mkdir(exist_ok=True); idx=list(range(args.num_scenes)); random.Random(args.seed).shuffle(idx); nt=int(round(args.num_scenes*.8)); nv=int(round(args.num_scenes*.1)); scene_items=[{"scene_id": f"scene_{i:05d}", "scene_npz": str((npz_dir/f"scene_{i:05d}.npz").resolve())} for i in range(args.num_scenes)]
    for name,ids in {'train':idx[:nt],'val':idx[nt:nt+nv],'test':idx[nt+nv:]}.items(): (split/f"{name}.json").write_text(json.dumps({'scenes':[scene_items[i] for i in ids],'data_root':str(out.resolve()),'split':name},indent=2))
    (out/"B_fast_generation_summary.json").write_text(json.dumps(summary,indent=2))
    print('DONE'); print(json.dumps(summary,indent=2))

if __name__=='__main__':
    main()
