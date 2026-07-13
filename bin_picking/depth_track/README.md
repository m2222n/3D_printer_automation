# depth_track — Depth 기반 빈피킹 인식·식별 트랙

`bin_picking/`의 **두 번째 인식 트랙**. `yolo_track/`(RGB YOLO)과 대등하게 나란히 둔다.

- **yolo_track** = RGB 카메라(ace2) + YOLO instance segmentation
- **depth_track** = Depth 카메라(Blaze ToF) 단독 + CAD codebook 매칭 → **색·재질 무관, CAD만 있으면 데이터 수집 없이 학습**

제조 부트캠프 3단계(6주) 성과물을 회사 자산으로 편입한 것. 최종 성능 = **27종 실측 test100 F1 0.684**(위치 0.88 / 종류 0.85).

> 원본 작업 디렉토리(`~/kaist_project`)는 그대로 보존. 여기는 회사 빈피킹에서 실제로 쓰기 위한 편입 사본.

---

## 왜 이 트랙인가 (북극성 정합)

"학습 잘 됨 → 카메라 잘 인식 → 로봇이 빈피킹 잘함"에서, depth_track은 **데이터 수집 병목을 없앤다**:
CAD(STL)만 있으면 합성 depth 데이터를 무한 생성 → 학습 → 실측 소량 fine-tune으로 현장 적응.
색·재질을 안 보므로 조명·색상 변화에 강하고, ToF depth로 형태를 직접 잡는다.

**핵심 교훈 (sim2real 6주 결론)**: 합성 데이터 augmentation을 아무리 강화해도 천장(F1 0.203)이 있다.
성능의 열쇠는 **실측 소량 fine-tune**(0.203 → 30장 0.45 → 200장 0.684)이고, 그중에서도 learning rate가 진짜 지렛대였다.
남은 병목은 학습이 아니라 센서 물리(좌우대칭·표면패턴을 depth만으로 구분 불가) → RGB 융합·고해상 depth가 다음 카드.

---

## 디렉토리 구조

```
depth_track/
├── model/            조교(임학수) depth-only 모델 본체 — 패키지 구조 유지(import 의존)
│   ├── depth_vq_detector/   DETR 계열 detector
│   ├── cad3d_encoder/       PointNet++ 기반 CAD 3D 인코더
│   └── build_cad_memory_bank.py, eval_*, infer_*
├── mentoring_new/    조교 정석 파이프라인 = 실제 train/eval/infer 진입점 (★ 학습은 여기서)
│   ├── train_depth_vq_detector.py       메인 학습
│   ├── eval_real_depth_vq_detector.py   실측 평가 (F1 산출)
│   ├── infer_depth_vq_detector.py       단일 추론
│   └── tools/                           데이터 빌드·split·전처리 도구
├── synth/            합성 데이터 생성 파이프라인 (BlenderProc, 단독 개발)
│   ├── gen_one_2denc*.py    CAD→depth+mask+pose 생성 (camsweep/camfit 변형)
│   ├── depth_noise.py       Blaze ToF 노이즈 모델
│   ├── edge_blur_aug.py     엣지블러 aug (요인분리서 유일 baseline 초과)
│   └── probe_3d_coords*.py  27종 COM·주축·grasp width 추출 → coords_27parts.json
├── scripts/          Blaze 촬영·라벨링·검증 도구 (단독 개발)
│   ├── blaze_capture_100.py, blaze_live_view.py
│   ├── labelme_to_synthformat.py   labelme 라벨 → 학습포맷 변환
│   └── verify_synthformat.py, probe_sim2real_matching.py
├── visual_hull/      초기 3D 복원 baseline (Visual Hull, 참고용)
└── data/             ★ 대용량 자산 심볼릭 링크 (git 제외, 6000 상주)
```

---

## 데이터 위치 (★ GPU 서버로 옮길 때 이 표대로 재연결)

`data/` 하위는 6000 서버 상주 데이터로의 **심볼릭 링크**다. git에는 안 올라간다(절대경로라 서버마다 다름).
다른 GPU 서버로 옮기면 아래 원본을 그 서버로 복사한 뒤 링크를 다시 걸어야 한다.

| data/ 링크 | 원본 (6000) | 내용 |
|-----------|------------|------|
| `synth_1000_27parts` | `/data/jtm/synth_out/dataset_2denc` | 합성 학습 데이터 npz 1000 + crops 8181 (27종) |
| `real_capture100` | `/data/jtm/synth_out/real_capture100` | 실측 Blaze depth 100 + labelme 라벨 100 + synthformat |
| `real_capture100_v2` | `/data/jtm/synth_out/blaze_capture100_v2` | 신규 고품질 실측 100 |
| `checkpoints` | `/data/jtm/a100_backup_0710/checkpoints/extracted` | 발표 모델 best.pt 4개 + eval 결과 |
| `stl_27parts` | `~/kaist_render/stl` | 27종 CAD 원본 STL |

링크 재생성:
```bash
cd depth_track/data
ln -sfn <원본경로>/dataset_2denc          synth_1000_27parts
ln -sfn <원본경로>/real_capture100        real_capture100
ln -sfn <체크포인트경로>                   checkpoints
ln -sfn <STL경로>                          stl_27parts
```

### 체크포인트 4개
| 모델 | 성능 | 용도 |
|------|------|------|
| `T100_csblur_lr1e4_ep80` | **F1 0.684** (위치 0.88/종류 0.85) | ★ 발표 메인, 27종 test100 |
| `L_csblur_lr1e4_ep80_0707` | F1 0.818 | test40 소규모 (참고) |
| `T26_P_baseline_lr1e4` | F1 0.669 | 26종 정직병합 |
| `retrain_csblur_joint` | F1 0.203 | 합성 baseline (fine-tune 출발점) |

best.pt 안에 codebook·args 내장 → 별도 파일 없이 재평가 가능.

---

## ⚠️ GPU 필요 (현재 미정)

학습·평가·추론은 **CUDA GPU 필수**. 6000 서버에는 GPU가 없다(합성 생성·데이터 보관 전용).
KAIST 학습은 임대 A100에서 진행했다. 회사 정식 GPU 환경은 **미정** — 후보:
- **A100 (임대)** — 지금 바로 재현·재학습 가능, 단 임대라 기간 제약
- **IPC-510 (산업용 PC, GPU 5060)** — 현장 배포·실제 피킹 E2E의 최종 지점, 단 셋업 필요

GPU 접속 정보는 **하드코딩하지 말 것**. 스크립트는 환경변수로 주입한다:
```bash
export GPU_HOST=<user@host>
export GPU_PORT=<port>
```

---

## 재현 순서 (GPU 확보 후)

1. **환경**: PyTorch + CUDA, `mentoring_new/`의 requirements 확인. numpy는 1.26.x 고정(2.x는 torch 붕괴), opencv는 headless.
2. **데이터 연결**: 위 "데이터 위치" 표대로 GPU 서버에 데이터 복사 + 링크.
3. **재평가 (학습 없이 F1 0.684 확인)**:
   `mentoring_new/eval_real_depth_vq_detector.py`로 `checkpoints/runs/T100_csblur_lr1e4_ep80/best.pt` + 실측 라벨 평가.
   → 저장된 결과: `data/checkpoints/eval_T100_csblur_lr1e4_ep80_test102/eval_real_metrics.json` (f1_micro 0.6836).
4. **재학습**: `mentoring_new/train_depth_vq_detector.py` (핵심 하이퍼파라미터 = csblur aug + lr 1e-4 + ep 80).
5. **합성 데이터 새로 생성**: `synth/gen_one_2denc.py` → 새 부품 추가/증강 시.

---

## 성능 향상 다음 카드 (병목 = 센서 물리)

- **RGB 융합**: 표면 구멍·슬롯으로만 구분되는 부품(depth 차 없음) → ace2 RGB 결합
- **고해상 depth**: 입체 돌기로 구분되는 부품
- **대칭쌍 문제**: 좌우대칭 부품은 depth-only로 원리상 구분 불가 → 빈피킹에선 동일 취급 or RGB 필요

---

## 출처·소유권

제조 AI 부트캠프 3단계 팀 프로젝트(우수상 수상). 모델 아키텍처는 멘토 협업, 합성/실측 데이터 파이프라인·실험은 자체 개발.
회사 빈피킹 자산으로 편입. 원본 작업 기록은 개발 메모리 참조.
