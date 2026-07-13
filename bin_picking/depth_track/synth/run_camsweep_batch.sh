#!/usr/bin/env bash
# 7/2 cam_sweep 배치 러너 — 실측 정합용 합성 1000장 재생성 (cam_h 0.4~1.0m 스윕, FOV 고정)
# 기존 dataset_2denc 는 안 건드리고 새 폴더에 생성. resume 지원(이미 있는 scene 건너뜀).
# 4개 병렬 워커. 각 워커가 자기 몫 인덱스만 담당.
set -u
BP=/data/jtm/blenderproc_venv/bin/blenderproc
SCRIPT=/home/jtm/kaist_project/synth/gen_one_2denc_camsweep.py
BLENDER=/data/jtm/blender
OUT=/data/jtm/synth_out/dataset_2denc_camsweep
NPZ=$OUT/npz
LOG=$OUT/run.log
N=${1:-1000}      # 총 장수 (기본 1000, 기존 2denc와 매칭)
WORKERS=${2:-4}   # 병렬 워커 수

mkdir -p "$NPZ"
echo "=== cam_sweep batch 시작: N=$N, workers=$WORKERS, out=$OUT ===" | tee -a "$LOG"
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

# 0..N-1 인덱스를 xargs로 WORKERS개 병렬 처리
seq 0 $((N-1)) | xargs -P "$WORKERS" -I {} bash -c 'render_one "$@"' _ {}

echo "=== 완료 ===" | tee -a "$LOG"
date | tee -a "$LOG"
echo "생성된 scene 수: $(ls "$NPZ"/*.npz 2>/dev/null | wc -l)" | tee -a "$LOG"
