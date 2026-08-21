#!/usr/bin/env bash
# TTA 측정 (2026-08-21) — F1 이득 + 추론 시간을 함께 잰다
# ⭐ 변수는 --scales 하나뿐. 나머지는 baseline과 동일(thr 0.20·동기화된 동치 처리).
#    scales=1.0 단독 = TTA 없음 = 이 스크립트 안의 baseline (조건 완전 동일)
set -uo pipefail
export PATH=/opt/conda/bin:$PATH; export CUDA_VISIBLE_DEVICES=0; export PYTHONUNBUFFERED=1
MN=/workspace/cadence/mentoring_new; cd $MN
CKPT=/workspace/cadence/runs/T100_csblur_lr1e4_ep80/best.pt
M=/workspace/cadence/runs/V0821_tta.log
echo "===== TTA 측정 (thr 0.20, T100, 0818 90장) $(date -u) =====" > $M
for sc in "1.0" "1.0,0.85,1.15" "1.0,0.9,1.1,0.8,1.2"; do
  tag=$(echo $sc | tr ',.' '__')
  python eval_tta.py --checkpoint $CKPT \
    --depth_dir $MN/data/real_depth_0818/npy --label_dir $MN/data/real_labels_0818 \
    --out_dir /workspace/cadence/tta_$tag --scales "$sc" --score_thresh 0.20 \
    > /tmp/tta_$tag.log 2>&1
  python -c "
import json
s=json.load(open('/workspace/cadence/tta_$tag/eval_tta_metrics.json'))['summary']
t=s['timing']
print('  scales=%-22s F1 %.4f  P %.3f  R %.3f  (TP %d FP %d FN %d)  |  %.2fs/장 (p95 %.2f)'%(
  '$sc', s['f1_micro'],s['precision_micro'],s['recall_micro'],s['tp'],s['fp'],s['fn'],
  t['sec_mean'],t['sec_p95']))" | tee -a $M
done
echo "완료 $(date -u)" | tee -a $M
