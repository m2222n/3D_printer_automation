# experiments/ — Sim2Real 실험 스크립트 (Team 6 작성)

발표 최종 결과(27종 test100 **F1 0.684**)를 낸 학습·평가·데이터셋 스크립트 모음.
모델 설계·학습 코드 자체는 조교(임학수)님 제공(`../model/`, `../mentoring_new/`)이고,
이 폴더는 **sim2real 전환 실험**(요인분리·real fine-tune·클래스 병합·평가)을 위해 팀6가 작성한 오케스트레이션이다.

> 실행 환경 = A100 컨테이너 `/workspace/cadence` (num_workers 0, numpy 1.26.4, opencv-headless).
> 코드 안의 절대경로(`/workspace/cadence/...`)는 그 환경 기준. 데이터·체크포인트·로그는 git 미추적(용량).

## 데이터셋 빌더
- `resplit_test100.py` — real 200장을 조교 지정 4:1:5(train80/val18/test102)로 층화 split (출처 shot/shot2 × 그룹 g1/g2/g3 균등, 누수 0 검증)
- `make_23cls.py` — 대칭쌍 4쌍 병합(27→23클래스). memory bank embedding 평균 + scene npz remap (⚠️category_id 1-based)
- `make_26cls.py` — roll_cover 1쌍만 정직 병합(27→26). 발표 §13 근거
- `normalize_camsweep_01.py` — 합성 depth 배경0 + 0-1 정규화

## 학습 (전부 csblur best.pt → real fine-tune)
- `run_LMN_0707.sh` — 최고 결과. L(csblur lr1e-4 80ep)=test40 F1 0.818
- `run_t100_0707.sh` — test100 정식조건 재학습 (발표 메인 0.684)
- `run_GHIJ_0707.sh` / `run_EF_0707.sh` — lr·init·epoch 요인분리 7판
- `run_23cls.sh` / `run_26cls.sh` — 클래스 병합 재학습
- `retrain_*_0704.sh` — 합성 augmentation 요인분리 6판 (csblur만 baseline 초과=발표 §7)
- `run_finetune_noside_0706.sh` / `run_finetune2_0706.sh` — 초기 real fine-tune (0.45 도약)

## 평가 / 진단
- `reeval_23cls.sh` — 병합 라벨셋 재평가 (eval codebook은 checkpoint서 로드, `--cad_memory` 주면 죽음)
- `grid_eval_L_0707.sh` — score×mask×nms 16조합 그리드서치 (threshold 무영향=음성결과)
- `eval_after_finetune_0706.sh` — fine-tune 완주 감지→자동 test 채점
- `symmerge_score.py` — 대칭쌍 병합 후처리 채점 (학습 없이 F1 재계산, per-scene CSV 파싱)
- `viz_clean.py` — eval 저장 예측을 depth 위에 그려 깨끗한 추론 예시 생성 (발표 §11)
- `diag_pairs.py` — 종류혼동 대칭쌍 진단 (발표 §12 백미 = A/B/C 3유형)
- `probe_norm.py` / `probe_real_norm.py` / `dryrun_norm.py` — 정규화·스케일 검증

## 발표 스토리 (재현 순서)
합성만 0.203 → real 30장 fine-tune 0.45 → real 200장 + lr 1e-4 = test40 0.818 → test100 정식 0.684.
병목 = 학습 아닌 센서 물리(대칭·표면패턴). 상세 = 슬라이드 9·10·12.
