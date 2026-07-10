#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path


def main():
    ap=argparse.ArgumentParser(description='Create a renderer handoff JSON from a measured real profile and regeneration defaults.')
    ap.add_argument('--real_profile_json', required=True, help='Output from tools/measure_real_depth_profile.py')
    ap.add_argument('--base_config', default='configs/pseudo_regen_profile.json')
    ap.add_argument('--out_json', required=True)
    args=ap.parse_args()
    prof=json.loads(Path(args.real_profile_json).read_text(encoding='utf-8'))
    base=json.loads(Path(args.base_config).read_text(encoding='utf-8')) if Path(args.base_config).exists() else {}
    agg=prof.get('aggregate',{})
    out=dict(base)
    out['measured_real_profile']=agg
    if agg.get('depth_p05_m') is not None and agg.get('depth_p95_m') is not None:
        out.setdefault('camera',{})['working_distance_m_main']=[round(float(agg['depth_p05_m']),3), round(float(agg['depth_p95_m']),3)]
        med=agg.get('depth_median_m') or agg.get('depth_mean_m')
        if med:
            lo=max(0.30, float(med)-0.10); hi=float(med)+0.10
            out['camera']['working_distance_m_robust']=[round(lo,3), round(hi,3)]
    if agg.get('valid_ratio_p10') is not None and agg.get('valid_ratio_p90') is not None:
        out.setdefault('scene',{})['target_valid_ratio_after_crop']=[round(float(agg['valid_ratio_p10']),4), round(float(agg['valid_ratio_p90']),4)]
        out.setdefault('depth_output',{}).setdefault('sensorization_for_train',{})['valid_ratio_range']=out['scene']['target_valid_ratio_after_crop']
    Path(args.out_json).parent.mkdir(parents=True,exist_ok=True)
    Path(args.out_json).write_text(json.dumps(out,indent=2),encoding='utf-8')
    print(json.dumps(out.get('camera',{}),indent=2))
    print('wrote', args.out_json)
if __name__=='__main__': main()
