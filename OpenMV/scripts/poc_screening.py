#!/usr/bin/env python
# OpenMV 모니터링 PoC — "세척/경화 상태가 영상으로 구별되는가?"를 수치로 확인.
# 딥러닝 없이 색/밝기 특징 + k-NN. 목적=가능성 스크리닝(Edge Impulse 학습 전 사전 판정).
# ⚠️ 정직한 평가: 클래스당 영상 1개라 프레임 랜덤분할=누수(인접프레임 유사).
#    → 시간순 분할(앞 70% train / 뒤 30% test)로 진짜 일반화 측정.
import cv2, glob, numpy as np
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "training_images"

def feat(img):
    # OpenMV VGA급 가정하고 저해상으로 다운(고해상 이점 제거=공정한 스크리닝)
    im = cv2.resize(img, (64, 64))
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    f = []
    # 색 히스토그램 (H,S,V 각 8bin) — UV발광/조명색 잡음
    for c in range(3):
        h = cv2.calcHist([hsv], [c], None, [8], [0, 256]).flatten()
        f.append(h / (h.sum() + 1e-6))
    # 전체 밝기 평균/표준편차
    f.append([im.mean() / 255, im.std() / 255])
    return np.concatenate(f)

def load(task):  # task='wash' or 'cure'
    Xtr, ytr, Xte, yte = [], [], [], []
    labels = [f"{task}_idle", f"{task}_running", f"{task}_complete"]
    for li, lbl in enumerate(labels):
        fs = sorted(glob.glob(str(BASE / lbl / "*.jpg")))  # 시간순(파일명 순번)
        n = len(fs); cut = int(n * 0.7)
        for i, fp in enumerate(fs):
            x = feat(cv2.imread(fp))
            if i < cut:
                Xtr.append(x); ytr.append(li)
            else:
                Xte.append(x); yte.append(li)
    return np.array(Xtr), np.array(ytr), np.array(Xte), np.array(yte), labels

def knn(Xtr, ytr, Xte, k=5):
    pred = []
    for x in Xte:
        d = np.linalg.norm(Xtr - x, axis=1)
        idx = np.argsort(d)[:k]
        vals, cnts = np.unique(ytr[idx], return_counts=True)
        pred.append(vals[np.argmax(cnts)])
    return np.array(pred)

for task in ["wash", "cure"]:
    Xtr, ytr, Xte, yte, labels = load(task)
    pred = knn(Xtr, ytr, Xte)
    acc = (pred == yte).mean()
    print(f"\n=== {task.upper()} (train {len(ytr)} / test {len(yte)}, 시간순분할) ===")
    print(f"  전체 정확도: {acc:.1%}")
    # 클래스별 혼동
    C = len(labels)
    conf = np.zeros((C, C), int)
    for t, p in zip(yte, pred):
        conf[t][p] += 1
    print("  혼동행렬 (행=정답, 열=예측):")
    print("        " + "  ".join(f"{l.split('_')[1][:4]:>5s}" for l in labels))
    for i, l in enumerate(labels):
        print(f"    {l.split('_')[1][:8]:9s}" + "  ".join(f"{conf[i][j]:5d}" for j in range(C)))
