#!/usr/bin/env python3
"""합성 depth 경계 블러 aug — 7/3 미팅 안건 ③ "엣지 뭉개기(블러)".

배경(왜 이 스크립트가 따로 필요한가):
  - 실측 depth는 부품 표면·경계가 매끈하지 않고 부드럽게 번진다(ToF 특성).
    측정(7/4): 합성 경계 gradient p50=0.000(완벽히 매끈) vs 실측 p50≈0.042(상시 요철).
  - 7/2 `depth_noise.add_blaze_noise`는 블러+dropout+flying pixel을 한꺼번에 넣어
    **과공격적 → 합성 test acc 80→56% 붕괴**(형상 정보 훼손). 그 교훈 반영.
  - 이 스크립트는 조교 지시대로 **경계 블러만** 한다. dropout·flying pixel 없음.

설계 원칙:
  1. 부품 마스크(inst_id>0) 내부에서만 블러 → 배경 0/NaN과 절대 안 섞임(7/2 경계튐 방지).
  2. 원본 raw meter 유지(정규화는 normalize_synth_01이 담당). 여기선 depth 값만 부드럽게.
  3. 강도 파라미터(sigma/kernel)로 light/medium 조절 → 재학습 비교로 최적점 탐색.

inst_id / category_id / meta 는 그대로 복사. depth만 블러.

호출:
  python edge_blur_aug.py --in_dir  /data/jtm/synth_out/dataset_2denc_camnear/npz \
                          --out_dir /data/jtm/synth_out/dataset_2denc_camnear_blur/npz \
                          --strength light   # light | medium
"""
import argparse, glob, os, json
import numpy as np


def _box_blur(a, k):
    """k×k 박스(평균) 블러. 누적합 O(N)."""
    pad = k // 2
    ap = np.pad(a, pad, mode="edge")
    cs = np.cumsum(np.cumsum(ap, axis=0), axis=1)
    cs = np.pad(cs, ((1, 0), (1, 0)), mode="constant")
    H, W = a.shape
    s = (cs[k:k+H, k:k+W] - cs[:H, k:k+W] - cs[k:k+H, :W] + cs[:H, :W])
    return (s / (k * k)).astype(np.float32)


def masked_blur(depth, part, passes, k):
    """부품 픽셀만 블러. 배경(0/NaN)과 안 섞이도록 depth*valid / valid 방식.

    passes회 반복하면 더 부드러워짐(가우시안 근사). 각 pass는 부품 내부에서만
    유효값 평균을 취하고, 경계 밖(배경)은 가중치 0이라 침범하지 않는다.
    """
    valid = part & np.isfinite(depth) & (depth > 0)
    d = np.where(valid, depth, 0.0).astype(np.float32)
    w = valid.astype(np.float32)
    out = d.copy()
    for _ in range(passes):
        num = _box_blur(out * w, k)
        den = _box_blur(w, k)
        blurred = np.where(den > 1e-6, num / np.maximum(den, 1e-6), out)
        out = np.where(valid, blurred, out)  # 부품 픽셀만 갱신
    result = depth.astype(np.float32).copy()
    result[valid] = out[valid]
    return result


STRENGTH = {
    # 측정(7/4): 합성 경계 grad p50=0.000(완벽 매끈) vs 실측 p50≈0.042(표면 요철).
    #   → 블러만으론 "없는 요철"을 못 만든다. 약한 표면 노이즈(surf_sigma)를 함께 준다.
    #   dropout·flying pixel은 넣지 않는다(7/2 과공격 붕괴 교훈).
    # surf_sigma = 부품 depth에 더할 Gaussian σ(meter). 실측 요철감 근사. 마스크 내부만.
    "light":  dict(passes=1, k=3, surf_sigma=0.0010),   # 1mm — 경계 살짝 + 표면 미세
    "medium": dict(passes=1, k=3, surf_sigma=0.0020),   # 2mm — 표면 요철 뚜렷
    # 7/4 추가측정: light(grad0.013)/medium(0.026) 둘 다 실측 요철(0.059)에 미달 →
    #   강도 스윕을 heavy로 완성. surf_sigma 3.5mm + passes 1(과블러로 형상 뭉개짐 방지).
    "heavy":  dict(passes=1, k=3, surf_sigma=0.0035),   # 3.5mm — 실측 요철(0.059)에 근접 목표
    "blur_only": dict(passes=2, k=3, surf_sigma=0.0),   # 블러만(노이즈 없음) 대조군
}


def process_one(src, dst, strength, rng):
    d = np.load(src, allow_pickle=True)
    depth = d["depth"].astype(np.float32)     # raw meter, 배경 NaN
    inst = d["inst_id"]
    part = inst > 0
    cfg = STRENGTH[strength]
    valid = part & np.isfinite(depth) & (depth > 0)

    # ① 약한 표면 노이즈(실측 요철 근사) — 마스크 내부만, 배경 안 건드림
    out = depth.astype(np.float32).copy()
    if cfg["surf_sigma"] > 0:
        noise = rng.normal(0.0, cfg["surf_sigma"], size=depth.shape).astype(np.float32)
        out[valid] = out[valid] + noise[valid]
    # ② 경계 블러 — 노이즈 후 부드럽게(과한 튐 방지)
    blurred = masked_blur(out, part, cfg["passes"], cfg["k"])

    try:
        meta = json.loads(str(d["meta"]))
    except Exception:
        meta = {}
    meta["edge_blur"] = strength
    meta["edge_blur_note"] = (f"7/4 미팅안건③ 경계블러+표면노이즈 (passes={cfg['passes']}, "
                              f"k={cfg['k']}, surf_sigma={cfg['surf_sigma']}m, 마스크내부만, dropout없음)")

    save = {k: d[k] for k in d.files if k not in ("depth", "meta")}
    save["depth"] = blurred
    save["meta"] = json.dumps(meta, ensure_ascii=False)
    np.savez_compressed(dst, **save)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_dir", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--strength", default="light", choices=list(STRENGTH))
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    rng = np.random.default_rng(1234)   # 재현성 고정
    files = sorted(glob.glob(os.path.join(args.in_dir, "*.npz")))
    print(f"=== 경계블러+표면노이즈 aug ({args.strength}): {len(files)}장 → {args.out_dir} ===")
    for i, f in enumerate(files, 1):
        process_one(f, os.path.join(args.out_dir, os.path.basename(f)), args.strength, rng)
        if i % 100 == 0:
            print(f"  {i}/{len(files)}")
    print(f"✅ {len(files)}장 완료")


if __name__ == "__main__":
    main()
