#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, shutil
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split_json", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--copy", action="store_true")
    args = ap.parse_args()
    d = json.loads(Path(args.split_json).read_text())
    out = Path(args.out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    n=0
    for item in d.get("scenes", []):
        src = Path(item.get("source_depth_path", ""))
        if not src.exists():
            continue
        dst = out / src.name
        if args.copy:
            shutil.copy2(src, dst)
        else:
            os.symlink(src.resolve(), dst)
        n+=1
    print(f"linked {n} depth files to {out}")
if __name__ == "__main__":
    main()
