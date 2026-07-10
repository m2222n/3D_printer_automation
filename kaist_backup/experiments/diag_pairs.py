import csv, collections, sys
csv_path = sys.argv[1]
rows = list(csv.DictReader(open(csv_path)))
conf = collections.Counter()
gt_total = collections.Counter(); correct = collections.Counter()
for r in rows:
    for pair in r["spatial_pairs"].split(";"):
        pair = pair.strip()
        if not pair: continue
        d = dict(x.split("=", 1) for x in pair.split("|"))
        if "pred" not in d or "gt" not in d: continue
        if float(d.get("iou", 0)) < 0.5: continue
        gt = d["gt"]; pr = d["pred"]; gt_total[gt] += 1
        if gt == pr: correct[gt] += 1
        else: conf[(gt, pr)] += 1

pairs = [("07_guide_paper_l", "09_guide_paper_r"),
         ("guide_paper_roll_cover_left", "guide_paper_roll_cover_right"),
         ("r_guide_a_l", "r_guide_a_r"),
         ("03_sol_block_front", "06_sol_block_back")]
print("=== 병합 4쌍: 서로 혼동 횟수 (병합 전) ===")
for a, b in pairs:
    ab = conf.get((a, b), 0); ba = conf.get((b, a), 0)
    print(f"  {a} <-> {b}:  {a}->{b}={ab}, {b}->{a}={ba}, 합={ab+ba}")
print()
print("=== 03/06 관련 전체 혼동 (다른 부품과도?) ===")
for (gt, pr), n in conf.most_common(40):
    if "03_sol_block" in gt+pr or "06_sol_block" in gt+pr:
        print(f"  {n:2d}  {gt} -> {pr}")
