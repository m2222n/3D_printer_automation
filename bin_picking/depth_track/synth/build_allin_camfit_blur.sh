#!/usr/bin/env bash
# 올인(All-in) 판 빌드: camfit(크기정합 580px) + 엣지블러 light
#   미팅 안건 ③(엣지 뭉개기) + 7/4 확증한 크기정합을 한 데이터셋에 결합.
#   개별 ablation 판(csnorm/csblur/csblurmed/camfit)과 별개로,
#   "발표용 최고성능 후보"를 노린 조합 판.
# 전제: camfit 1000장 생성 완료(/data/jtm/synth_out/dataset_2denc_camfit/npz).
# 흐름: camfit npz → edge_blur light 적용 → A100 tar-over-ssh 전송.
#   (A100 재학습 launch는 이 스크립트 성공 후 별도 실행 — retrain_camfitblur_0704.sh)
set -eu
# 학습 서버 접속 정보는 환경변수로 주입 (하드코딩 금지)
#   export GPU_HOST=<user@host>  GPU_PORT=<port>
GPU_HOST="${GPU_HOST:?GPU_HOST 미설정 (예: export GPU_HOST=user@host)}"
GPU_PORT="${GPU_PORT:-22}"
PY=/home/jtm/table_crop_env/bin/python
SYNTH=/home/jtm/kaist_project/synth
CAMFIT=/data/jtm/synth_out/dataset_2denc_camfit/npz
ALLIN=/data/jtm/synth_out/dataset_2denc_camfitblur_light/npz

echo "=== [1/2] camfit에 엣지블러 light 적용 $(date) ==="
"$PY" "$SYNTH/edge_blur_aug.py" --in_dir "$CAMFIT" --out_dir "$ALLIN" --strength light

N=$(ls "$ALLIN"/*.npz 2>/dev/null | wc -l)
echo "생성: ${N}장"
[ "$N" -ge 1000 ] || { echo "⚠️ 1000장 미만, 중단"; exit 1; }

echo "=== [2/2] A100 전송 (tar over ssh — rsync 미설치 교훈) $(date) ==="
DST=/workspace/cadence/data/2d_dataset_camfitblur_light/npz
ssh -o ConnectTimeout=15 "$GPU_HOST" -p "$GPU_PORT" "mkdir -p $DST"
cd "$ALLIN" && tar cf - *.npz | ssh -o ConnectTimeout=15 "$GPU_HOST" -p "$GPU_PORT" "cd $DST && tar xf - && ls *.npz | wc -l"
echo "=== 올인 데이터 준비 완료 $(date) ==="
