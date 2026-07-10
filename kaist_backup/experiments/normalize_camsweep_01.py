"""
camsweep(raw meter, 배경 NaN) → 실측 eval과 동일 도메인으로 정규화.
- 부품 픽셀(inst_id>0)만 per-scene min-max [0,1] 정규화
- 배경(inst_id==0) = NaN 유지 (실측 eval과 동일: 배경 NaN, 부품 0-1)
- inst_id / category_id / meta 그대로 복사
7/4: 미팅 안건 ①값도메인통일(회색조) + ②정규화 를 camsweep 39.6% baseline에 적용.
"""
import numpy as np, glob, os, sys, shutil

SRC = "data/2d_dataset_camsweep"
DST = "data/2d_dataset_camsweep_norm01"

def find_npz(root):
    fs = sorted(glob.glob(os.path.join(root, "**", "*.npz"), recursive=True))
    return [f for f in fs if "/npz/" in f or os.path.basename(os.path.dirname(f)) == "npz"]

def main():
    src_files = find_npz(SRC)
    if not src_files:
        # npz가 최상위에 흩어져 있을 수도
        src_files = sorted(glob.glob(os.path.join(SRC, "*.npz")))
    print("src npz:", len(src_files), "예시:", src_files[0] if src_files else None)
    assert src_files, "camsweep npz 없음"

    # 상대경로 구조 보존
    n_ok = 0
    for f in src_files:
        rel = os.path.relpath(f, SRC)
        out = os.path.join(DST, rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        d = np.load(f)
        dep = d["depth"].astype(np.float32).copy()
        inst = d["inst_id"]
        part = inst > 0
        pv = dep[part]
        pv = pv[np.isfinite(pv)]
        if pv.size == 0:
            # 빈 장면: 그대로 저장
            newdep = dep
        else:
            lo, hi = float(pv.min()), float(pv.max())
            rng = hi - lo if hi > lo else 1.0
            newdep = np.full_like(dep, np.nan, dtype=np.float32)
            # 부품만 0-1, 배경 NaN
            pm = part & np.isfinite(dep)
            newdep[pm] = (dep[pm] - lo) / rng
            newdep = np.clip(newdep, 0.0, 1.0)
            # 배경은 NaN (이미 full nan)
        save = {k: d[k] for k in d.keys()}
        save["depth"] = newdep
        np.savez_compressed(out, **save)
        n_ok += 1
        if n_ok % 200 == 0:
            print("  ", n_ok, "완료")
    print("정규화 완료:", n_ok, "→", DST)

    # splits 폴더 복사 (train/val/test.json = 상대경로 ../npz 기준이므로 구조 동일하면 그대로 유효)
    src_splits = os.path.join(SRC, "splits")
    dst_splits = os.path.join(DST, "splits")
    if os.path.isdir(src_splits):
        if os.path.isdir(dst_splits):
            shutil.rmtree(dst_splits)
        shutil.copytree(src_splits, dst_splits)
        print("splits 복사 완료")
    else:
        print("⚠️ src splits 없음 → 학습 전 make_scene_splits 필요")

if __name__ == "__main__":
    main()
