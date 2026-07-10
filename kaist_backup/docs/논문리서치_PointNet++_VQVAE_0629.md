# 논문 리서치 — PointNet++ & VQ-VAE (우리 모델 근거)

> **작성**: 2026-06-29 · 정태민
> **목적**: 6/19 미팅서 확정된 우리 모델 근거 논문 2편 정리. 최종발표(7/9)·논문 공저·7/1 멘토링 대비.
> **우리 모델 구성** (6/19 명문화): 3D 인코더 = **PointNet++** (CAD→pointcloud) / 2D 인코더 = **VQ-VAE의 VQ만** (DepthMap, RGB X, point 뿌리기). 두 인코더를 latent space에서 정렬·복원.

---

## 0. 왜 이 두 논문인가 (한 줄씩)

- **PointNet++** = 3D CAD 형상을 **point cloud로 받아 계층적으로 인코딩**하는 백본. 우리 3D 인코더의 뼈대.
- **VQ-VAE (VQ)** = 2D Depth 인코더의 연속 feature를 **이산 codebook 벡터로 양자화**하는 모듈. 3D(point)와 2D(depth)를 **공통 이산 표현(codebook)으로 정렬**하는 다리.
- ⚠️ **6/25 발표 Q&A 연결**: "2D는 DepthMap, 3D는 CAD point — modality 비대칭" 지적이 나왔음. 이 두 논문이 각 modality를 어떻게 다루는지 이해하면, 향후 "depth를 K-역투영해 point로 통일"하는 확장(=다음 멘토링 안건)의 근거가 됨.

---

## 1. PointNet++ (arXiv 1706.02413, Qi et al. 2017)

### 1-1. 한 줄 요약
PointNet에 **계층적(hierarchical) 구조**를 도입해, point cloud의 **지역(local) 기하 구조**를 점점 넓은 스케일로 학습. CNN이 이미지를 다루듯 point cloud를 다루게 함.

### 1-2. PointNet의 한계 → PointNet++이 나온 이유
- 원조 PointNet: 각 점을 개별 MLP로 처리 후 **max-pooling 한 번으로 전역(global) 특징으로 압축**.
- 따라서 점들이 놓인 거리공간의 **지역 구조(곡면·모서리·부분 형태)를 못 봄** → 세밀한 패턴 인식·복잡한 장면 일반화 약함.

### 1-3. 핵심 아이디어
- **계층적 특징 학습**: PointNet을 점들의 **중첩 부분집합에 재귀 적용**. 낮은 층=미세구조 / 높은 층=큰 구조.
- **Set Abstraction (SA) layer** — 3단계:
  1. **Sampling** — **FPS(Farthest Point Sampling)** 로 대표 중심점 선택 (랜덤보다 공간 고르게 덮음).
  2. **Grouping** — 각 중심점 주변 이웃 점을 묶어 지역 영역 구성 (ball query 반경 or kNN).
  3. **PointNet** — 각 지역 영역에 mini-PointNet 적용 → 영역 하나를 특징 벡터로 인코딩. 상대좌표로 이동 불변성.
- **밀도 불균일 대응** (실 센서는 가까운 곳 빽빽/먼 곳 성김):
  - **MSG (Multi-Scale Grouping)**: 같은 중심점에서 **여러 반경**으로 그룹핑 후 concat (정확·연산량 큼).
  - **MRG (Multi-Resolution Grouping)**: 하위층 특징 + raw 점 특징 결합 (효율적).

### 1-4. 구조
- **인코더**: SA layer 여러 개 적층. 층마다 점 수↓ 특징 차원↑ (CNN식 점진 추상화).
- **분류 head**: 전역 특징 → FC → 클래스 점수.
- **세그멘테이션 head**: **Feature Propagation(FP)** — 역거리 가중 보간으로 상위층 특징을 조밀한 점으로 전파 + skip connection + unit PointNet → 원본 해상도 복원 → 점별 라벨.

### 1-5. 입력 / 출력
- 입력: **N×3** (xyz) 또는 **N×(3+C)** (법선·색 등 추가 특징).
- 출력: 분류 = K개 클래스 확률 / 세그 = 점별 라벨(N개 각각).

### 1-6. 성능 / 의의
- **ModelNet40 분류 ~91.9%** (당시 SOTA), ScanNet 등에서도 최고 성능.
- point cloud에 **CNN식 계층적·다중스케일 학습**을 처음 효과적으로 구현 → 이후 3D 딥러닝 백본 표준.

### 🎯 우리 프로젝트 연결
- 3D 인코더가 CAD를 point로 뿌려 받음(mesh 아님, 6/19 확정) → SA layer가 부품 표면의 지역 관계성 학습.
- ⭐ **MSG의 밀도 불균일 강건성**이 핵심: Blaze depth → point 변환 시 거리에 따라 밀도가 달라지므로, 이 설계가 실증 데이터에 그대로 유효. (depth-point 통일 확장 시 특히 의미)

---

## 2. VQ-VAE (arXiv 1711.00937, van den Oord et al. 2017)

### 2-1. 한 줄 요약
연속 잠재변수 대신 **이산(discrete) 잠재변수**를 학습. 인코더 출력을 학습 가능한 **codebook**의 가장 가까운 벡터로 **양자화(VQ)** → 단순하고 posterior collapse 없는 이산 표현.

### 2-2. 기존 VAE 한계 → 왜 discrete latent
- 일반 VAE = 연속 가우시안 latent.
- **Posterior collapse**: 디코더가 강력하면 latent z를 무시 → latent가 의미 정보를 못 담음.
- 많은 데이터(언어·음소·객체)가 본질적으로 이산 → 이산 표현이 자연스럽고, VQ-VAE는 결정론적 이산 구조로 collapse 회피.

### 2-3. 핵심 — Vector Quantization (VQ) ⭐
- 임베딩 공간 **e ∈ R^(K×D)**: D차원 벡터가 **K개** (K = 이산 코드 개수).
- 작동: ① 인코더가 연속 출력 **z_e(x)** 생성 → ② **nearest-neighbor 양자화**(L2 최소 codebook 벡터 선택) → ③ 그 벡터 **z_q(x) = e_k** 를 디코더 입력으로.
- 즉 **인코더 출력을 가장 가까운 codebook 벡터로 "스냅"** = discretisation bottleneck.
- 실제론 단일 z가 아니라 feature map(2D=이미지 grid 등)에 위치별 적용.

### 2-4. 학습 — 3개 loss + straight-through
```
L = log p(x|z_q(x))         (a) reconstruction — 인코더+디코더 학습
  + ||sg[z_e(x)] − e||²       (b) codebook loss — codebook을 인코더 출력 쪽으로 (k-means 유사)
  + β·||z_e(x) − sg[e]||²     (c) commitment loss — 인코더가 코드에 commit (β=0.25)
```
- `sg[·]` = stop-gradient.
- **Straight-through estimator**: argmin은 미분 불가 → forward는 z_q(x), backward는 디코더 입력 기울기를 **그대로 인코더로 복사** (양자화를 항등처럼 통과). z_e와 z_q가 같은 공간이라 유효.
- codebook은 loss 대신 **EMA**로 갱신 가능(후속 구현 흔히 채택).

### 2-5. Codebook이란 ⭐
- **K개 D차원 임베딩 벡터의 학습 가능한 테이블** (dictionary). 표현 가능한 "이산 코드 어휘집".
- 각 latent 위치 = 정수 인덱스 1개(0~K−1) → codebook의 한 벡터를 가리킴.
- 연속 표현을 유한 prototype으로 압축 → 이산·해석가능.

### 2-6. 의의 / 후속
- 장점: collapse 회피, 압축·해석 용이, 강력한 prior와 결합 가능, 단순.
- 후속: **VQ-VAE-2**(계층 codebook 고해상도), **VQGAN**(VQ+GAN, Transformer prior) → 현대 멀티모달 **이산 토큰화** 패러다임 기반.

### 🎯 우리 프로젝트 연결
- **"VQ만" 떼어 2D 인코더에 붙인다** = 2D Depth 인코더 feature map의 각 위치 벡터를 codebook nearest로 양자화 + codebook/commitment loss + straight-through로 학습.
- 생성용 prior(PixelCNN)·reconstruction 디코더는 **안 씀** — **양자화 병목 + codebook + STE** 부분만 재사용.
- ⭐ **두 modality 정렬의 핵심**: 3D(point)와 2D(depth)가 **같은 codebook**을 공유하면, 서로 다른 입력이 공통 이산 코드로 매핑 → latent space에서 부품 식별/복원이 가능. (조교 CADENCE 파이프라인의 CAD VQ head와 정합)

---

## 3. 7/1 멘토링 / 최종발표용 메모

- **modality 비대칭 (6/25 Q&A)**: 현재 2D=DepthMap(투영된 2D) / 3D=CAD point(3D). VQ codebook이 둘을 같은 이산 공간으로 묶지만, **입력 modality 자체는 비대칭**. → 향후 **depth를 카메라 intrinsic으로 역투영(back-projection)해 point cloud로 통일**하면 양쪽 다 PointNet++로 처리 = 진짜 대칭. (다음 멘토링 안건)
- **논문 공저 관점**: 우리 기여 = "데이터(합성+실증) + 비교 실험". 두 논문은 차용한 빌딩블록이므로 related work/method에서 정확히 인용 필요 (위 핵심·수식 그대로 활용 가능).
- **출처**:
  - PointNet++: https://arxiv.org/abs/1706.02413 · PDF https://arxiv.org/pdf/1706.02413
  - VQ-VAE: https://arxiv.org/abs/1711.00937 · PDF https://arxiv.org/pdf/1711.00937
