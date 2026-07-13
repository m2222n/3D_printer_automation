#!/usr/bin/env bash
# 7/4 cam_near 자동 체인 (6000 → A100):
#   1) cam_near 1000장 생성 완료 대기
#   2) 부품 per-scene 0-1 정규화 (train/test 동일 전처리, 조교 7/3 지시)
#   3) A100로 전송
#   4) A100서 재학습(warmup→joint→실측 F1 eval) 원격 실행
# setsid로 독립 실행. 진행 로그 = auto_chain_camnear.log
set -u
KP=/home/jtm/kaist_project
RAW=/data/jtm/synth_out/dataset_2denc_camnear/npz
NORM_DIR=/data/jtm/synth_out/dataset_2denc_camnear_01
NPZ01=$NORM_DIR/npz
LOG=/data/jtm/synth_out/auto_chain_camnear.log
PY=/data/jtm/blenderproc_venv/bin/python
# 학습 서버 접속 정보는 환경변수로 주입 (하드코딩 금지)
#   export GPU_HOST=<user@host>  GPU_PORT=<port>
GPU_HOST="${GPU_HOST:?GPU_HOST 미설정 (예: export GPU_HOST=user@host)}"
GPU_PORT="${GPU_PORT:-22}"
A100="ssh -o ConnectTimeout=15 -o StrictHostKeyChecking=no $GPU_HOST -p $GPU_PORT"
TARGET=${1:-1000}

echo "===== auto_chain_camnear 시작 $(date) target=$TARGET =====" | tee -a $LOG

# 1) 생성 완료 대기 (target장 도달 + blender 프로세스 종료)
while true; do
  n=$(ls $RAW/*.npz 2>/dev/null | wc -l)
  procs=$(pgrep -f gen_one_2denc_camnear | wc -l)
  echo "[대기] 생성 $n/$TARGET, blender proc=$procs $(date)" | tee -a $LOG
  if [ "$n" -ge "$TARGET" ] && [ "$procs" -eq 0 ]; then break; fi
  sleep 120
done
echo "[1] ✅ 생성 완료 ($n장) $(date)" | tee -a $LOG

# 2) 0-1 정규화
echo "[2] 0-1 정규화 시작 $(date)" | tee -a $LOG
$PY $KP/synth/normalize_synth_01.py --in_dir $RAW --out_dir $NPZ01 >> $LOG 2>&1
n01=$(ls $NPZ01/*.npz 2>/dev/null | wc -l)
echo "[2] ✅ 정규화 완료 ($n01장) $(date)" | tee -a $LOG

# 3) A100 전송
echo "[3] A100 전송 시작 $(date)" | tee -a $LOG
$A100 'mkdir -p /workspace/cadence/data/dataset_2denc_camnear_01/npz' >> $LOG 2>&1
rsync -az -e "ssh -p $GPU_PORT -o StrictHostKeyChecking=no" $NPZ01/ \
    "$GPU_HOST:/workspace/cadence/data/dataset_2denc_camnear_01/npz/" >> $LOG 2>&1
ntx=$($A100 'ls /workspace/cadence/data/dataset_2denc_camnear_01/npz/*.npz 2>/dev/null | wc -l')
echo "[3] ✅ A100 전송 완료 ($ntx장) $(date)" | tee -a $LOG

# 4) 재학습 원격 실행 (setsid로 A100 내부 완결)
echo "[4] A100 재학습 launch $(date)" | tee -a $LOG
$A100 'cd /workspace/cadence && setsid bash retrain_camnear_0704.sh > runs/retrain_camnear_0704.nohup 2>&1 < /dev/null &' >> $LOG 2>&1
echo "[4] ✅ 재학습 launch 완료. A100 runs/retrain_camnear_0704.log 확인." | tee -a $LOG
echo "===== auto_chain_camnear 체인 종료(재학습은 A100서 진행중) $(date) =====" | tee -a $LOG
