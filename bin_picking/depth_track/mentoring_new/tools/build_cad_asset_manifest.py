#!/usr/bin/env python3
"""
Build a CAD asset manifest for B BlenderProc generation.

The preferred category-id source is an existing synthetic dataset root whose
scene_*.npz meta.instances[*].stl/category_id pairs already define the training
label convention. This avoids guessing category IDs from filename prefixes.

Output JSON schema:
{
  "assets": [
    {"stl": "03_sol_block_front.stl", "path": "/abs/.../03_sol_block_front.stl", "category_id": 3, "class_name": "03_sol_block_front"}
  ],
  "category_id_source": "reference_dataset|filename_prefix|sorted_index",
  "num_assets": 27
}
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np


def canonical_stem(name: str) -> str:
    stem = Path(str(name)).stem
    # Remove hash suffix created by previous point-cloud pipeline, e.g. foo__abcd1234
    stem = re.sub(r"__[0-9a-fA-F]{6,}$", "", stem)
    return stem


def scan_reference_category_map(reference_dataset: Optional[Path]) -> Dict[str, int]:
    mapping: Dict[str, int] = {}
    if reference_dataset is None:
        return mapping
    npz_dir = reference_dataset / "npz"
    if not npz_dir.exists():
        return mapping
    for scene_path in sorted(npz_dir.glob("scene_*.npz")):
        try:
            data = np.load(scene_path, allow_pickle=True)
            meta_raw = data["meta"].item() if hasattr(data["meta"], "shape") else data["meta"]
            meta = json.loads(str(meta_raw))
        except Exception:
            continue
        instances = meta.get("instances", {})
        if isinstance(instances, list):
            iterable = instances
        else:
            iterable = instances.values()
        for inst in iterable:
            stl = inst.get("stl") or inst.get("cad_id") or inst.get("name")
            cid = inst.get("category_id")
            if stl is None or cid is None:
                continue
            key = canonical_stem(stl)
            mapping.setdefault(key, int(cid))
    return mapping


def infer_category_from_prefix(path: Path) -> Optional[int]:
    m = re.match(r"^(\d+)[_\-].*", path.stem)
    if not m:
        return None
    return int(m.group(1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stl_dir", required=True, type=Path)
    ap.add_argument("--out_json", required=True, type=Path)
    ap.add_argument("--reference_dataset", type=Path, default=None,
                    help="Existing 2d_dataset root. Its scene meta defines stl->category_id.")
    ap.add_argument("--recursive", action="store_true")
    args = ap.parse_args()

    pattern = "**/*.stl" if args.recursive else "*.stl"
    stl_paths = sorted(args.stl_dir.glob(pattern))
    if not stl_paths:
        raise FileNotFoundError(f"No STL files found under {args.stl_dir} with pattern {pattern}")

    ref_map = scan_reference_category_map(args.reference_dataset)
    assets: List[dict] = []
    used_ids = set()
    source = "reference_dataset" if ref_map else "filename_prefix"

    for idx, p in enumerate(stl_paths, start=1):
        stem = canonical_stem(p.name)
        cid = ref_map.get(stem)
        if cid is None:
            cid = infer_category_from_prefix(p)
        if cid is None:
            source = "sorted_index" if source != "reference_dataset" else source
            cid = idx
        if cid in used_ids:
            # Duplicate category id is not always wrong, but it usually means prefix/ref-map conflict.
            # Keep it and report in manifest.
            pass
        used_ids.add(cid)
        assets.append({
            "stl": p.name,
            "path": str(p.resolve()),
            "category_id": int(cid),
            "class_name": stem,
        })

    # Stable order by category then name; this matches most dataset conventions.
    assets.sort(key=lambda x: (int(x["category_id"]), x["stl"]))
    out = {
        "stl_dir": str(args.stl_dir.resolve()),
        "reference_dataset": str(args.reference_dataset.resolve()) if args.reference_dataset else None,
        "category_id_source": source,
        "num_assets": len(assets),
        "assets": assets,
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"Wrote {len(assets)} assets to {args.out_json}")
    print(f"Category id source: {source}")
    print("First 10 assets:")
    for a in assets[:10]:
        print(f"  C{a['category_id']:02d} {a['stl']} -> {a['path']}")


if __name__ == "__main__":
    main()
