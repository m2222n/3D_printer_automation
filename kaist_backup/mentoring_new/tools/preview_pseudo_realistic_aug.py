#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from depth_vq_detector.depth_preprocess import (
    load_depth, parse_float_range, preprocess_metric_depth,
)


def show(ax, depth, title):
    valid=np.isfinite(depth)&(depth>0)
    img=np.zeros_like(depth,dtype=np.float32)
    if valid.sum():
        vals=depth[valid]
        p1,p99=np.percentile(vals,[1,99])
        img[valid]=1.0-np.clip((depth[valid]-p1)/(p99-p1+1e-8),0,1)
        text=f"valid={valid.mean()*100:.2f}%\nmean={vals.mean():.3f}m\np5/p95={np.percentile(vals,5):.3f}/{np.percentile(vals,95):.3f}m"
    else:
        text='no valid pixels'
    ax.imshow(img,cmap='gray',vmin=0,vmax=1); ax.axis('off'); ax.set_title(title)
    ax.text(0.01,0.99,text,transform=ax.transAxes,va='top',ha='left',fontsize=9,color='white',bbox=dict(facecolor='black',alpha=.55))


def main():
    ap=argparse.ArgumentParser(description='Preview pseudo-to-real input augmentation pipeline.')
    ap.add_argument('--scene_npz', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--target_median_range', default='0.45,0.55')
    ap.add_argument('--depth_keep_range', default='0.35,0.65')
    ap.add_argument('--pseudo_uint16_max_depth_m', type=float, default=10.0)
    ap.add_argument('--noise_sigma_m', type=float, default=0.0015)
    ap.add_argument('--noise_rel_sigma', type=float, default=0.002)
    ap.add_argument('--random_dropout_prob', type=float, default=0.02)
    ap.add_argument('--boundary_dropout_prob', type=float, default=0.35)
    ap.add_argument('--boundary_radius', type=int, default=2)
    ap.add_argument('--hole_prob', type=float, default=2.0)
    ap.add_argument('--target_valid_ratio_range', default='0.04,0.08')
    ap.add_argument('--avg_pool_kernel', type=int, default=3)
    ap.add_argument('--seed', type=int, default=42)
    args=ap.parse_args()
    raw=load_depth(args.scene_npz)
    rng=np.random.default_rng(args.seed)
    shifted=preprocess_metric_depth(raw,target_median_range=parse_float_range(args.target_median_range),target_median_random=False,rng=rng)
    aug=preprocess_metric_depth(
        raw,
        target_median_range=parse_float_range(args.target_median_range),
        target_median_random=True,
        keep_depth_range=parse_float_range(args.depth_keep_range),
        pseudo_uint16_max_depth_m=args.pseudo_uint16_max_depth_m,
        noise_sigma_m=args.noise_sigma_m,
        noise_rel_sigma=args.noise_rel_sigma,
        random_dropout_prob=args.random_dropout_prob,
        boundary_dropout_prob=args.boundary_dropout_prob,
        boundary_radius=args.boundary_radius,
        hole_prob=args.hole_prob,
        target_valid_ratio_range=parse_float_range(args.target_valid_ratio_range),
        avg_pool_kernel=args.avg_pool_kernel,
        rng=rng,
    )
    fig,axs=plt.subplots(1,3,figsize=(15,5))
    show(axs[0],raw,'raw pseudo')
    show(axs[1],shifted,'median shifted')
    show(axs[2],aug,'sensorized pseudo input')
    Path(args.out).parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(args.out,dpi=160,bbox_inches='tight')
    print('wrote', args.out)
if __name__=='__main__': main()
