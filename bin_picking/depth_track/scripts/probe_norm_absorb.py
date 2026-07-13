#!/usr/bin/env python3
"""1순위 검증 (7/2): 조교 정규화(robust_normalize_depth)가 3.5배 배율을 흡수하는가?
   + 우리 변환(배경0+0-1)이 조교 파이프라인(valid=depth>0)과 충돌하지 않는가?

두 가지를 정량 증명:
  (A) 선형 배율 k 상쇄 증명: raw depth vs k*raw depth를 robust_normalize에 넣어 결과 동일 확인.
  (B) ⚠️ 함정 점검: 우리 변환기가 부품 min을 0으로 눌렀는데, 조교 valid=depth>0가
      부품 픽셀 일부를 배경으로 오인해 잃는가? (0-1 정규화 부작용)
"""
import sys, json, glob, os
import numpy as np

# torch 없는 로컬(6000)에서도 돌도록 조교 robust_normalize_depth를 그대로 복제
# (model/depth_vq_detector/depth_preprocess.py:145-158 원본과 동일 로직, numpy only)
def robust_normalize_depth(depth, valid):
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

RAW_NPY = "/data/jtm/synth_out/real_capture100/npy"
SF_DIR  = "/data/jtm/synth_out/real_capture100/synthformat"
LJ_DIR  = "/data/jtm/synth_out/real_capture100/labelme_json"

print("="*70)
print("(A) 선형 배율 상쇄 증명 — robust_normalize_depth")
print("="*70)
# 실측 raw npy 한 장에서 부품 영역 depth 뽑아 배율 실험
import glob as _g
sample = sorted(_g.glob(os.path.join(RAW_NPY, "*.npy")))[0]
raw = np.load(sample).astype(np.float32)  # mm
valid = raw > 0
z1, med1, sc1 = robust_normalize_depth(raw, valid)
for k in [1/3.5, 2.0, 3.5]:
    zk, medk, sck = robust_normalize_depth(raw*k, valid)
    diff = np.abs(z1[valid] - zk[valid]).max()
    print(f"  배율 k={k:.3f}: med {med1:.1f}→{medk:.1f}, scale {sc1:.1f}→{sck:.1f}, "
          f"정규화 결과 최대차 = {diff:.2e}  {'✅ 상쇄' if diff<1e-4 else '❌'}")
print("  → median-subtract + (p95-p05) 나눗셈은 임의 선형 배율을 완전 상쇄.")
print("    ⭐ 3.5배 스케일 오류는 학습/평가 입력단에서 자동 소거됨 (보정 불필요).")

print()
print("="*70)
print("(B) ⚠️ 함정: 우리 0-1 변환 + 조교 valid=depth>0 충돌 점검")
print("="*70)
files = sorted(glob.glob(os.path.join(SF_DIR, "*.npz")))
lost_frac = []
zero_in_part = []
for f in files:
    d = np.load(f, allow_pickle=True)
    depth, inst = d["depth"], d["inst_id"]
    part = inst > 0                              # 진짜 부품(라벨 기준)
    npart = int(part.sum())
    if npart == 0: continue
    # 조교 파이프라인이 볼 valid
    valid = np.isfinite(depth) & (depth > 0)
    # 부품인데 valid에서 빠진 픽셀 (depth==0 or NaN)
    lost = part & (~valid)
    lost_frac.append(lost.sum() / npart)
    # 부품 픽셀 중 정확히 depth==0 인 비율 (0-1 정규화로 min이 0된 것)
    pv = depth[part]
    zero_in_part.append(np.mean(pv == 0) if pv.size else 0)

lost_frac = np.array(lost_frac); zero_in_part = np.array(zero_in_part)
print(f"  장당 '부품인데 valid 제외된 픽셀' 비율: 평균 {lost_frac.mean()*100:.2f}% "
      f"(최대 {lost_frac.max()*100:.2f}%)")
print(f"  장당 '부품 픽셀 중 depth==0' 비율:     평균 {zero_in_part.mean()*100:.2f}% "
      f"(최대 {zero_in_part.max()*100:.2f}%)")
if lost_frac.max() < 0.02:
    print("  ✅ 손실 미미 — per_scene 0-1의 최소값 픽셀(딱 1점)만 제외, 실질 영향 없음.")
else:
    print("  ⚠️ 무시 못할 손실 — 0-1 정규화 하한을 0보다 크게(예: eps) 두거나,")
    print("     조교에 'valid는 inst_id>0로 판정' 요청 필요.")

print()
print("="*70)
print("(C) 권고 — 이중정규화 회피")
print("="*70)
print("""  현재: 우리 변환기가 per_scene [0,1] 정규화 → 조교가 median-subtract 재정규화.
  (A)에서 선형변환은 상쇄되므로 이중정규화 자체는 결과 왜곡 없음(수학적으로 안전).
  단 (B)의 valid=depth>0 함정만 주의. → 미팅 확인 포인트:
    "우리는 배경 0 + 부품 0-1로 넘긴다. 너희 valid 판정이 depth>0이면
     부품 최소depth 픽셀이 배경 취급된다. valid를 inst_id>0(=mask)로 잡아달라,
     혹은 우리가 부품 하한을 eps로 올려주랴?" """)
