# `real_capture100` 촬영·라벨링 절차 (2026-06-26 ~ 06-29)

> ⛔ **종료된 작업의 절차 기록.** 이 100장은 이미 촬영·라벨링이 끝났고
> **지금은 평가셋(test)으로만 쓴다.** 원본 2개(`capture_guide_100.md` ·
> `실증100장_라벨링_가이드_0629.md`)를 8/19에 이 파일로 통합했다.
>
> ⭐ **왜 남기나** — **g1/g2/g3 그룹 구성표**는 이 데이터셋을 평가에 쓸 때
> "이 장에 어떤 부품이 있어야 하는가"의 정답지이고, 지금도 유효하다.
> label 번호는 `label_map_27parts.md`가 정본.
>
> 🚨 **회사 빈피킹의 현행 절차는 이것이 아니다** →
> 촬영 `bin_picking/FIELD_CARD_0818.md` · 라벨링 `bin_picking/LABEL_CARD_0819.md`

---

## 1. 데이터셋 개요

**27종 × 3그룹 = 100장** (그룹당 9종을 한 판에 깔고 촬영, 부품 교체 2회)
raw **848×480 uint16**, top-down, Basler Blaze.
파일명 `shot_001_g1.npy` … `shot_100_g3.npy` — 접미사 `_gN`이 그 장의 9종 그룹.

| 그룹 | shot 범위 | 장수 | label |
|---|---|---|---|
| **g1** | 001~034 | 34 | 1~9 |
| **g2** | 035~067 | 33 | 10~18 |
| **g3** | 068~100 | 33 | 19~27 |

### ⭐ 그룹별 부품 9종 (평가 시 정답지)

**g1** `01_sol_block_a` · `03_sol_block_front` · `08_r_guide_a` · `13_variant` ·
`18_button_function_niro` · `bracket_sen_1` · `main_body` · `r_guide_a_r` · `top_inner_sheet`

**g2** `09_guide_paper_r` · `14_13` · `16_cam_f_bracket` · `bracket_case` ·
`bracket_sensor1` · `bracket_sensor2` · `brkt_switch` · `plate_e` · `r_guide_a_l`

**g3** `02_sol_block_b` · `06_sol_block_back` · `07_guide_paper_l` · `11_sw_block` ·
`13_x2_bcf8ccb4` · `15_roller_bracket` · `17_mks_holder` ·
`guide_paper_roll_cover_left` · `guide_paper_roll_cover_right`

📌 **각 장에는 그 그룹 9종만 등장한다** ⇒ 그룹 밖 부품이 라벨되면 **오류로 자동 탐지**된다.
⭐ 이 발상이 8/18 본촬영의 `group_labels_0818.json`으로 이어졌다.

---

## 2. 촬영 방식 (당시)

- 그룹당 **겹침(적재형) ~20장 + 펼침(정렬형) ~13장** — 합성 주력은 겹침, 펼침은 형태 전체가 보이는 케이스
- 매 장 위치·자세·회전 다르게(같은 장면 두 번 금지), 저장 전 손으로 흐트러뜨림
- 화면에 **부품만 + 배경 검정**, 박스 벽이 들어오면 거리·각도 조정

🚨 **이 방식과 8/18 본촬영의 결정적 차이**
| | real_capture100 (7월) | 8/18 본촬영 |
|---|---|---|
| 장당 종류 | **9종** | **7종** |
| 장당 개수 | 9개 (1종 1개) | 7개 (1종 1개) |
| 그룹 구성 | label 번호 순서대로 3등분 | ⭐**혼동쌍이 같은 그룹에 오도록 설계** |

⭐ 8/18에 그룹을 **혼동쌍 기준으로 다시 짠** 이유 = *"모델이 A와 B를 구별하려면 둘을
동시에 보며 배워야 한다. 갈라놓으면 각각은 외우지만 같이 나타나면 못 가린다."*

---

## 3. 라벨링 방식 (당시)

labelme + SAM2/AI-Box, 부품마다 polygon 1개, 라벨 = **STL 이름**.
같은 부품이 한 장에 2개면 각각 따로(instance 분리), 라벨 이름은 같게.
occlusion은 **보이는 부분만**(가려진 뒤쪽을 상상해서 그리지 않음).

**좌표 스케일** = `label_png`(1696×960) = npy(848×480) **×2** → 변환기가 자동 /2.
⭐ 이 2배 규약은 **지금도 동일**하다(`make_label_png.py --scale 2.0`).

**변환** = `labelme_to_synthformat.py` → 합성 `dataset_2denc` 포맷 npz
(⚠️ 조교 7/1 지시로 **배경 NaN → 0 + 부품만 0-1 정규화**로 변경됨)

**6DoF pose 없음** — 실물 자세를 실측하지 않아 instance mask + category_id까지가 범위.

---

## 4. 데이터 위치

```
/data/jtm/synth_out/real_capture100/
├── npy/            100장 원본 (848×480 uint16)
├── label_png/      라벨링용 PNG (1696×960)
├── labelme_json/   라벨 100개
└── synthformat/    변환본 npz
```
백업 = `/data/jtm/synth_out/real_capture100_BACKUP_ORIGINAL_0629/` (읽기전용)
