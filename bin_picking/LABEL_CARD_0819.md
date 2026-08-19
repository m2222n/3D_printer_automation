# 라벨링 카드 — 8/19 (90장 / 630 인스턴스)

> 8/18 본촬영 90장의 라벨링. **찍는 건 공장에서만 되고 라벨은 언제든 된다**
> ⇒ ⭐ **60장 먼저 라벨 → F1 측정 → 나머지 30장은 다음 주.**
> 정답지 `group_labels_0818.json` · 근거 `memory/project_capture_done_0818.md`

## 0. 준비 상태 (8/19 완료)

| 항목 | 상태 |
|---|---|
| `label_png/` 90장 생성 | ✅ (1696x960, HUD 없음, npy의 2배) |
| `label_png/labels.txt` | ✅ 29줄 (0731과 동일 파일) |
| 라벨명 ↔ labels.txt 대조 | ✅ **21종 전부 일치, 오타 0** |
| 부품 개수 검산 | ✅ 90장 전부 **7개** (blob 중앙값 7) |

🚨 **라벨링은 `label_png/`에서 한다** — 촬영 원본 PNG에는 HUD(BAND·DIST·흰 박스)가
박혀 있어 부품을 가리고, 학습셋과 컬러맵이 달라 경계 판단 기준이 어긋난다.

## 1. 실행

```bash
cd /data/jtm/synth_out/blaze_capture_0818/label_png
labelme . --labels labels.txt --output ./labelme_json --nodata
```

## 2. 🚨 그리기 규칙 — 여기서 틀리면 F1이 조용히 왜곡된다

1. ⭐⭐ **반드시 `polygon`으로, 첫 점을 클릭해 닫을 것**
   - 닫지 않고 Enter → `linestrip`(열린 선)으로 확정된다
   - 평가기는 **`polygon`/`rectangle`만 마스크로 만든다** ⇒ 열린 선은 **GT에서 통째로 빠지고**,
     모델이 맞게 찾아도 **FP로 집계되어 precision이 억울하게 떨어진다**
   - 🔴 **8/5에 실제로 밟았다** = 299개 중 **23개**(linestrip 22 + points 1)가 이 형태였다
2. **부품이 잘려 두 조각으로 보여도 한 부품이면 한 폴리곤** (A그룹에서 자주 발생)
3. **부품끼리 닿아 한 덩어리로 보여도 부품 수만큼 따로** (B/C그룹에서 자주 발생)

## 3. 장당 라벨 개수 = **항상 7개**

| 그룹 | shot | 후보 종류 | 장당 |
|---|---|---|---|
| **B** | 001–030 (`_c1`) | **6종** | **7개** ⚠️ `13_variant`가 **2개** |
| **C** | 031–060 (`_c3`) | 7종 | 7개 (1종 1개) |
| **A** | 061–090 (`_c4`) | 7종 | 7개 (1종 1개) |

🚨 **파일명 접미사가 아니라 shot 범위가 정답**(촬영 중 c2가 비어 밀렸다).

### 그룹별 후보 (이 목록 밖의 이름은 그 장에 없다)

**B** `07_guide_paper_l` `09_guide_paper_r` `13_variant`×2 `13_x2_bcf8ccb4` `16_cam_f_bracket` `bracket_sensor1`
**C** `06_sol_block_back` `03_sol_block_front` `plate_e` `r_guide_a_l` `r_guide_a_r` `08_r_guide_a` `brkt_switch`
**A** `bracket_sen_1` `guide_paper_roll_cover_left` `guide_paper_roll_cover_right` `01_sol_block_a` `02_sol_block_b` `18_button_function_niro` `15_roller_bracket`

## 4. 🚨 헷갈리는 자리 3곳

| 대상 | 판단 |
|---|---|
| ⭐⭐ **`13_variant` / `14_13`** | **둘 다 `13_variant`로 라벨** (병합 확정, 태민님 A안). 3mm=2.1px라 **물리적으로 구별 불가** ⇒ 🚨**B그룹은 `13_variant`가 장당 2개, `14_13` 라벨은 쓰지 않는다** |
| ⚠️ **`r_guide_a_l` / `r_guide_a_r` / `08_r_guide_a`** (C) | **구별 가능** — span·높이는 같고 **길이가 271 / 163 / 117.8mm**(70~100px 차) ⇒ **가장 긴 것 = `08_r_guide_a`** |
| ⚠️ **`roll_cover_left` / `right`** (A) | **경계선** — XY 59x48 동일, 두께만 6mm(≈4px) 차. **병합 안 함.** 실제로 구별되는지 라벨링하며 확인하고, 안 되면 기록할 것 |

## 5. 끝나고 반드시 (검산 2단계)

```bash
# ① 형식 검사 — linestrip/points 가 남았는지 (검사만, 안 고침)
/data/jtm/depth_venv/bin/python \
  bin_picking/depth_track/scripts/fix_labelme_shapes.py \
  --dir /data/jtm/synth_out/blaze_capture_0818/label_png/labelme_json
#   → 걸리면 --apply 로 복구 + "면적 의심" 경고는 육안 확인

# ② 내용 검사 — 개수·미지 라벨·그룹 밖 라벨
/data/jtm/depth_venv/bin/python \
  bin_picking/depth_track/scripts/check_labels_0819.py
```

⭐ **①은 "그린 모양이 유효한가", ②는 "맞는 것을 그렸는가"** — 다른 검사다. 둘 다 돌릴 것.
