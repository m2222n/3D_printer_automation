"""23클래스 대칭쌍 병합 데이터셋 + memory bank 생성.
대칭 4쌍을 대표 하나로 병합(라벨 remap). category_id 픽셀맵도 remap.
--verify 5장만 검증. 인자 없으면 전체 200 npz + memory bank 생성.
"""
import numpy as np, glob, json, os, sys, shutil

SRC_DS = "/workspace/cadence/mentoring_new/data/real_labelme_dataset_E200_noside"
DST_DS = "/workspace/cadence/mentoring_new/data/real_labelme_dataset_23cls"
SRC_CAD = "/workspace/cadence/runs/cad_pointnet2/cad_memory_bank.npz"
DST_CAD = "/workspace/cadence/runs/cad_pointnet2/cad_memory_bank_23cls.npz"

# 대칭쌍: {제거될 cad_name: 대표 cad_name}
MERGE = {
    "09_guide_paper_r": "07_guide_paper_l",
    "guide_paper_roll_cover_right": "guide_paper_roll_cover_left",
    "r_guide_a_r": "r_guide_a_l",
    "06_sol_block_back": "03_sol_block_front",
}

def norm(name):
    """cad_name/stl에서 확장자·접미사 떼고 MERGE 판단용 정규화."""
    b = str(name).strip()
    if b.endswith(".stl"): b = b[:-4]
    return b

def merged_name(name):
    n = norm(name)
    return MERGE.get(n, n)

VERIFY = "--verify" in sys.argv

# ---------- 1. memory bank 23클래스 재생성 ----------
cm = np.load(SRC_CAD, allow_pickle=True)
cad_ids = [str(x) for x in cm["cad_ids"]]
class_names = [str(x) for x in cm["class_names"]]
emb = cm["embeddings"]; lxyz = cm["local_xyz"]; ltok = cm["local_tokens"]

# 대표 cad_name → 원본 인덱스들
groups = {}  # rep_name -> [orig_idx,...]
order = []   # 대표 등장 순서
for i, cn in enumerate(class_names):
    rep = merged_name(cn)
    if rep not in groups:
        groups[rep] = []; order.append(rep)
    groups[rep].append(i)

new_cad_ids, new_class_names, new_emb, new_lxyz, new_ltok = [], [], [], [], []
for rep in order:
    idxs = groups[rep]
    # 대표 cad_id는 그 그룹의 원본 cad_id 중 대표명에 해당하는 것 사용
    rep_i = idxs[0]
    for i in idxs:
        if norm(class_names[i]) == rep: rep_i = i
    new_cad_ids.append(cad_ids[rep_i])
    new_class_names.append(rep)
    new_emb.append(emb[idxs].mean(0))
    new_lxyz.append(lxyz[idxs].mean(0))
    new_ltok.append(ltok[idxs].mean(0))

new_emb = np.stack(new_emb).astype(np.float32)
print(f"[memory bank] {len(cad_ids)}클래스 -> {len(new_cad_ids)}클래스")
print("  병합된 대표:", [r for r in order if len(groups[r])>1])

if not VERIFY:
    np.savez(DST_CAD,
             cad_ids=np.array(new_cad_ids),
             class_names=np.array(new_class_names),
             cad_indices=np.arange(len(new_cad_ids)),
             class_indices=np.arange(len(new_cad_ids)),
             embeddings=new_emb,
             local_xyz=np.stack(new_lxyz).astype(np.float32),
             local_tokens=np.stack(new_ltok).astype(np.float32))
    print(f"  저장: {DST_CAD}")

# category_id 픽셀맵/meta는 1-based (0=배경, 1..27). class_indices는 0-based (0..26).
# 따라서 category_id_old(1-based) = old_class_idx + 1.  remap: 새 category_id = new_class_idx + 1.
old_to_new = {}           # 0-based class idx old->new (cad memory용)
old_cat_to_new_cat = {}   # 1-based category_id old->new (픽셀맵/meta용)
for new_i, rep in enumerate(order):
    for oi in groups[rep]:
        old_to_new[oi] = new_i
        old_cat_to_new_cat[oi + 1] = new_i + 1
print("  old->new class_idx(0-based) 예시:", dict(list(old_to_new.items())[:8]))
print("  old->new category_id(1-based) 예시:", dict(list(old_cat_to_new_cat.items())[:8]))

# ---------- 2. scene npz remap ----------
files = sorted(glob.glob(f"{SRC_DS}/npz/scene_*.npz"))
if VERIFY: files = files[:5]
else:
    os.makedirs(f"{DST_DS}/npz", exist_ok=True)
    # splits 심링크/복사
    if os.path.exists(f"{SRC_DS}/splits"):
        shutil.copytree(f"{SRC_DS}/splits", f"{DST_DS}/splits", dirs_exist_ok=True)

n_inst_merged = 0
for f in files:
    d = np.load(f, allow_pickle=True)
    meta = json.loads(str(d["meta"]))
    cat = d["category_id"].copy()
    # instances의 cad_name/stl/raw_label + meta category_id(1-based) 병합
    for k, inst in meta["instances"].items():
        merged_here = False
        for fld in ("cad_name", "stl", "raw_label"):
            if fld in inst and inst[fld]:
                nm = merged_name(inst[fld])
                if norm(inst[fld]) != nm:
                    merged_here = True
                inst[fld] = nm + (".stl" if fld == "stl" else "")
        # meta의 category_id도 1-based remap
        if "category_id" in inst and inst["category_id"] is not None:
            oc = int(inst["category_id"])
            inst["category_id"] = old_cat_to_new_cat.get(oc, oc)
        if merged_here:
            n_inst_merged += 1
    # category_id 픽셀맵 1-based remap (배경 0은 유지)
    newcat = cat.copy()
    for oc, nc in old_cat_to_new_cat.items():
        if oc != nc:
            newcat[cat == oc] = nc
    if not VERIFY:
        newmeta = json.dumps(meta, ensure_ascii=False)
        np.savez(os.path.join(f"{DST_DS}/npz", os.path.basename(f)),
                 depth=d["depth"], inst_id=d["inst_id"],
                 category_id=newcat, meta=newmeta)

print(f"[scene npz] {len(files)}장 처리, 병합된 instance {n_inst_merged}건 ({'검증만' if VERIFY else '저장'})")
if VERIFY:
    print("검증 OK — 실제 생성은 --verify 없이 실행")
