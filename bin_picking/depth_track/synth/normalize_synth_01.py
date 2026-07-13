#!/usr/bin/env python3
"""합성 scene npz(raw meter, 배경 NaN) → 부품 per-scene 0-1 정규화 npz.

7/3 미팅(조교) 지시: "test(실측)를 노멀라이즈한 높이 = train(합성)도 똑같이".
측정으로 확인(7/4): 합성=raw meter, 실측=0-1 상태라 robust_normalize 후 입력분포가 어긋남
  (실측 z_norm +1.21 vs 합성 +0.36). → 합성도 실측 변환기와 **동일한 per-scene 0-1**로 통일.

⭐ 정규화 로직은 scripts/labelme_to_synthformat.py 와 완전 동일해야 함:
  - 배경 = 0 (실측: BG_VALUE=0). 합성 원본은 배경 NaN → 0으로.
  - 부품 픽셀만 [0,1] per-scene min-max clip.
  - depth 단위는 무관(선형이므로 min-max가 흡수). meter 그대로 min-max.

inst_id / category_id / meta 는 그대로 복사. depth만 변환.
resize 불필요(합성은 이미 512x512).

호출:
  python normalize_synth_01.py --in_dir  /data/jtm/synth_out/dataset_2denc_camnear/npz \
                               --out_dir /data/jtm/synth_out/dataset_2denc_camnear_01/npz
"""
import argparse, glob, os, json
import numpy as np

BG_VALUE = 0.0   # 실측 변환기와 동일 (배경 0)


def normalize_one(src_path, dst_path):
    d = np.load(src_path, allow_pickle=True)
    depth = d["depth"].astype(np.float32)          # (H,W) meter, 배경 NaN
    inst  = d["inst_id"]
    part = inst > 0                                  # 부품 = inst_id>0 (실측: mask & depth>0)
    # 합성 배경은 NaN. 부품 픽셀 중 유효(finite & >0)만 정규화 대상.
    valid_part = part & np.isfinite(depth) & (depth > 0)

    out = np.full(depth.shape, BG_VALUE, np.float32)  # 배경 0
    pv = depth[valid_part]
    if pv.size:
        lo, hi = float(pv.min()), float(pv.max())   # per-scene min-max (실측과 동일)
        rng = max(hi - lo, 1e-6)
        out[valid_part] = np.clip((pv - lo) / rng, 0.0, 1.0)

    # meta에 정규화 표식 추가
    try:
        meta = json.loads(str(d["meta"]))
    except Exception:
        meta = {}
    meta["depth_units"] = "normalized_01"
    meta["norm_mode"] = "per_scene"
    meta["background"] = "0"
    meta["norm_note"] = "7/4: train/test 동일 0-1 정합 (조교 7/3 지시). 원본=raw meter."

    save = {k: d[k] for k in d.files if k not in ("depth", "meta")}
    save["depth"] = out
    save["meta"] = json.dumps(meta, ensure_ascii=False)
    np.savez_compressed(dst_path, **save)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_dir", required=True, help="raw meter scene npz 폴더")
    ap.add_argument("--out_dir", required=True, help="0-1 정규화 출력 npz 폴더")
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    files = sorted(glob.glob(os.path.join(args.in_dir, "*.npz")))
    print(f"=== 합성 0-1 정규화: {len(files)}장 → {args.out_dir} ===")
    ok = 0
    for f in files:
        dst = os.path.join(args.out_dir, os.path.basename(f))
        normalize_one(f, dst)
        ok += 1
        if ok % 100 == 0:
            print(f"  {ok}/{len(files)}")
    print(f"✅ {ok}/{len(files)} 완료")


if __name__ == "__main__":
    main()
