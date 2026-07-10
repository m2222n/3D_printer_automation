#!/usr/bin/env python3
# real 200장 → 조교 4:1:5 (train80/val20/test100) 재-split.
# 층화(stratified): shot/shot2 출처 × g1/g2/g3 그룹이 각 split에 골고루 들어가게.
import json, re, random, os
from collections import defaultdict

DS = "/workspace/cadence/mentoring_new/data/real_labelme_dataset_E200_noside"
ALL = json.load(open(f"{DS}/splits/all.json"))
scenes = ALL["scenes"]
assert len(scenes) == 200, len(scenes)

def strat_key(s):
    sid = s.get("source_id","")
    src = "shot2" if "shot2" in sid else "shot"
    m = re.search(r"_g([123])", sid)
    grp = m.group(1) if m else "0"
    return f"{src}_g{grp}"

# 층별로 모아서 4:1:5 비율로 분배
buckets = defaultdict(list)
for s in scenes:
    buckets[strat_key(s)].append(s)

random.seed(42)
train, val, test = [], [], []
for key in sorted(buckets):
    lst = buckets[key][:]
    random.shuffle(lst)
    n = len(lst)
    # 4:1:5 비율 → train 0.4, val 0.1, test 0.5
    n_tr = round(n*0.4)
    n_va = round(n*0.1)
    train += lst[:n_tr]
    val   += lst[n_tr:n_tr+n_va]
    test  += lst[n_tr+n_va:]

# 총합 맞추기 (반올림 오차 보정 → train80/val20/test100 목표)
def dump(name, lst):
    out = {"split": name, "data_root": DS, "scenes": lst}
    p = f"{DS}/splits/{name}_t100.json"
    json.dump(out, open(p,"w"), indent=1)
    return p, len(lst)

print("층별 분포:", {k: len(v) for k,v in sorted(buckets.items())})
for nm, lst in [("train", train), ("val", val), ("test", test)]:
    p, n = dump(nm, lst)
    # 그룹/출처 분포 출력
    dist = defaultdict(int)
    for s in lst: dist[strat_key(s)] += 1
    print(f"{nm}: {n}장  {dict(sorted(dist.items()))}  -> {p}")

# 누수 검증: train/val/test 간 scene_id 겹침 0이어야
ids = lambda L: set(s["scene_id"] for s in L)
assert not (ids(train)&ids(test)), "누수! train∩test"
assert not (ids(train)&ids(val)), "누수! train∩val"
assert not (ids(val)&ids(test)), "누수! val∩test"
print("누수 검증 OK (train/val/test 완전 분리)")
