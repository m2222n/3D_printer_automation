#!/usr/bin/env bash
# 7/3 cam_sweep HI 배치 러너 — cam_h 0.5~1.6m 스윕(상한↑), FOV 고정.
# 배경: 7/2 camsweep(0.4~1.0m)이 실측 5%→39.6%로 진범=스케일 확증. 다만 부품이 여전히
#       실측(407px)보다 큼(1530px). → 상한 1.6m로 부품을 더 작게(원거리) 커버해 39.6%↑ 검증.
# 기존 dataset_2denc / dataset_2denc_camsweep 는 안 건드리고 새 폴더에 생성. resume 지원.
set -u
BP=/data/jtm/blenderproc_venv/bin/blenderproc
SCRIPT=/home/jtm/kaist_project/synth/gen_one_2denc_camsweep_hi.py
BLENDER=/data/jtm/blender
OUT=/data/jtm/synth_out/dataset_2denc_camsweep_hi
NPZ=$OUT/npz
LOG=$OUT/run.log
N=${1:-1000}      # 총 장수 (기존 camsweep과 매칭)
WORKERS=${2:-6}   # 병렬 워커 수

mkdir -p "$NPZ"
echo "=== cam_sweep HI batch 시작: N=$N, workers=$WORKERS, out=$OUT ===" | tee -a "$LOG"
date | tee -a "$LOG"

render_one() {
  local idx=$1
  local f
  f=$(printf "%s/scene_%05d.npz" "$NPZ" "$idx")
  if [ -f "$f" ]; then return 0; fi   # resume: 이미 있으면 skip
  "$BP" run "$SCRIPT" --blender-install-path "$BLENDER" -- "$idx" "$OUT" \
     >> "$OUT/worker_$((idx % WORKERS)).log" 2>&1
}
export -f render_one
export BP SCRIPT BLENDER OUT NPZ WORKERS

seq 0 $((N-1)) | xargs -P "$WORKERS" -I {} bash -c 'render_one "$@"' _ {}

echo "=== 완료 ===" | tee -a "$LOG"
date | tee -a "$LOG"
echo "생성된 scene 수: $(ls "$NPZ"/*.npz 2>/dev/null | wc -l)" | tee -a "$LOG"
