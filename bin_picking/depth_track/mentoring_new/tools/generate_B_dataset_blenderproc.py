import blenderproc as bproc

"""
Generate B pseudo dataset with BlenderProc.

This script creates a new CAD-rendered pseudo dataset that matches the real-depth
acquisition profile and writes the same output format as the existing synthetic
2D dataset.

IMPORTANT: BlenderProc requires `import blenderproc as bproc` to be the first
statement in this file. Do not move it below this docstring.
"""

import argparse
import json
import math
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

_DEPTH_OUTPUT_ENABLED = False
_CURRENT_CAMERA_POSE = None


# ----------------------------- helpers -----------------------------

def parse_fraction_pair(s: str) -> Tuple[float, float]:
    if isinstance(s, (list, tuple)) and len(s) == 2:
        return float(s[0]), float(s[1])
    parts = str(s).split(",")
    if len(parts) != 2:
        raise ValueError(f"Expected pair like '1/6,5/6', got {s}")
    vals = []
    for p in parts:
        p = p.strip()
        if "/" in p:
            a, b = p.split("/", 1)
            vals.append(float(a) / float(b))
        else:
            vals.append(float(p))
    return vals[0], vals[1]


def center_crop_bbox_hw(height: int, width: int, keep: str) -> Tuple[int, int, int, int]:
    lo, hi = parse_fraction_pair(keep)
    y0 = int(round(height * lo))
    y1 = int(round(height * hi))
    x0 = int(round(width * lo))
    x1 = int(round(width * hi))
    return y0, x0, y1, x1


def canonical_stem(name: str) -> str:
    stem = Path(str(name)).stem
    stem = re.sub(r"__[0-9a-fA-F]{6,}$", "", stem)
    return stem


def read_json(path: Optional[Path], default: Any = None) -> Any:
    if path is None or not path.exists():
        return default
    return json.loads(path.read_text())


def ensure_dirs(root: Path) -> None:
    for d in ["npz", "crops", "vis", "profile_check"]:
        (root / d).mkdir(parents=True, exist_ok=True)


def look_at_rotation(camera_location: np.ndarray, target: np.ndarray) -> Euler:
    """Camera looks along its local -Z axis toward target."""
    direction = Vector((target - camera_location).tolist())
    quat = direction.to_track_quat('-Z', 'Y')
    return quat.to_euler()


def import_stl_raw(filepath: Path) -> bpy.types.Object:
    """Import an STL and return the newly created Blender object."""
    before = set(bpy.data.objects)
    try:
        bpy.ops.import_mesh.stl(filepath=str(filepath))
    except Exception:
        # Blender 4.x may use wm.stl_import
        bpy.ops.wm.stl_import(filepath=str(filepath))
    after = set(bpy.data.objects)
    new_objs = list(after - before)
    if not new_objs:
        raise RuntimeError(f"Failed to import STL: {filepath}")
    # Join multiple imported meshes if necessary.
    if len(new_objs) > 1:
        bpy.ops.object.select_all(action='DESELECT')
        for o in new_objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = new_objs[0]
        bpy.ops.object.join()
        obj = bpy.context.view_layer.objects.active
    else:
        obj = new_objs[0]
    obj.name = filepath.stem
    return obj


def center_mesh_geometry(obj: bpy.types.Object) -> None:
    """Move mesh vertices so local bbox center becomes object origin."""
    bpy.context.view_layer.update()
    if not hasattr(obj.data, "vertices"):
        return
    coords = np.array([v.co[:] for v in obj.data.vertices], dtype=np.float32)
    if coords.size == 0:
        return
    center = coords.mean(axis=0)
    # More stable for asymmetric assembly-coordinate STLs: bbox center.
    mn = coords.min(axis=0)
    mx = coords.max(axis=0)
    center = (mn + mx) * 0.5
    for v in obj.data.vertices:
        v.co.x -= float(center[0])
        v.co.y -= float(center[1])
        v.co.z -= float(center[2])
    obj.location += Vector(center.tolist())
    obj.location = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()


def bbox_world_xy_extent(obj: bpy.types.Object) -> Tuple[float, float, float]:
    bpy.context.view_layer.update()
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    return max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)


def set_origin_on_floor(obj: bpy.types.Object) -> None:
    bpy.context.view_layer.update()
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    min_z = min(c.z for c in corners)
    obj.location.z -= min_z


def create_material(name: str, color: Tuple[float, float, float, float]) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        try:
            bsdf.inputs["Base Color"].default_value = color
            bsdf.inputs["Roughness"].default_value = 0.7
        except Exception:
            pass
    return mat


def assign_gray_material(obj: bpy.types.Object, mat: bpy.types.Material) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def ensure_camera_object() -> bpy.types.Object:
    """Create and register a Blender camera before any BlenderProc camera utility call."""
    cam = bpy.context.scene.camera
    if cam is None or cam.name not in bpy.data.objects:
        cam_data = bpy.data.cameras.new("Camera")
        cam = bpy.data.objects.new("Camera", cam_data)
        bpy.context.collection.objects.link(cam)
        bpy.context.scene.camera = cam
    cam.data.type = 'PERSP'
    bpy.context.view_layer.update()
    return cam


def setup_camera(width: int, height: int, fx: Optional[float], fy: Optional[float], cx: Optional[float], cy: Optional[float], hfov_deg: float) -> None:
    # BlenderProc 2.x/Blender 4.x expects scene.camera to exist before
    # bproc.camera.set_resolution(), otherwise CameraUtility tries to access
    # None.data and crashes.
    cam = ensure_camera_object()
    bproc.camera.set_resolution(width, height)
    if fx is not None and fy is not None:
        if cx is None:
            cx = width / 2.0
        if cy is None:
            cy = height / 2.0
        K = np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float32)
        bproc.camera.set_intrinsics_from_K_matrix(K, width, height)
    else:
        # Set focal length through FOV. BlenderProc supports camera pose regardless of this.
        cam.data.sensor_fit = 'HORIZONTAL'
        cam.data.angle_x = math.radians(hfov_deg)
        # angle_y is inferred from sensor fit/aspect.


def set_camera_pose_top_down(height_m: float, xy_jitter: float, tilt_deg: float, rng: random.Random) -> None:
    """Set the Blender camera transform and cache a cam2world matrix.

    Important: we do NOT register the pose with BlenderProc here.
    `force_single_frame_for_rendering()` clears animation data just before rendering,
    and that can erase the pose BlenderProc registered via keyframes.  The pose is
    registered immediately before `bproc.renderer.render()` inside
    `register_current_camera_pose_for_rendering()`.
    """
    global _CURRENT_CAMERA_POSE
    cam = ensure_camera_object()
    loc = np.array([
        rng.uniform(-xy_jitter, xy_jitter),
        rng.uniform(-xy_jitter, xy_jitter),
        height_m,
    ], dtype=np.float32)
    target = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    rot = look_at_rotation(loc, target)
    # Add small roll/pitch/yaw perturbation around camera orientation.
    tilt = math.radians(tilt_deg)
    perturb = Euler((rng.uniform(-tilt, tilt), rng.uniform(-tilt, tilt), rng.uniform(-tilt, tilt)), 'XYZ')
    cam.location = Vector(loc.tolist())
    cam.rotation_euler = rot
    cam.rotation_euler.rotate(perturb)
    bpy.context.view_layer.update()
    _CURRENT_CAMERA_POSE = np.array(cam.matrix_world, dtype=np.float32)


def register_current_camera_pose_for_rendering() -> None:
    """Register exactly one camera pose right before rendering.

    BlenderProc raises "No camera poses have been registered" if the pose is
    added before later keyframe/animation cleanup.  Registering after
    `force_single_frame_for_rendering()` fixes that.  We try `frame=0` first so
    repeated scene attempts overwrite/use a single frame in recent BlenderProc
    versions; older versions fall back to the positional-only API.
    """
    if _CURRENT_CAMERA_POSE is None:
        raise RuntimeError("Camera pose was not set before rendering")
    try:
        bproc.camera.add_camera_pose(_CURRENT_CAMERA_POSE, frame=0)
    except TypeError:
        bproc.camera.add_camera_pose(_CURRENT_CAMERA_POSE)


def blender_quat_wxyz(obj: bpy.types.Object) -> List[float]:
    q = obj.rotation_euler.to_quaternion()
    return [float(q.w), float(q.x), float(q.y), float(q.z)]


def blender_euler_zyx_deg(obj: bpy.types.Object) -> List[float]:
    e = obj.rotation_euler
    # Store in ZYX order to match existing dataset convention.
    return [float(math.degrees(e.z)), float(math.degrees(e.y)), float(math.degrees(e.x))]


def object_center_from_camera_depth(depth: np.ndarray, inst: np.ndarray, crop: Tuple[int, int, int, int]) -> float:
    y0, x0, y1, x1 = crop
    valid = np.isfinite(depth[y0:y1, x0:x1]) & (inst[y0:y1, x0:x1] > 0)
    if valid.sum() == 0:
        return float("nan")
    return float(np.nanmedian(depth[y0:y1, x0:x1][valid]))


def ensure_default_segmentation_attributes() -> None:
    """BlenderProc segmap requires requested custom attributes on every renderable ID.

    Some versions include the World/background in the segmentation attribute pass.
    Give all non-CAD objects and the World a category_id=0 so they become background
    instead of raising "World does not have category_id".
    """
    for obj in bpy.data.objects:
        if "category_id" not in obj:
            obj["category_id"] = 0
    for world in bpy.data.worlds:
        try:
            if "category_id" not in world:
                world["category_id"] = 0
        except Exception:
            pass


def enable_depth_output_once() -> None:
    """BlenderProc cannot enable depth output twice in one process."""
    global _DEPTH_OUTPUT_ENABLED
    if not _DEPTH_OUTPUT_ENABLED:
        bproc.renderer.enable_depth_output(activate_antialiasing=False)
        _DEPTH_OUTPUT_ENABLED = True


def force_single_frame_for_rendering() -> None:
    """Keep physics simulation from making render() output all physics frames."""
    # If rigid-body simulation or frame iteration set a long timeline, BlenderProc may
    # render all frames. Freeze current transforms and reset the render range to one frame.
    # Do not preserve/add camera keyframes here; the camera pose is registered separately
    # immediately before render().
    bpy.context.view_layer.update()
    for obj in bpy.data.objects:
        try:
            mat = obj.matrix_world.copy()
            obj.animation_data_clear()
            obj.matrix_world = mat
        except Exception:
            pass
    bpy.context.scene.frame_start = 0
    bpy.context.scene.frame_end = 0
    bpy.context.scene.frame_set(0)
    bpy.context.view_layer.update()


def render_depth_and_seg() -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[dict]]:
    ensure_default_segmentation_attributes()
    force_single_frame_for_rendering()
    register_current_camera_pose_for_rendering()
    enable_depth_output_once()

    render_data = bproc.renderer.render()
    depth = render_data.get("depth")
    if depth is None:
        raise RuntimeError("BlenderProc render() did not return depth. Check renderer setup.")
    depth = np.asarray(depth[0], dtype=np.float32)

    # default_values prevents background/World from crashing category_id lookup.
    try:
        seg_data = bproc.renderer.render_segmap(
            map_by=["instance", "category_id", "name"],
            default_values={"category_id": 0},
        )
    except TypeError:
        # Older BlenderProc versions may not expose default_values; in that case,
        # the explicit category_id=0 properties above usually suffice.
        seg_data = bproc.renderer.render_segmap(map_by=["instance", "category_id", "name"])

    # BlenderProc key names differ by version; handle common cases.
    inst = None
    cat = None
    attrs = []
    for k in ["instance_segmaps", "instance"]:
        if k in seg_data:
            inst = np.asarray(seg_data[k][0], dtype=np.int32)
            break
    for k in ["category_id_segmaps", "category_id"]:
        if k in seg_data:
            cat = np.asarray(seg_data[k][0], dtype=np.int32)
            break
    for k in ["instance_attribute_maps", "instance_attributes"]:
        if k in seg_data:
            attrs = seg_data[k][0]
            break
    if inst is None:
        raise RuntimeError(f"Could not find instance segmentation in seg_data keys={list(seg_data.keys())}")
    if cat is None:
        cat = np.zeros_like(inst, dtype=np.int32)
    return depth, inst, cat, attrs

def remap_visible_instances(depth: np.ndarray, inst: np.ndarray, cat: np.ndarray, name_to_asset: Dict[str, dict], min_pixels: int) -> Tuple[np.ndarray, np.ndarray, Dict[str, dict], List[int]]:
    obj_mask = inst > 0
    # Remove plane or non-CAD objects: keep only pixels whose category_id > 0.
    obj_mask &= cat > 0
    new_inst = np.zeros_like(inst, dtype=np.int32)
    new_cat = np.zeros_like(cat, dtype=np.int32)
    meta_instances: Dict[str, dict] = {}
    visible_ids: List[int] = []
    next_id = 1
    for old_id in sorted(np.unique(inst[obj_mask]).tolist()):
        m = (inst == old_id) & obj_mask
        if int(m.sum()) < min_pixels:
            continue
        cats, counts = np.unique(cat[m], return_counts=True)
        cid = int(cats[np.argmax(counts)])
        new_inst[m] = next_id
        new_cat[m] = cid
        visible_ids.append(next_id)
        meta_instances[str(next_id)] = {"category_id": cid}
        next_id += 1
    return new_inst, new_cat, meta_instances, visible_ids


def save_scene_and_crops(
    out_root: Path,
    scene_idx: int,
    depth: np.ndarray,
    inst_id: np.ndarray,
    category_id: np.ndarray,
    meta_instances: Dict[str, dict],
    object_by_category: Dict[int, bpy.types.Object],
    asset_by_category: Dict[int, dict],
    bg_kind: str,
    center_crop: str,
) -> Dict[str, Any]:
    H, W = depth.shape
    object_pixels = inst_id > 0
    depth_out = depth.astype(np.float32).copy()
    depth_out[~object_pixels] = np.nan

    visible_inst_ids = sorted([int(x) for x in np.unique(inst_id) if x > 0])
    full_meta_instances: Dict[str, dict] = {}
    for iid in visible_inst_ids:
        mask = inst_id == iid
        cats, counts = np.unique(category_id[mask], return_counts=True)
        cid = int(cats[np.argmax(counts)])
        asset = asset_by_category.get(cid, {})
        obj = object_by_category.get(cid)
        ys, xs = np.where(mask)
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        if obj is not None:
            quat = blender_quat_wxyz(obj)
            euler = blender_euler_zyx_deg(obj)
        else:
            quat = [1.0, 0.0, 0.0, 0.0]
            euler = [0.0, 0.0, 0.0]
        stl = asset.get("stl", f"category_{cid:02d}.stl")
        full_meta_instances[str(iid)] = {
            "category_id": cid,
            "stl": stl,
            "quat_wxyz": quat,
            "euler_zyx_deg": euler,
            "bbox_yxyx": [y0, x0, y1, x1],
        }
        crop_depth = depth_out[y0:y1, x0:x1]
        crop_mask = mask[y0:y1, x0:x1]
        crop_path = out_root / "crops" / f"scene{scene_idx:05d}_inst{iid:02d}_cat{cid:02d}.npz"
        np.savez_compressed(
            crop_path,
            depth=crop_depth.astype(np.float32),
            mask=crop_mask.astype(bool),
            label=np.array(cid, dtype=np.int32),
            quat_wxyz=np.asarray(quat, dtype=np.float64),
            euler_zyx_deg=np.asarray(euler, dtype=np.float64),
            bbox_yxyx=np.asarray([y0, x0, y1, x1], dtype=np.int32),
            stl=np.array(stl),
        )

    meta = {
        "scene_idx": scene_idx,
        "bg_kind": bg_kind,
        "resolution": [H, W],
        "center_crop": center_crop,
        "n_parts_dropped": len(object_by_category),
        "visible_inst_ids": visible_inst_ids,
        "instances": full_meta_instances,
        "convention": {
            "depth_unit": "meter",
            "background_depth": "NaN",
            "quat": "wxyz",
            "euler": "ZYX intrinsic degrees",
            "pose_meaning": "STL canonical to current rendered pose, approximate if no physics is used",
        },
        "generator": "B BlenderProc generator",
    }
    scene_path = out_root / "npz" / f"scene_{scene_idx:05d}.npz"
    np.savez_compressed(
        scene_path,
        depth=depth_out.astype(np.float32),
        inst_id=inst_id.astype(np.int32),
        category_id=category_id.astype(np.int32),
        meta=json.dumps(meta, ensure_ascii=False),
    )

    # Save visual depth preview: nearer brighter, background black.
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        valid = np.isfinite(depth_out)
        disp = np.zeros_like(depth_out, dtype=np.float32)
        if valid.any():
            p1, p99 = np.percentile(depth_out[valid], [1, 99])
            vals = (depth_out[valid] - p1) / (p99 - p1 + 1e-8)
            disp[valid] = 1.0 - np.clip(vals, 0.0, 1.0)
        plt.imsave(out_root / "vis" / f"scene_{scene_idx:05d}.png", disp, cmap="gray", vmin=0, vmax=1)
    except Exception:
        pass

    y0, x0, y1, x1 = center_crop_bbox_hw(H, W, center_crop)
    crop_valid = np.isfinite(depth_out[y0:y1, x0:x1])
    return {
        "scene_idx": scene_idx,
        "visible_count": len(visible_inst_ids),
        "valid_ratio_full": float(np.isfinite(depth_out).mean()),
        "valid_ratio_crop": float(crop_valid.mean()),
        "depth_median_crop": float(np.nanmedian(depth_out[y0:y1, x0:x1])) if crop_valid.any() else None,
    }


def clear_scene() -> None:
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def setup_world(bg_kind: str, table_size: float = 1.2) -> bpy.types.Object:
    bpy.ops.mesh.primitive_plane_add(size=table_size, location=(0, 0, 0))
    plane = bpy.context.object
    plane.name = "background_plane"
    plane["category_id"] = 0
    mat_color = (0.85, 0.85, 0.85, 1.0) if bg_kind == "white_desk" else (0.65, 0.75, 0.80, 1.0)
    mat = create_material(f"mat_{bg_kind}", mat_color)
    plane.data.materials.append(mat)
    return plane


def add_basic_lights() -> None:
    bpy.ops.object.light_add(type='AREA', location=(0, 0, 1.2))
    light = bpy.context.object
    light.name = "top_area_light"
    light.data.energy = 350
    light.data.size = 3.0


def add_rigidbody(obj: bpy.types.Object, kind: str, mass: float = 0.02) -> None:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.rigidbody.object_add(type=kind)
    obj.rigid_body.collision_shape = 'CONVEX_HULL' if kind == 'ACTIVE' else 'BOX'
    obj.rigid_body.friction = 0.8
    obj.rigid_body.restitution = 0.05
    if kind == 'ACTIVE':
        obj.rigid_body.mass = mass
    obj.select_set(False)


def run_physics(frames: int = 90) -> None:
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = max(1, frames)
    for f in range(1, frames + 1):
        bpy.context.scene.frame_set(f)
        bpy.context.view_layer.update()
    # Freeze final transforms and collapse the timeline to a single frame for rendering.
    bpy.context.view_layer.update()
    final_mats = {obj.name: obj.matrix_world.copy() for obj in bpy.data.objects}
    for obj in bpy.data.objects:
        try:
            obj.animation_data_clear()
            obj.matrix_world = final_mats[obj.name]
        except Exception:
            pass
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 1
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()


@dataclass
class Asset:
    stl: str
    path: Path
    category_id: int
    class_name: str


def load_assets(manifest_path: Path) -> List[Asset]:
    manifest = json.loads(manifest_path.read_text())
    assets = []
    for a in manifest.get("assets", []):
        p = Path(a["path"])
        if not p.exists():
            raise FileNotFoundError(f"Asset path does not exist: {p}")
        assets.append(Asset(stl=a.get("stl", p.name), path=p, category_id=int(a["category_id"]), class_name=a.get("class_name", canonical_stem(p.name))))
    if not assets:
        raise RuntimeError(f"No assets in manifest: {manifest_path}")
    return assets


def request_defaults(request: Dict[str, Any]) -> Dict[str, Any]:
    cam = request.get("camera", {})
    scene = request.get("scene", {})
    depth_out = request.get("depth_output", {})
    sensor = depth_out.get("sensorization_for_train", {})
    return {
        "resolution_hw": cam.get("render_resolution_hw", [480, 848]),
        "center_crop": cam.get("train_center_crop", "1/6,5/6"),
        "working_distance_main": cam.get("working_distance_m_main", [0.45, 0.55]),
        "working_distance_robust": cam.get("working_distance_m_robust", [0.35, 0.60]),
        "visible_object_count_target": scene.get("visible_object_count_target", [8, 9]),
        "valid_ratio_after_crop": scene.get("target_valid_ratio_after_crop", sensor.get("valid_ratio_range", [0.04, 0.08])),
    }


def place_objects(
    assets: List[Asset],
    rng: random.Random,
    n_objects: int,
    stl_unit_scale: float,
    mat: bpy.types.Material,
    placement_radius: float,
    z_drop_range: Tuple[float, float],
    no_physics: bool,
) -> Tuple[Dict[int, bpy.types.Object], Dict[int, dict]]:
    chosen = rng.sample(assets, k=min(n_objects, len(assets)))
    object_by_category: Dict[int, bpy.types.Object] = {}
    asset_by_category: Dict[int, dict] = {}
    for asset in chosen:
        obj = import_stl_raw(asset.path)
        center_mesh_geometry(obj)
        obj.scale = (stl_unit_scale, stl_unit_scale, stl_unit_scale)
        obj.rotation_euler = Euler((rng.uniform(-0.15, 0.15), rng.uniform(-0.15, 0.15), rng.uniform(0, 2 * math.pi)), 'XYZ')
        r = placement_radius * math.sqrt(rng.random())
        theta = rng.uniform(0, 2 * math.pi)
        obj.location = (r * math.cos(theta), r * math.sin(theta), rng.uniform(*z_drop_range))
        obj.name = canonical_stem(asset.stl)
        obj["category_id"] = int(asset.category_id)
        obj["stl"] = asset.stl
        assign_gray_material(obj, mat)
        if no_physics:
            set_origin_on_floor(obj)
        else:
            add_rigidbody(obj, 'ACTIVE', mass=0.02)
        object_by_category[int(asset.category_id)] = obj
        asset_by_category[int(asset.category_id)] = {"stl": asset.stl, "class_name": asset.class_name, "category_id": int(asset.category_id)}
    return object_by_category, asset_by_category


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset_manifest", required=True, type=Path)
    ap.add_argument("--out_root", required=True, type=Path)
    ap.add_argument("--request_json", type=Path, default=None)
    ap.add_argument("--num_scenes", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--start_idx", type=int, default=0)
    ap.add_argument("--max_attempts_per_scene", type=int, default=12)
    ap.add_argument("--stl_unit_scale", type=float, default=0.001, help="STL unit to meter scale; use 0.001 for mm STLs")
    ap.add_argument("--hfov_deg", type=float, default=62.0)
    ap.add_argument("--fx", type=float, default=None)
    ap.add_argument("--fy", type=float, default=None)
    ap.add_argument("--cx", type=float, default=None)
    ap.add_argument("--cy", type=float, default=None)
    ap.add_argument("--physics_frames", type=int, default=90)
    ap.add_argument("--no_physics", action="store_true")
    ap.add_argument("--min_visible_pixels", type=int, default=80)
    ap.add_argument("--placement_radius", type=float, default=0.08)
    ap.add_argument("--z_drop_min", type=float, default=0.06)
    ap.add_argument("--z_drop_max", type=float, default=0.18)
    ap.add_argument("--camera_xy_jitter", type=float, default=0.015)
    ap.add_argument("--camera_tilt_deg", type=float, default=2.5)
    ap.add_argument("--allow_profile_mismatch", action="store_true", help="Save best attempt even if target valid-ratio/object-count is not met")
    args = ap.parse_args()

    assets = load_assets(args.asset_manifest)
    request = read_json(args.request_json, default={}) or {}
    cfg = request_defaults(request)
    H, W = int(cfg["resolution_hw"][0]), int(cfg["resolution_hw"][1])
    center_crop = cfg["center_crop"]
    valid_min, valid_max = [float(x) for x in cfg["valid_ratio_after_crop"]]
    count_min, count_max = [int(x) for x in cfg["visible_object_count_target"]]
    wd_min, wd_max = [float(x) for x in cfg["working_distance_main"]]

    rng = random.Random(args.seed)
    np.random.seed(args.seed)

    args.out_root.mkdir(parents=True, exist_ok=True)
    ensure_dirs(args.out_root)

    summary_rows: List[dict] = []
    bproc.init()
    # Render relatively clean depth; train-time sensorization happens in dataloader.
    bproc.renderer.set_output_format(enable_transparency=False)
    # Fast CPU/GPU agnostic defaults.
    try:
        bproc.renderer.set_max_amount_of_samples(32)
    except Exception:
        pass

    for scene_i in range(args.start_idx, args.start_idx + args.num_scenes):
        best_payload = None
        best_score = float("inf")
        for attempt in range(args.max_attempts_per_scene):
            clear_scene()
            setup_camera(W, H, args.fx, args.fy, args.cx, args.cy, args.hfov_deg)
            bg_kind = "white_desk" if rng.random() < 0.65 else "clear_box"
            plane = setup_world(bg_kind)
            add_basic_lights()
            gray_mat = create_material("mat_parts_gray", (0.55, 0.55, 0.55, 1.0))
            if not args.no_physics:
                add_rigidbody(plane, 'PASSIVE')

            n_obj = rng.randint(count_min, count_max)
            object_by_category, asset_by_category = place_objects(
                assets=assets,
                rng=rng,
                n_objects=n_obj,
                stl_unit_scale=args.stl_unit_scale,
                mat=gray_mat,
                placement_radius=args.placement_radius,
                z_drop_range=(args.z_drop_min, args.z_drop_max),
                no_physics=args.no_physics,
            )
            if not args.no_physics:
                run_physics(args.physics_frames)

            camera_height = rng.uniform(wd_min, wd_max)
            set_camera_pose_top_down(camera_height, args.camera_xy_jitter, args.camera_tilt_deg, rng)
            try:
                depth, inst_raw, cat_raw, attrs = render_depth_and_seg()
            except Exception as e:
                print(f"[scene {scene_i:05d} attempt {attempt}] render failed: {e}")
                continue

            inst, cat, meta_instances, visible_ids = remap_visible_instances(
                depth, inst_raw, cat_raw, {}, min_pixels=args.min_visible_pixels
            )
            obj_pixels = inst > 0
            depth_obj = depth.copy().astype(np.float32)
            depth_obj[~obj_pixels] = np.nan
            y0, x0, y1, x1 = center_crop_bbox_hw(H, W, center_crop)
            crop_valid = np.isfinite(depth_obj[y0:y1, x0:x1])
            valid_ratio = float(crop_valid.mean())
            visible_count = len(visible_ids)
            # Score target profile. Count mismatch is less important than valid ratio.
            ratio_penalty = 0.0 if (valid_min <= valid_ratio <= valid_max) else min(abs(valid_ratio - valid_min), abs(valid_ratio - valid_max))
            count_penalty = 0.0 if (count_min <= visible_count <= count_max) else min(abs(visible_count - count_min), abs(visible_count - count_max)) * 0.02
            score = ratio_penalty + count_penalty
            payload = (depth, inst, cat, object_by_category, asset_by_category, bg_kind, visible_count, valid_ratio)
            if score < best_score:
                best_score = score
                best_payload = payload
            if valid_min <= valid_ratio <= valid_max and count_min <= visible_count <= count_max:
                break

        if best_payload is None:
            raise RuntimeError(f"Failed to render scene {scene_i:05d} after {args.max_attempts_per_scene} attempts")
        depth, inst, cat, object_by_category, asset_by_category, bg_kind, visible_count, valid_ratio = best_payload
        if not args.allow_profile_mismatch and not (valid_min <= valid_ratio <= valid_max):
            print(f"[WARN] scene {scene_i:05d}: valid_ratio_crop={valid_ratio:.4f} outside target [{valid_min},{valid_max}], saving best attempt")

        stat = save_scene_and_crops(
            out_root=args.out_root,
            scene_idx=scene_i,
            depth=depth,
            inst_id=inst,
            category_id=cat,
            meta_instances={},
            object_by_category=object_by_category,
            asset_by_category=asset_by_category,
            bg_kind=bg_kind,
            center_crop=center_crop,
        )
        summary_rows.append(stat)
        if (scene_i - args.start_idx + 1) % 10 == 0 or scene_i == args.start_idx:
            print(f"[{scene_i:05d}] visible={stat['visible_count']} valid_crop={stat['valid_ratio_crop']:.4f} median={stat['depth_median_crop']}")

    summary = {
        "num_scenes": len(summary_rows),
        "request_json": str(args.request_json) if args.request_json else None,
        "asset_manifest": str(args.asset_manifest),
        "resolution_hw": [H, W],
        "center_crop": center_crop,
        "valid_ratio_crop_mean": float(np.mean([r["valid_ratio_crop"] for r in summary_rows])),
        "valid_ratio_crop_p05": float(np.percentile([r["valid_ratio_crop"] for r in summary_rows], 5)),
        "valid_ratio_crop_p95": float(np.percentile([r["valid_ratio_crop"] for r in summary_rows], 95)),
        "visible_count_mean": float(np.mean([r["visible_count"] for r in summary_rows])),
        "rows": summary_rows[:20],
    }
    (args.out_root / "B_blenderproc_generation_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Done. Wrote dataset to {args.out_root}")


if __name__ == "__main__":
    main()
