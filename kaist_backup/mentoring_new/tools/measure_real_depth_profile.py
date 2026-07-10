#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, math
from pathlib import Path
import numpy as np


def parse_range(s: str | None):
    if not s or s.lower() in {'none','off'}:
        return None
    def one(x):
        x=x.strip()
        if '/' in x:
            a,b=x.split('/',1); return float(a)/float(b)
        return float(x)
    p=[one(x) for x in s.split(',')]
    if len(p)==2:
        return p[0],p[1],p[0],p[1]
    if len(p)==4:
        return tuple(p)
    raise ValueError('range must be y0,y1 or y0,y1,x0,x1')


def crop_center(depth, fracs):
    if fracs is None: return depth, [0,0,depth.shape[0], depth.shape[1]]
    y0f,y1f,x0f,x1f=fracs
    h,w=depth.shape
    y0,y1=round(h*y0f), round(h*y1f)
    x0,x1=round(w*x0f), round(w*x1f)
    return depth[y0:y1, x0:x1], [int(y0), int(x0), int(y1), int(x1)]


def load_depth(path: Path, max_depth_m: float):
    arr=np.load(path)
    if arr.dtype.kind in 'iu':
        d=arr.astype(np.float32)*(max_depth_m/65535.0)
        d[arr<=0]=np.nan
    else:
        d=arr.astype(np.float32)
        d[~np.isfinite(d) | (d<=0)] = np.nan
    return d


def main():
    ap=argparse.ArgumentParser(description='Measure real depth distribution/profile for pseudo regeneration and train augmentations.')
    ap.add_argument('--depth_dir', required=True)
    ap.add_argument('--glob', default='shot_*_g1.npy')
    ap.add_argument('--out_json', required=True)
    ap.add_argument('--out_csv', default=None)
    ap.add_argument('--real_uint16_max_depth_m', type=float, default=10.0)
    ap.add_argument('--center_crop', default='1/6,5/6')
    ap.add_argument('--depth_keep_range', default='0.40,0.60')
    args=ap.parse_args()

    fr=parse_range(args.center_crop)
    keep=None
    if args.depth_keep_range and args.depth_keep_range.lower() not in {'none','off'}:
        lo,hi=[float(x) for x in args.depth_keep_range.split(',')]
        keep=(lo,hi)

    files=sorted(Path(args.depth_dir).glob(args.glob))
    rows=[]; vals_all=[]
    for f in files:
        try:
            d=load_depth(f,args.real_uint16_max_depth_m)
        except Exception as e:
            rows.append({'file':f.name,'error':str(e)}); continue
        dc,crop=crop_center(d,fr)
        valid=np.isfinite(dc)&(dc>0)
        if keep is not None:
            valid &= (dc>=keep[0]) & (dc<=keep[1])
        vals=dc[valid]
        if vals.size: vals_all.append(vals.astype(np.float32))
        rows.append({
            'file': f.name,
            'source_shape_hw': list(d.shape),
            'crop_bbox_yxyx': crop,
            'crop_shape_hw': list(dc.shape),
            'valid_ratio_crop': float(valid.mean()),
            'num_valid': int(valid.sum()),
            'depth_mean_m': float(vals.mean()) if vals.size else None,
            'depth_median_m': float(np.median(vals)) if vals.size else None,
            'depth_p05_m': float(np.percentile(vals,5)) if vals.size else None,
            'depth_p95_m': float(np.percentile(vals,95)) if vals.size else None,
        })
    allv=np.concatenate(vals_all) if vals_all else np.array([],dtype=np.float32)
    summary={
        'num_files': len(files),
        'valid_files': int(sum(1 for r in rows if r.get('num_valid',0)>0)),
        'depth_dir': str(Path(args.depth_dir).resolve()),
        'glob': args.glob,
        'real_uint16_max_depth_m': args.real_uint16_max_depth_m,
        'center_crop': args.center_crop,
        'depth_keep_range': args.depth_keep_range,
        'aggregate': {
            'valid_ratio_mean': float(np.mean([r.get('valid_ratio_crop',0) for r in rows if 'valid_ratio_crop' in r])) if rows else 0.0,
            'valid_ratio_p10': float(np.percentile([r.get('valid_ratio_crop',0) for r in rows if 'valid_ratio_crop' in r],10)) if rows else 0.0,
            'valid_ratio_p90': float(np.percentile([r.get('valid_ratio_crop',0) for r in rows if 'valid_ratio_crop' in r],90)) if rows else 0.0,
            'depth_mean_m': float(allv.mean()) if allv.size else None,
            'depth_median_m': float(np.median(allv)) if allv.size else None,
            'depth_p05_m': float(np.percentile(allv,5)) if allv.size else None,
            'depth_p95_m': float(np.percentile(allv,95)) if allv.size else None,
        },
        'suggested_train_args': {
            'train_depth_median_range': '0.45,0.55',
            'train_robust_depth_median_range': '0.35,0.60',
            'pseudo_uint16_max_depth_m': 10.0,
            'train_valid_ratio_range': '0.04,0.08',
            'train_boundary_dropout_prob': 0.35,
            'train_boundary_radius': 2,
            'train_random_dropout_prob': 0.02,
            'train_hole_prob': 2.0,
            'train_noise_sigma_m': 0.0015,
            'train_noise_rel_sigma': 0.002,
        },
        'per_file': rows,
    }
    Path(args.out_json).parent.mkdir(parents=True,exist_ok=True)
    Path(args.out_json).write_text(json.dumps(summary,indent=2),encoding='utf-8')
    if args.out_csv:
        import csv
        Path(args.out_csv).parent.mkdir(parents=True,exist_ok=True)
        keys=sorted({k for r in rows for k in r.keys()})
        with open(args.out_csv,'w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=keys); w.writeheader(); w.writerows(rows)
    print(json.dumps(summary['aggregate'],indent=2))
    print('wrote', args.out_json)

if __name__=='__main__': main()
